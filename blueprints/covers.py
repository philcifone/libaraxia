"""Background "fetch missing covers" jobs (logic in utils/cover_jobs.py).

Started from the Goodreads import result and the profile page (your own
books) or the admin covers page (every book). Progress shows in the floating
panel from `_sidebar.html` (static/cover_jobs.js), which polls /covers/status.
"""
from flask import Blueprint, abort, flash, jsonify, redirect, request, url_for
from flask_login import current_user, login_required

from utils import cover_jobs
from utils.database import get_db
from utils.rate_limiting import limiter

covers_blueprint = Blueprint('covers', __name__)


def _wants_json():
    return request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest'


def _back():
    """Where a plain form post returns to: a local path from the form, else the library."""
    target = request.form.get('next', '')
    if target.startswith('/') and not target.startswith('//'):
        return redirect(target)
    return redirect(url_for('base.index'))


@covers_blueprint.route('/start', methods=['POST'])
@login_required
@limiter.limit("30 per hour")
def start():
    scope = request.form.get('scope', 'own')
    if scope not in ('own', 'all'):
        abort(400)
    if scope == 'all' and not current_user.is_admin:
        abort(403)

    conn = get_db()
    job, created = cover_jobs.start_job(conn, current_user.id, scope)
    if job:
        cover_jobs.kick()
        message = (f"Fetching covers for {job['total']} book(s) in the background. "
                   "You can leave this page." if created else "A cover fetch is already running.")
    else:
        message = "Every book with an ISBN already has a cover."

    if _wants_json():
        return jsonify({'success': True, 'job': cover_jobs.as_dict(job), 'message': message})
    flash(message, 'success' if job else 'info')
    return _back()


@covers_blueprint.route('/status')
@login_required
def status():
    """The job for the user's progress panel (or null). Restarts the worker
    if the process that had it died, e.g. a deploy restart."""
    job = cover_jobs.current_job(get_db(), current_user.id)
    if cover_jobs.needs_worker(job):
        cover_jobs.kick()
    return jsonify({'success': True, 'job': cover_jobs.as_dict(job)})


@covers_blueprint.route('/<int:job_id>/stop', methods=['POST'])
@login_required
def stop(job_id):
    conn = get_db()
    conn.execute("UPDATE cover_jobs SET status = 'cancelled', finished_at = CURRENT_TIMESTAMP "
                 "WHERE id = ? AND user_id = ? AND status = 'running'", (job_id, current_user.id))
    conn.commit()
    job = conn.execute('SELECT * FROM cover_jobs WHERE id = ? AND user_id = ?',
                       (job_id, current_user.id)).fetchone()
    return jsonify({'success': True, 'job': cover_jobs.as_dict(job)})


@covers_blueprint.route('/<int:job_id>/dismiss', methods=['POST'])
@login_required
def dismiss(job_id):
    conn = get_db()
    conn.execute("UPDATE cover_jobs SET dismissed = 1 WHERE id = ? AND user_id = ? AND status != 'running'",
                 (job_id, current_user.id))
    conn.commit()
    return jsonify({'success': True})
