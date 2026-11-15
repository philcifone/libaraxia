"""Item photos beyond the cover: a back, a spine (books only) and a gallery
(ROADMAP 16.0a, docs/PHOTOS-VALUE-SPEC.md section 3, migration 036).

Queries only; the files are saved by image_utils.save_photo and removed by
image_utils.delete_image_file. Routes are in blueprints/photos.py; the item
page's gallery and the edit page's Photos section read `photos_of`.
"""
from flask import url_for

from utils import image_utils
from utils.media import BOOK

BACK, SPINE, GALLERY = 'back', 'spine', 'gallery'
KINDS = (BACK, SPINE, GALLERY)
SINGLE = (BACK, SPINE)          # one per item; adding another replaces it
MAX_PER_ITEM = 30               # enough for a box set; stops a runaway upload
LABELS = {BACK: 'Back', SPINE: 'Spine', GALLERY: 'Photo'}


def kinds_for(media_type):
    """The kinds an item of this type takes: a spine is books only."""
    return KINDS if media_type == BOOK else (BACK, GALLERY)


def as_dict(row):
    return {'id': row['id'], 'kind': row['kind'], 'caption': row['caption'] or '',
            'url': url_for('static', filename=row['path'])}


def photos_of(conn, book_id):
    """{'back': row or None, 'spine': row or None, 'gallery': [rows]},
    gallery in upload order. Rows whose file is gone are left out, so a
    missing file never shows as a broken image."""
    out = {BACK: None, SPINE: None, GALLERY: []}
    for row in conn.execute('SELECT * FROM item_photos WHERE book_id = ? ORDER BY position, id',
                            (book_id,)):
        if not image_utils.upload_exists(row['path']):
            continue
        if row['kind'] == GALLERY:
            out[GALLERY].append(row)
        else:
            out[row['kind']] = row
    return out


def slides(photos, cover_url=None):
    """The item page's "More photos" order: cover, back, spine, gallery.
    Each a dict with url, caption and a label ("Back") for the alt text."""
    out = []
    if cover_url:
        out.append({'url': cover_url, 'caption': '', 'label': 'Cover'})
    for kind in SINGLE:
        if photos[kind]:
            out.append({**as_dict(photos[kind]), 'label': LABELS[kind]})
    for row in photos[GALLERY]:
        out.append({**as_dict(row), 'label': LABELS[GALLERY]})
    return out


def count(conn, book_id):
    return conn.execute('SELECT COUNT(*) FROM item_photos WHERE book_id = ?', (book_id,)).fetchone()[0]


def add(conn, book_id, kind, path, caption=None):
    """Insert a photo row; for a back or spine, the old one (row and file) is
    replaced. Returns the new row id. The caller commits."""
    if kind in SINGLE:
        old = conn.execute('SELECT id, path FROM item_photos WHERE book_id = ? AND kind = ?',
                           (book_id, kind)).fetchone()
        if old:
            conn.execute('DELETE FROM item_photos WHERE id = ?', (old['id'],))
            image_utils.delete_image_file(old['path'], image_utils.STATIC_ROOT)
    position = conn.execute('SELECT COALESCE(MAX(position), -1) + 1 FROM item_photos WHERE book_id = ?',
                            (book_id,)).fetchone()[0]
    return conn.execute(
        'INSERT INTO item_photos (book_id, kind, path, caption, position) VALUES (?, ?, ?, ?, ?)',
        (book_id, kind, path, caption or None, position)).lastrowid


def delete(conn, photo_id, book_id):
    """Delete one photo, its row and then its file. The caller commits."""
    row = conn.execute('SELECT path FROM item_photos WHERE id = ? AND book_id = ?',
                       (photo_id, book_id)).fetchone()
    if not row:
        return False
    conn.execute('DELETE FROM item_photos WHERE id = ? AND book_id = ?', (photo_id, book_id))
    image_utils.delete_image_file(row['path'], image_utils.STATIC_ROOT)
    return True
