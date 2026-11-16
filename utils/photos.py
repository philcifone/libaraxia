"""Item photos beyond the cover: a back, every side and a gallery (ROADMAP 16.0a, 16.0c;
docs/PHOTOS-VALUE-SPEC.md section 3, docs/FACES-SPEC.md; migrations 036, 040, 041).

Queries only; the files are saved by image_utils.save_photo and removed by
image_utils.delete_image_file. Routes are in blueprints/photos.py; the item
page's gallery and the edit page's Photos section read `photos_of`. What
the 3D view needs of them is utils/item3d.py.
"""
from flask import url_for

from utils import image_utils
from utils.media import BOOK

# The photo_kinds table (migrations 040, 041; a test keeps the two in
# step), in the gallery's order. SPINE is the left side, as a book in the
# hand; SIDE is the right; TOP and BOTTOM the ends (16.0c: every type takes
# every face, docs/FACES-SPEC.md section 2).
BACK, SPINE, SIDE, TOP, BOTTOM, GALLERY = 'back', 'spine', 'side', 'top', 'bottom', 'gallery'
KINDS = (BACK, SPINE, SIDE, TOP, BOTTOM, GALLERY)
SINGLE = (BACK, SPINE, SIDE, TOP, BOTTOM)   # one per item; adding another replaces it
EDGES = (SPINE, SIDE, TOP, BOTTOM)          # the faces a placeholder can stand in for (16.0c)
MAX_PER_ITEM = 30               # enough for a box set; stops a runaway upload
LABELS = {BACK: 'Back', SPINE: 'Spine', SIDE: 'Right side', TOP: 'Top', BOTTOM: 'Bottom', GALLERY: 'Photo'}
# A book's right side and ends are its pages
BOOK_LABELS = {SIDE: 'Fore-edge', TOP: 'Top edge', BOTTOM: 'Bottom edge'}


def kinds_for(media_type, fmt=None):
    """The kinds an item takes, in the edit page's order: every face and the
    gallery, whatever its type (Phil, 2026-11-15: "something interesting in
    the paper" of a book, a gatefold's printed spine, a tape's bottom)."""
    return KINDS


def label(kind, fmt=None, media_type=None):
    """What the UI calls a kind: a book's right side and ends are its
    pages ("Fore-edge"); on a VHS the spine is the "Left side", since it
    has a right one too."""
    if media_type == BOOK and fmt != 'Audiobook' and kind in BOOK_LABELS:
        return BOOK_LABELS[kind]
    if kind == SPINE and fmt == 'VHS':
        return 'Left side'
    return LABELS[kind]


def as_dict(row):
    return {'id': row['id'], 'kind': row['kind'], 'caption': row['caption'] or '',
            'url': url_for('static', filename=row['path'])}


def photos_of(conn, book_id):
    """{'back': row or None, 'spine': row or None, 'gallery': [rows]},
    gallery in upload order. Rows whose file is gone are left out, so a
    missing file never shows as a broken image."""
    out = {**{kind: None for kind in SINGLE}, GALLERY: []}
    for row in conn.execute('SELECT * FROM item_photos WHERE book_id = ? ORDER BY position, id',
                            (book_id,)):
        if not image_utils.upload_exists(row['path']):
            continue
        if row['kind'] == GALLERY:
            out[GALLERY].append(row)
        else:
            out[row['kind']] = row
    return out


def slides(photos, cover_url=None, fmt=None, media_type=None):
    """The item page's gallery order: cover, back, sides, top, gallery.
    Each a dict with url, caption and a label ("Back") for the alt text."""
    out = []
    if cover_url:
        out.append({'url': cover_url, 'caption': '', 'label': 'Cover'})
    for kind in SINGLE:
        if photos[kind]:
            out.append({**as_dict(photos[kind]), 'label': label(kind, fmt, media_type)})
    for row in photos[GALLERY]:
        out.append({**as_dict(row), 'label': LABELS[GALLERY]})
    return out


def count(conn, book_id):
    return conn.execute('SELECT COUNT(*) FROM item_photos WHERE book_id = ?', (book_id,)).fetchone()[0]


def add(conn, book_id, kind, path, caption=None):
    """Insert a photo row; for a single kind (a back, a spine), the old one (row and file) is
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


def box_faces(conn, rows):
    """The Shelf style's flat cover box with an item's top and right side
    photos on its faces (Phil, 2026-11-15; a VHS first, every type since
    16.0c): {book_id: style}, where style sets --face-top / --face-side to
    the photos' URLs, for the items among `rows` that have either. One
    query per page of items; the item page, the library grids and their
    infinite scroll (book_utils.card_json) use it (styles.css "Box faces")."""
    ids = [r['id'] for r in rows]
    if not ids:
        return {}
    marks = ','.join('?' * len(ids))
    out = {}
    for row in conn.execute(f"SELECT book_id, kind, path FROM item_photos "
                            f"WHERE kind IN ('{TOP}', '{SIDE}') AND book_id IN ({marks})", ids):
        if image_utils.upload_exists(row['path']):
            url = url_for('static', filename=row['path'])
            out[row['book_id']] = out.get(row['book_id'], '') + f'--face-{row["kind"]}: url("{url}"); '
    return out
