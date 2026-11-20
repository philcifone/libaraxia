"""Merge two records into one (ROADMAP 16.0f part B, docs/PROGRESS-MERGE-SPEC.md).

One page for both ways in: an item's Book tools ("Merge another record
into this one", ?keep=<id>) and Admin -> Maintenance. ?keep and ?fold show
the preview; POST merges (a site backup first) and lands on the kept
record; POST /merge/<edit_id>/undo puts it back. The rules are
utils/merge.py (may_merge is checked on every route).
"""
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from models import can_view_book
from utils import backups, bulk, media
from utils import merge as merging
from utils.database import get_db
from utils.rate_limiting import limiter

merge_blueprint = Blueprint('merge', __name__)


def _record(conn, book_id):
    """A books row the viewer may open, with its owner's name, or None."""
    if not book_id or not can_view_book(conn, current_user, book_id):
        return None
    return conn.execute('SELECT b.*, u.username AS owner FROM books b LEFT JOIN users u ON u.id = b.added_by '
                        'WHERE b.id = ?', (book_id,)).fetchone()


@merge_blueprint.route('/')
@login_required
def index():
    conn = get_db()
    keep = _record(conn, request.args.get('keep', type=int))
    fold = _record(conn, request.args.get('fold', type=int))
    preview = reason = None
    if keep and fold:
        reason = merging.may_merge(conn, current_user, keep, fold)
        if not reason:
            preview = merging.plan(conn, keep['id'], fold['id'])
    elif request.args.get('keep') and not keep:
        abort(404)
    query = request.args.get('q', '')
    return render_template(
        'merge.html', keep=keep, fold=fold, preview=preview, reason=reason, query=query,
        found=merging.candidates(conn, current_user, keep, query) if keep and not fold else [],
        merges=merging.recent(conn, current_user),
        m=media.item_labels(keep) if keep else None)


@merge_blueprint.route('/', methods=['POST'])
@login_required
@limiter.limit('30 per hour')
def merge():
    conn = get_db()
    keep = _record(conn, request.form.get('keep', type=int))
    fold = _record(conn, request.form.get('fold', type=int))
    if not keep or not fold:
        abort(404)
    reason = merging.may_merge(conn, current_user, keep, fold)
    back = url_for('merge.index', keep=keep['id'], fold=fold['id'])
    if reason:
        flash(reason, 'error')
        return redirect(back)
    choices = {k[len('choice:'):]: v for k, v in request.form.items() if k.startswith('choice:')}
    fills = request.form.getlist('fill')
    try:
        backups.create('merge', current_user.username)
    except Exception:
        current_app.logger.exception('Backup before a merge failed')
        flash("Couldn't take a backup first, so nothing was merged.", 'error')
        return redirect(back)
    try:
        merging.apply(conn, current_user, keep['id'], fold['id'], choices, fills)
    except merging.MergeError as e:
        flash(str(e), 'error')
        return redirect(back)
    flash(f"Merged {fold['title']} (#{fold['id']}) into this record. "
          f"Undo it from Merge records if it was a mistake.", 'success')
    return redirect(url_for(media.item_endpoint(media.media_type_of(keep)), id=keep['id']))


@merge_blueprint.route('/<int:edit_id>/undo', methods=['POST'])
@login_required
@limiter.limit('30 per hour')
def undo(edit_id):
    conn = get_db()
    edit = conn.execute('SELECT action FROM bulk_edits WHERE id = ? AND user_id = ?',
                        (edit_id, current_user.id)).fetchone()
    if not edit or edit['action'] != merging.ACTION_KEY:
        abort(404)
    try:
        result = bulk.undo(conn, current_user, edit_id)
    except bulk.BulkError as e:
        flash(str(e), 'error')
    else:
        flash('Merge undone: both records are back.' if result.changed
              else "Couldn't undo: the folded record's number is in use again.", 'success' if result.changed else 'error')
    return redirect(url_for('merge.index'))
