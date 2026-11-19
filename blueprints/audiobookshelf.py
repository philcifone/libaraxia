"""The Audiobookshelf connection (ROADMAP 16.0e, docs/AUDIOBOOKSHELF-SPEC.md):
connect and disconnect from Settings -> Library, Sync, and the import's
review. The client and keys are utils/audiobookshelf.py, the import
utils/abs_import.py; these routes read the form, commit, and come back to
the Settings card or the review with a flash.

The review is one plain form (no script): a select per item and one per
box ("All in this box"), saved with Save choices or Import.

Every route is a 404 while AUDIOBOOKSHELF_URL isn't set, so the feature
doesn't exist on a site without a server.
"""
from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from utils import abs_import
from utils import audiobookshelf as abs_
from utils.audiobookshelf import AbsError
from utils.database import get_db
from utils.rate_limiting import limiter

abs_blueprint = Blueprint('abs', __name__)


@abs_blueprint.before_request
def _only_when_configured():
    if not abs_.enabled():
        abort(404)


def _secret():
    return current_app.config['SECRET_KEY']


def _back():
    """Settings, at the Audiobookshelf card (its hash opens the Library tab)."""
    return redirect(url_for('user.settings', _anchor='audiobookshelf'))


def settings_context(conn, user_id):
    """What the Settings card needs (user.settings passes it as `abs`), or
    None when the feature is off. Never the key; `readable` is False when
    the stored key no longer decrypts (SECRET_KEY changed): Reconnect."""
    if not abs_.enabled():
        return None
    acct = abs_.account(conn, user_id)
    readable = bool(acct) and abs_.token_for(conn, user_id, _secret()) is not None
    staged = conn.execute("SELECT 1 FROM abs_staging WHERE user_id = ? AND staged_at >= datetime('now', ?) LIMIT 1",
                          (user_id, f'-{abs_import.STAGING_HOURS} hours')).fetchone() is not None
    return {'account': acct, 'readable': readable, 'staged': staged}


@abs_blueprint.route('/connect', methods=['POST'])
@login_required
@limiter.limit('10 per hour')
def connect():
    """Check a pasted key against ABS (/api/me) and keep it, encrypted."""
    conn = get_db()
    try:
        username = abs_.connect(conn, current_user.id, request.form.get('abs_token', ''), _secret())
        conn.commit()
        flash(f'Connected to Audiobookshelf as {username}.', 'success')
    except AbsError as e:
        conn.rollback()
        flash(str(e) if not e.auth else "Audiobookshelf didn't accept that key.", 'error')
    except Exception:
        conn.rollback()
        current_app.logger.exception('Audiobookshelf connect failed for user %s', current_user.id)
        flash('Something went wrong; nothing was saved.', 'error')
    return _back()


@abs_blueprint.route('/disconnect', methods=['POST'])
@login_required
@limiter.limit('30 per hour')
def disconnect():
    """Forget the key. What was imported stays."""
    conn = get_db()
    abs_.disconnect(conn, current_user.id)
    conn.commit()
    flash('Disconnected from Audiobookshelf. What you imported stays.', 'success')
    return _back()


# ------------------------------------------------------------------ the import

@abs_blueprint.route('/sync', methods=['POST'])
@login_required
@limiter.limit('10 per hour')
def sync():
    """Read your progress and the libraries from ABS into the review."""
    conn = get_db()
    token = abs_.token_for(conn, current_user.id, _secret())
    if not token:
        flash('Connect to Audiobookshelf first.', 'error')
        return _back()
    try:
        count = abs_import.sync(conn, current_user, token,
                                include_unstarted=request.form.get('include_unstarted') == '1')
    except AbsError as e:
        conn.rollback()
        flash("Audiobookshelf didn't accept your key any more; paste it again." if e.auth else str(e), 'error')
        return _back()
    if not count:
        flash('Nothing to import: no started audiobooks or ebooks on Audiobookshelf.', 'success')
        return _back()
    return redirect(url_for('abs.review'))


@abs_blueprint.route('/review')
@login_required
def review():
    conn = get_db()
    plan = abs_import.plan(conn, current_user)
    if plan is None:
        flash('Nothing waiting for review; sync with Audiobookshelf first.', 'error')
        return _back()
    return render_template('abs_review.html', plan=plan, boxes=abs_import.BOXES,
                           choices=abs_import.CHOICES, hours=abs_import.hours,
                           abs_link=abs_.item_link)


def _form_choices(plan):
    """{item id: choice} from the review form: a box's "All in this box"
    wins over its rows' selects when set."""
    form = request.form
    out = {}
    for row in plan.rows:
        choice = form.get(f'box_{row.box}') or form.get(f'choice_{row.item_id}')
        if choice:
            out[row.item_id] = choice
    return out


@abs_blueprint.route('/choose', methods=['POST'])
@login_required
@limiter.limit('120 per hour')
def choose():
    """Save the review's choices and show it again with what they'd write."""
    conn = get_db()
    plan = abs_import.plan(conn, current_user)
    if plan is None:
        return _back()
    abs_import.choose(conn, current_user, _form_choices(plan))
    flash('Choices saved. Nothing is imported until you press Import.', 'success')
    return redirect(url_for('abs.review'))


@abs_blueprint.route('/apply', methods=['POST'])
@login_required
@limiter.limit('6 per hour')
def apply():
    """Save the form's choices, back up your library, write the import,
    then fetch covers for what it added (a time budget; the rest next
    time). Undo is the bulk journal's, under Recent bulk edits."""
    from utils import personal_backups
    conn = get_db()
    plan = abs_import.plan(conn, current_user)
    if plan is None:
        flash('Nothing waiting for review; sync with Audiobookshelf first.', 'error')
        return _back()
    abs_import.choose(conn, current_user, _form_choices(plan))
    # Your library as it is, before the import writes
    try:
        personal_backups.create(conn, current_user.id, current_user.username, 'audiobookshelf')
    except personal_backups.PersonalBackupError:
        current_app.logger.exception('Backup before the Audiobookshelf import failed for user %s', current_user.id)
        flash("Couldn't back up your library first, so nothing was imported.", 'error')
        return redirect(url_for('abs.review'))
    try:
        result = abs_import.apply(conn, current_user, request.form.get('fingerprint', ''))
    except abs_import.PlanError as e:          # StalePlan included: the review shows the fresh plan
        conn.rollback()
        flash(str(e), 'error')
        return redirect(url_for('abs.review'))
    message = result['summary'] + '.'
    token = abs_.token_for(conn, current_user.id, _secret())
    if token:
        fetched, left = abs_import.fetch_covers(conn, current_user, token)
        if fetched:
            message += f" {fetched} cover{'' if fetched == 1 else 's'} from Audiobookshelf."
        if left:
            message += f" {left} more cover{'' if left == 1 else 's'} next time."
    if result['edit_id']:
        message += ' Undo it under Recent bulk edits.'
    flash(message, 'success')
    return _back()


@abs_blueprint.route('/discard', methods=['POST'])
@login_required
def discard():
    abs_import.discard(get_db(), current_user)
    flash('Review discarded; nothing was imported.', 'success')
    return _back()


# ------------------------------------------------------------------ the item page's live line

# (user id, ABS item id) -> (monotonic time, answer): ABS is asked at most
# once a minute per item, however often the page is opened
_PROGRESS_CACHE = {}
PROGRESS_SECONDS = 60


@abs_blueprint.route('/progress/<int:book_id>')
@login_required
@limiter.limit('120 per hour')
def progress(book_id):
    """Your ABS progress on an item you imported, as JSON for the item
    page (book_detail.js). A 404 unless the link is yours; quiet when ABS
    doesn't answer (the page shows nothing)."""
    import time
    conn = get_db()
    link = abs_import.link_for(conn, current_user.id, book_id)
    token = abs_.token_for(conn, current_user.id, _secret()) if link else None
    if not link or not token:
        abort(404)
    fmt = conn.execute('SELECT format FROM books WHERE id = ?', (book_id,)).fetchone()['format']
    key = (current_user.id, link['abs_item_id'])
    cached = _PROGRESS_CACHE.get(key)
    if cached and time.monotonic() - cached[0] < PROGRESS_SECONDS:
        return jsonify(cached[1])
    try:
        prog = abs_.progress(token, link['abs_item_id'])
    except AbsError:
        return jsonify({'success': False, 'error': "Audiobookshelf didn't answer."}), 502
    answer = {'success': True, **abs_import.progress_line(prog, fmt, link),
              'link': abs_.item_link(link['abs_item_id'])}
    # The covers' ring follows what this just read
    abs_import.store_progress(conn, current_user.id, link['abs_item_id'], answer.get('progress'))
    conn.commit()
    if len(_PROGRESS_CACHE) > 1000:
        _PROGRESS_CACHE.clear()
    _PROGRESS_CACHE[key] = (time.monotonic(), answer)
    return jsonify(answer)
