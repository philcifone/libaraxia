"""Bulk edit routes (ROADMAP 14, docs/BULK-EDIT-SPEC.md). The rules live in
utils/bulk.py; this turns requests into those calls.

The browser says "these ids, this action, this value". It never names a
column or a table, and permission is decided per item inside utils/bulk.py
at plan, apply and undo time.
"""
from flask import Blueprint, current_app, jsonify, request, session
from flask_login import current_user, login_required

from utils import bulk, media
from utils.database import get_db
from utils.rate_limiting import limiter

bulk_blueprint = Blueprint('bulk', __name__, template_folder='templates')


def _per_user():
    """Rate-limit key: the signed-in user, so a household behind one IP
    doesn't share an allowance."""
    return f'user:{current_user.id}' if current_user.is_authenticated else request.remote_addr


def _fail(message, status=400, **extra):
    return jsonify({'success': False, 'error': message, **extra}), status


def _body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


@bulk_blueprint.app_context_processor
def inject_bulk_result():
    """The banner after an apply or undo shows once (_bulk_result.html):
    `pop_bulk_result()` takes it out of the session."""
    return {'pop_bulk_result': lambda: session.pop('bulk_result', None)}


@bulk_blueprint.route('/plan', methods=['POST'])
@login_required
@limiter.limit('200 per hour', key_func=_per_user)
def plan():
    """What an action would do to a selection, for the review sheet.

    POST only because the id list can be long. It writes nothing."""
    data = _body()
    try:
        result = bulk.plan(get_db(), current_user, data.get('action'), data.get('params'), data.get('ids'))
    except bulk.BulkError as e:
        return _fail(str(e))
    except Exception:
        current_app.logger.exception('Bulk plan failed')
        return _fail('Something went wrong working that out. Nothing was changed.', 500)
    return jsonify({'success': True, 'plan': result.as_dict()})


@bulk_blueprint.route('/selection', methods=['POST'])
@login_required
@limiter.limit('300 per hour', key_func=_per_user)
def selection():
    """The selected items with what each has now, listed under the sheet's
    inputs before the review. POST for the id list; writes nothing."""
    try:
        items = bulk.selection(get_db(), current_user, _body().get('ids'))
    except bulk.BulkError as e:
        return _fail(str(e))
    except Exception:
        current_app.logger.exception('Bulk selection failed')
        return _fail('Something went wrong loading the selection.', 500)
    return jsonify({'success': True, 'items': items})


@bulk_blueprint.route('/apply', methods=['POST'])
@login_required
@limiter.limit('60 per hour', key_func=_per_user)
def apply():
    """Write a reviewed plan. `excluded_ids` are the items the user unticked,
    so the default (everything ticked) is an empty list. If the data moved
    since the plan, answers 409 with the new plan and writes nothing."""
    data = _body()
    conn = get_db()
    try:
        result = bulk.apply(conn, current_user, data.get('action'), data.get('params'), data.get('ids'),
                            data.get('fingerprint'), data.get('excluded_ids') or [])
    except bulk.StalePlan as stale:
        return _fail(str(stale), 409, stale=True, plan=stale.plan.as_dict())
    except bulk.BulkError as e:
        return _fail(str(e))
    except Exception:
        conn.rollback()
        current_app.logger.exception('Bulk apply failed')
        return _fail('Something went wrong. Nothing was changed.', 500)
    if result.edit_id:
        session['bulk_result'] = {'edit_id': result.edit_id, 'summary': result.summary}
    return jsonify({'success': True, 'edit_id': result.edit_id, 'summary': result.summary,
                    'changed': result.changed, 'failed': result.failed})


@bulk_blueprint.route('/<int:edit_id>/undo', methods=['POST'])
@login_required
@limiter.limit('60 per hour', key_func=_per_user)
def undo(edit_id):
    """Undo one of your bulk edits (within 30 days), item by item, leaving
    anything changed since alone."""
    conn = get_db()
    try:
        result = bulk.undo(conn, current_user, edit_id)
    except bulk.BulkError as e:
        return _fail(str(e))
    except Exception:
        conn.rollback()
        current_app.logger.exception('Bulk undo failed')
        return _fail('Something went wrong. Nothing was changed.', 500)
    # Shown once on the next page, without an Undo of its own
    session['bulk_result'] = {'summary': result.summary, 'undone': True}
    return jsonify({'success': True, 'summary': result.summary,
                    'restored': result.changed, 'skipped': result.skipped})


@bulk_blueprint.route('/genres', methods=['GET'])
@login_required
def genres():
    """Your genres for the picker: [{value, count}], most used first, on
    your own items of one type (?type=book|video|record) or all of them."""
    kind = request.args.get('type')
    if kind and kind not in media.MEDIA_TYPES:
        return _fail('Unknown type.')
    return jsonify({'success': True, 'genres': bulk.genres(get_db(), current_user, kind or None)})


@bulk_blueprint.route('/options', methods=['GET'])
@login_required
def options():
    """What the sheet's pickers offer for one type (?type=book|video|record):
    its statuses and formats, your shelves for the section and your tags."""
    kind = request.args.get('type')
    if kind and kind not in media.MEDIA_TYPES:
        return _fail('Unknown type.')
    return jsonify({'success': True, **bulk.options(get_db(), current_user, kind)})
