"""Item values (ROADMAP 16.0a, docs/PHOTOS-VALUE-SPEC.md section 6): the edit
page's Fetch value, the admin's Test value sources, and starting the bulk
Fetch values job (whose progress is the cover jobs' panel, utils/cover_jobs.py).

A fetch here only answers: the edit page puts the value in its field
(static/value_fetch.js) and it's stored when the form is saved, so it can be
looked at first (utils/copy_fields.py). The bulk job stores as it goes.
"""
from flask import Blueprint, abort, current_app, flash, jsonify, redirect, request, url_for
from flask_login import current_user, login_required

from models import admin_required, can_view_book
from utils import condition, copy_fields, cover_jobs, media, valuation
from utils.database import get_db
from utils.rate_limiting import limiter

values_blueprint = Blueprint('values', __name__)


@values_blueprint.route('/fetch/<int:book_id>', methods=['POST'])
@login_required
@limiter.limit('120 per hour')
def fetch(book_id):
    """The value of one item, at the grade (and Discogs release) now on its
    edit form, which may not be saved yet. Owner or admin."""
    conn = get_db()
    row = conn.execute('SELECT * FROM books WHERE id = ?', (book_id,)).fetchone()
    if not row or not can_view_book(conn, current_user, book_id):
        abort(404)
    if not (current_user.is_admin or row['added_by'] == current_user.id):
        abort(403)
    item = dict(row)
    try:
        item['condition'] = condition.clean(row['media_type'], request.form.get('condition', row['condition']))
        if 'discogs_release' in request.form:
            item['discogs_release_id'] = copy_fields.parse_discogs_release(request.form['discogs_release'])
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    result = valuation.fetch(item)
    current_app.logger.info('User %s fetched a value for book %s: %s', current_user.id, book_id,
                            'found' if result.cents is not None else 'none')
    return jsonify({'success': True, 'result': result.as_dict()})


@values_blueprint.route('/test', methods=['POST'])
@login_required
@admin_required
@limiter.limit('20 per hour')
def test():
    """Settings, Maintenance: ask each value source once and say how it went."""
    for name, ok, message in valuation.test_sources():
        flash(f'{name}: {"works" if ok else "not working"}. {message}', 'success' if ok else 'error')
    return redirect(url_for('user.settings', _anchor='maintenance'))


@values_blueprint.route('/start', methods=['POST'])
@login_required
@limiter.limit('30 per hour')
def start():
    """Start the bulk Fetch values job (Settings, Library): your own shelf,
    or everyone's for an admin (scope=all). Sections from the form's
    media_type boxes (none ticked: all); "skip values from the last 30
    days" on unless unticked. Values you typed are never overwritten."""
    scope = request.form.get('scope', 'own')
    if scope not in ('own', 'all'):
        abort(400)
    if scope == 'all' and not current_user.is_admin:
        abort(403)
    types = [t for t in request.form.getlist('media_type') if t in media.MEDIA_TYPES] or None
    # The form sends a hidden 0 and, when ticked, a 1; no field at all is on
    ticks = request.form.getlist('skip_recent')
    skip_days = 30 if (not ticks or '1' in ticks) else None

    conn = get_db()
    job, created = cover_jobs.start_job(conn, current_user.id, scope, kind='value',
                                        media_types=types, skip_days=skip_days)
    if job:
        cover_jobs.kick()
        message = (f"Fetching values for {job['total']} item(s) in the background, about one every "
                   "two seconds. You can leave this page." if created else "A value fetch is already running.")
    else:
        message = ("Nothing to value: every item that a value source can look up was valued recently, "
                   "has a value you typed, or has no ISBN or barcode.")
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'job': cover_jobs.as_dict(job), 'message': message})
    flash(message, 'success' if job else 'info')
    return redirect(url_for('user.settings', _anchor='library'))
