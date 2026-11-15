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
from utils import condition, copy_fields, valuation
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
