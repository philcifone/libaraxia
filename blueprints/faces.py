"""Placeholder faces (ROADMAP 16.0c, docs/FACES-SPEC.md; utils/faces.py).

Admin -> Placeholders (/faces/admin): the library of placeholder images by
body and face, uploaded and cropped with the cover's crop tool, and the
named sets that group them. Admins only.

On an item's edit page (_photos_edit.html): its owner or an admin picks a
placeholder for a face, or fills its faces from a set. Plain form posts that
come back to the Photos section, as blueprints/photos.py's do.
"""
from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from models import admin_required
from utils import cover_crop, faces, image_utils
from utils.database import get_db
from utils.image_utils import PhotoError, save_photo, is_safe_upload_path
from utils.rate_limiting import limiter
from blueprints.photos import _item_for_owner, _done

faces_blueprint = Blueprint('faces', __name__)


def _back(body=None):
    """The admin page, at the body's section."""
    return redirect(url_for('faces.admin', _anchor=f'body-{body}' if body in faces.BODIES else None))


@faces_blueprint.route('/admin')
@login_required
@admin_required
def admin():
    return render_template('admin/faces.html', library=faces.library(get_db()))


@faces_blueprint.route('/admin/add', methods=['POST'])
@login_required
@admin_required
@limiter.limit('120 per hour')
def add():
    """Upload a placeholder: body, kind, name and the file (`photo`)."""
    conn = get_db()
    body, kind = request.form.get('body'), request.form.get('kind')
    if body not in faces.BODIES or kind not in faces.KINDS:
        abort(400)
    file = request.files.get('photo')
    if not file or not file.filename:
        flash('Choose an image first.', 'error')
        return _back(body)
    try:
        name = faces._clean_name(request.form.get('name') or faces.kind_label(body, kind))
        path = save_photo(file, None, folder=image_utils.FACES_FOLDER)
    except (PhotoError, faces.FaceError) as e:
        flash(str(e), 'error')
        return _back(body)
    try:
        faces.add_placeholder(conn, body, kind, name, path)
        conn.commit()
    except Exception:
        conn.rollback()
        faces.remove_file(path)
        current_app.logger.exception('Saving placeholder face')
        flash("Couldn't save that placeholder.", 'error')
        return _back(body)
    current_app.logger.info('Admin %s added a %s %s placeholder', current_user.id, body, kind)
    flash(f'{faces.body_label(body)}: "{name}" added. Crop it if it needs straightening.', 'success')
    return _back(body)


def _placeholder_or_404(conn, placeholder_id):
    row = faces.placeholder(conn, placeholder_id)
    if not row:
        abort(404)
    return row


@faces_blueprint.route('/admin/<int:placeholder_id>/rename', methods=['POST'])
@login_required
@admin_required
def rename(placeholder_id):
    conn = get_db()
    row = _placeholder_or_404(conn, placeholder_id)
    try:
        faces.rename_placeholder(conn, placeholder_id, request.form.get('name'))
        conn.commit()
        flash('Renamed.', 'success')
    except faces.FaceError as e:
        flash(str(e), 'error')
    return _back(row['body'])


@faces_blueprint.route('/admin/<int:placeholder_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete(placeholder_id):
    conn = get_db()
    row = _placeholder_or_404(conn, placeholder_id)
    path = faces.delete_placeholder(conn, placeholder_id)
    conn.commit()
    faces.remove_file(path)
    current_app.logger.info('Admin %s deleted placeholder %s', current_user.id, placeholder_id)
    flash(f'"{row["name"]}" deleted. Items that used it show their default again.', 'success')
    return _back(row['body'])


@faces_blueprint.route('/admin/<int:placeholder_id>/crop', methods=['POST'])
@login_required
@admin_required
@limiter.limit('120 per hour')
def crop(placeholder_id):
    """Crop or straighten a placeholder with the crop tool (cover_crop.js
    photo mode, as blueprints/photos.crop): saved as a new file, the old
    one removed, and every item using it shows the new one."""
    import os
    from PIL import Image, ImageOps
    conn = get_db()
    row = _placeholder_or_404(conn, placeholder_id)
    if not is_safe_upload_path(row['path']):
        abort(404)
    data = request.get_json(silent=True) or {}
    try:
        geom = cover_crop.parse_geometry(data.get('geometry'))
        with Image.open(os.path.join(image_utils.STATIC_ROOT, row['path'])) as img:
            img.load()
            upright = cover_crop._to_rgb(ImageOps.exif_transpose(img))
        new_path = image_utils.save_photo_image(cover_crop.render(upright, geom), None,
                                                folder=image_utils.FACES_FOLDER)
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception:
        current_app.logger.exception('Cropping placeholder %s failed', placeholder_id)
        return jsonify({'success': False, 'error': "Couldn't crop that image."}), 500
    old = faces.replace_image(conn, placeholder_id, new_path)
    conn.commit()
    faces.remove_file(old)
    return jsonify({'success': True, 'message': 'Placeholder cropped.',
                    'url': url_for('static', filename=new_path)})


@faces_blueprint.route('/admin/sets/add', methods=['POST'])
@login_required
@admin_required
def add_set():
    conn = get_db()
    body = request.form.get('body')
    try:
        faces.create_set(conn, body, request.form.get('name'))
        conn.commit()
        flash('Set added: pick its faces below.', 'success')
    except faces.FaceError as e:
        flash(str(e), 'error')
    return _back(body)


@faces_blueprint.route('/admin/sets/<int:set_id>/update', methods=['POST'])
@login_required
@admin_required
def update_set(set_id):
    """Name, members (face_<kind> = placeholder id or empty) and default."""
    conn = get_db()
    row = faces.face_set(conn, set_id)
    if not row:
        abort(404)
    members = {}
    for kind in faces.KINDS:
        value = request.form.get(f'face_{kind}') or ''
        members[kind] = int(value) if value.isdigit() else None
    try:
        faces.update_set(conn, set_id, request.form.get('name'), members,
                         request.form.get('is_default') == '1')
        conn.commit()
        flash(f'"{faces.face_set(conn, set_id)["name"]}" saved.', 'success')
    except faces.FaceError as e:
        conn.rollback()
        flash(str(e), 'error')
    return _back(row['body'])


@faces_blueprint.route('/admin/sets/<int:set_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_set(set_id):
    conn = get_db()
    row = faces.face_set(conn, set_id)
    if not row:
        abort(404)
    faces.delete_set(conn, set_id)
    conn.commit()
    flash(f'"{row["name"]}" deleted. Items it filled in keep their faces.', 'success')
    return _back(row['body'])


# --- On an item: its owner or an admin -----------------------------------------

def _item(conn, book_id):
    """The item with the columns faces needs, by photos' owner rule."""
    _item_for_owner(conn, book_id)
    return conn.execute('SELECT * FROM books WHERE id = ?', (book_id,)).fetchone()


@faces_blueprint.route('/item/<int:book_id>/choose', methods=['POST'])
@login_required
def choose(book_id):
    """One face's placeholder: kind, placeholder_id (empty: the default)."""
    conn = get_db()
    item = _item(conn, book_id)
    kind = request.form.get('kind')
    value = request.form.get('placeholder_id') or ''
    try:
        faces.choose(conn, item, kind, int(value) if value.isdigit() else None)
        conn.commit()
    except faces.FaceError as e:
        conn.rollback()
        return _done(item, str(e), ok=False, status=400)
    return _done(item, 'Placeholder saved.' if value else 'Back to the default.')


@faces_blueprint.route('/item/<int:book_id>/set', methods=['POST'])
@login_required
def apply_set(book_id):
    """Fill an item's faces from a set (set_id)."""
    conn = get_db()
    item = _item(conn, book_id)
    value = request.form.get('set_id') or ''
    try:
        row = faces.apply_set(conn, item, int(value) if value.isdigit() else 0)
        conn.commit()
    except faces.FaceError as e:
        conn.rollback()
        return _done(item, str(e), ok=False, status=400)
    return _done(item, f'{row["name"]}: its faces are on this item now.')
