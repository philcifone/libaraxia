"""Photos beyond the cover (ROADMAP 16.0a, docs/PHOTOS-VALUE-SPEC.md section 3).

Added, captioned and deleted from an item's edit page (static/photos.js),
by its owner or an admin. Each route answers JSON to fetch and redirects
back to the edit page's Photos section for a plain form post, so the page
works without JS. Anyone who can see the item sees its photos (they're on
the item page, like the cover); a stranger gets 404 here, as on the item.
"""
from flask import Blueprint, abort, current_app, flash, jsonify, redirect, request, url_for
from flask_login import current_user, login_required

from models import can_view_book
from utils import media, photos
from utils.database import get_db
from utils import cover_crop, image_utils
from utils.image_utils import PhotoError, save_photo, delete_image_file, is_safe_upload_path
from utils.rate_limiting import limiter

photos_blueprint = Blueprint('photos', __name__)


def _wants_json():
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json


def _item_for_owner(conn, book_id):
    """The item, if the current user may change its photos. 404 when they
    can't see it at all (as the item page), 403 when they can see it but
    aren't its owner or an admin."""
    book = conn.execute('SELECT id, title, added_by, media_type, format FROM books WHERE id = ?',
                        (book_id,)).fetchone()
    if not book or not can_view_book(conn, current_user, book_id):
        abort(404)
    if not (current_user.is_admin or book['added_by'] == current_user.id):
        abort(403)
    return book


def _photo_for_owner(conn, photo_id):
    """(photo row, its item), with the same rule as _item_for_owner."""
    row = conn.execute('SELECT * FROM item_photos WHERE id = ?', (photo_id,)).fetchone()
    if not row:
        abort(404)
    return row, _item_for_owner(conn, row['book_id'])


def _done(book, message, ok=True, status=200, **extra):
    """JSON to fetch, or a flash and back to the edit page's Photos section."""
    if _wants_json():
        body = {'success': ok, **extra}
        body['message' if ok else 'error'] = message
        return jsonify(body), status
    flash(message, 'success' if ok else 'error')
    edit = url_for(media.item_endpoint(media.media_type_of(book), 'edit'), id=book['id'])
    return redirect(edit + '#photos')


def _save_files(conn, book, kind, files):
    """Save uploads as `kind` photos of `book`. Returns (saved rows as dicts,
    error message or None). Stops at the first bad file or at the limit."""
    saved = []
    for file in files:
        if not file or not file.filename:
            continue
        if photos.count(conn, book['id']) >= photos.MAX_PER_ITEM and kind == photos.GALLERY:
            return saved, f"An item can have at most {photos.MAX_PER_ITEM} photos."
        try:
            path = save_photo(file, book['id'])
        except PhotoError as e:
            return saved, str(e)
        try:
            new_id = photos.add(conn, book['id'], kind, path)
            conn.commit()
        except Exception:
            conn.rollback()
            delete_image_file(path, image_utils.STATIC_ROOT)
            current_app.logger.exception('Saving photo for book %s', book['id'])
            return saved, "Couldn't save that photo."
        saved.append(photos.as_dict(conn.execute('SELECT * FROM item_photos WHERE id = ?',
                                                 (new_id,)).fetchone()))
    return saved, None


@photos_blueprint.route('/<int:book_id>/<kind>', methods=['POST'])
@login_required
@limiter.limit('120 per hour')
def add(book_id, kind):
    """Add or replace the back or spine; add one or more gallery photos.
    The form field is `photo` (several for the gallery)."""
    conn = get_db()
    book = _item_for_owner(conn, book_id)
    if kind not in photos.kinds_for(media.media_type_of(book), book['format']):
        abort(404)
    files = request.files.getlist('photo')
    if not any(f and f.filename for f in files):
        return _done(book, 'Choose a photo first.', ok=False, status=400)
    if kind in photos.SINGLE:
        files = files[:1]
    saved, error = _save_files(conn, book, kind, files)
    if error:
        return _done(book, error, ok=False, status=400, photos=saved)
    word = photos.label(kind, book['format'], media.media_type_of(book))
    message = (f'{word} photo saved.' if kind in photos.SINGLE
               else f'{len(saved)} photo{"s" if len(saved) != 1 else ""} added.')
    current_app.logger.info('User %s added %d %s photo(s) to book %s',
                            current_user.id, len(saved), kind, book_id)
    return _done(book, message, photos=saved)


@photos_blueprint.route('/photo/<int:photo_id>/delete', methods=['POST'])
@login_required
def delete(photo_id):
    conn = get_db()
    row, book = _photo_for_owner(conn, photo_id)
    photos.delete(conn, photo_id, book['id'])
    conn.commit()
    return _done(book, 'Photo deleted.', id=photo_id)


@photos_blueprint.route('/photo/<int:photo_id>/caption', methods=['POST'])
@login_required
def caption(photo_id):
    conn = get_db()
    row, book = _photo_for_owner(conn, photo_id)
    text = (request.form.get('caption') or '').strip()[:200] or None
    conn.execute('UPDATE item_photos SET caption = ? WHERE id = ? AND book_id = ?',
                 (text, photo_id, book['id']))
    conn.commit()
    return _done(book, 'Caption saved.' if text else 'Caption cleared.', caption=text or '')


@photos_blueprint.route('/photo/<int:photo_id>/crop', methods=['POST'])
@login_required
@limiter.limit('120 per hour')
def crop(photo_id):
    """Crop or straighten a photo with the cover's crop tool (cover_crop.js
    in photo mode): JSON {"geometry": ..., "source": the path it opened}. The photo
    is rendered from its own file and saved as a new one (no metadata, as
    every photo); the old file goes. Owner or admin."""
    import os
    from PIL import Image, ImageOps
    conn = get_db()
    row, book = _photo_for_owner(conn, photo_id)
    data = request.get_json(silent=True) or {}
    if not is_safe_upload_path(row['path']):
        abort(404)
    # The tool names the file it opened. A second Save of the same crop
    # (a slow answer, a second tap) would otherwise re-crop the file the
    # first one made: turned twice, cut twice. Phil, 2026-11-16.
    if data.get('source') != row['path']:
        return jsonify({'success': False, 'error': 'This image changed since the crop tool opened. Reload the page.'}), 409
    try:
        geom = cover_crop.parse_geometry(data.get('geometry'))
        with Image.open(os.path.join(image_utils.STATIC_ROOT, row['path'])) as img:
            img.load()
            upright = cover_crop._to_rgb(ImageOps.exif_transpose(img))
        new_path = image_utils.save_photo_image(cover_crop.render(upright, geom), book['id'])
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception:
        current_app.logger.exception('Cropping photo %s failed', photo_id)
        return jsonify({'success': False, 'error': "Couldn't crop that photo."}), 500
    conn.execute('UPDATE item_photos SET path = ? WHERE id = ? AND book_id = ?', (new_path, photo_id, book['id']))
    conn.commit()
    delete_image_file(row['path'], image_utils.STATIC_ROOT)
    return jsonify({'success': True, 'message': 'Photo cropped.',
                    'url': url_for('static', filename=new_path)})
