"""Background "fetch missing covers" jobs (logic in utils/cover_jobs.py).

Started from the Goodreads import result and the profile page (your own
books) or the admin covers page (every book). Progress shows in the floating
panel from `_sidebar.html` (static/cover_jobs.js), which polls /covers/status.
"""
from io import BytesIO

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, request, send_file, url_for
from flask_login import current_user, login_required

from models import can_view_book
from utils import cover_crop, cover_jobs
from utils.image_utils import delete_image_file, is_safe_upload_path
from utils.database import get_db
from utils.rate_limiting import limiter

covers_blueprint = Blueprint('covers', __name__)


def _wants_json():
    return request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest'


def _back():
    """Where a plain form post returns to: the form's `next` (same-site), else
    where it came from, else the library (utils/landing.py)."""
    from utils.landing import back
    return back(url_for('base.index'))


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


# ---------------------------------------------------------------------------
# Cover crop tool (static/cover_crop.js, logic in utils/cover_crop.py)
# ---------------------------------------------------------------------------

def _crop_error(message, status=400):
    return jsonify({'success': False, 'error': message}), status


@covers_blueprint.route('/crop/source', methods=['POST'])
@login_required
@limiter.limit("30 per hour")
def crop_source():
    """Stage a picked photo (up to 2400 px) so the crop works from a big
    original instead of the 500x1000 cover."""
    try:
        staged = cover_crop.stage_upload(request.files.get('image'))
    except ValueError as err:
        return _crop_error(str(err))
    except Exception:
        current_app.logger.exception('Staging a cover for cropping failed')
        return _crop_error("Couldn't prepare that image.", 500)
    return jsonify({'success': True, **staged})


@covers_blueprint.route('/crop/preview', methods=['POST'])
@login_required
@limiter.limit("600 per hour")
def crop_preview():
    """A rendered crop as a JPEG (WebP for a disc). Nothing is stored: the tool shows the blob,
    and the real render happens when the form is saved."""
    data = request.get_json(silent=True) or {}
    source = data.get('source')
    if not cover_crop.is_crop_source(source):
        return _crop_error("That cover can't be cropped.")
    try:
        geom = cover_crop.parse_geometry(data.get('geometry'))
        img = cover_crop.downscale(cover_crop.open_source(source))
        body, mimetype = cover_crop.render_preview(img, geom)
    except ValueError as err:
        return _crop_error(str(err))
    except Exception:
        current_app.logger.exception('Cover crop preview failed')
        return _crop_error("Couldn't render the crop.", 500)
    response = send_file(BytesIO(body), mimetype=mimetype)
    response.headers['Cache-Control'] = 'no-store'
    return response


@covers_blueprint.route('/crop/save/<int:book_id>', methods=['POST'])
@login_required
@limiter.limit("120 per hour")
def crop_save(book_id):
    """Save a crop as the item's cover at once (the crop tool's Save on an
    Edit page; Phil, 2026-11-15), rather than with the form: JSON
    {"source": ..., "geometry": ..., "fetched": ...}. The source is the
    item's own cover, a staged upload or the cover a lookup saved (`fetched`,
    the form's existing_cover_url), exactly as for the edit form's crop
    (cover_crop.apply_form_crop). Owner or admin; 404 for someone who can't
    see the item. The old cover's file goes once the row points at the new."""
    import json
    conn = get_db()
    book = conn.execute('SELECT id, added_by, cover_image_url FROM books WHERE id = ?', (book_id,)).fetchone()
    if not book or not can_view_book(conn, current_user, book_id):
        abort(404)
    if not (current_user.is_admin or book['added_by'] == current_user.id):
        abort(403)
    data = request.get_json(silent=True) or {}
    source, fetched = data.get('source'), data.get('fetched')
    old = book['cover_image_url']
    try:
        new_path = cover_crop.apply_form_crop(
            {'cover_crop': json.dumps(data.get('geometry')), 'crop_source': source or ''},
            [old, fetched if isinstance(fetched, str) and is_safe_upload_path(fetched) else None])
    except ValueError as err:
        return _crop_error(str(err))
    except Exception:
        current_app.logger.exception('Saving a cover crop for book %s failed', book_id)
        return _crop_error("Couldn't save the crop.", 500)
    if not new_path:
        return _crop_error('Nothing to crop.')
    conn.execute('UPDATE books SET cover_image_url = ? WHERE id = ?', (new_path, book_id))
    conn.commit()
    if old and old != new_path:
        delete_image_file(old)
    return jsonify({'success': True, 'message': 'Cropped cover saved.', 'path': new_path,
                    'url': url_for('static', filename=new_path)})
