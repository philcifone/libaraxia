"""Placeholder faces (ROADMAP 16.0c, docs/FACES-SPEC.md; migration 041).

The admin's images for a face of an item that has no photo of it: a
clamshell's plastic top, an orange tape's bottom, a clear DVD shell's edge,
a page texture. Each is for one face kind (spine, side, top, bottom) of one
**medium** (books, vinyl, CDs, cassettes, DVDs, VHS: one tab each on the
admin page); named **sets** group a medium's placeholders (at most one per
face: "White clamshell", "Nickelodeon"). An owner picks placeholders per
item (`item_faces`), a set on the add form or the edit page, or one face
at a time on the edit page. Nothing is automatic: an item nobody picked
for keeps the plain look.

Which image a face shows, first that exists (spec section 5):
    the item's photo of that face
    a VHS sleeve's right side: its left side's photo (16.0a; a VHS with a
        top photo is a sleeve, spec section 6)
    the item's chosen placeholder
    nothing: the plain look in styles.css ("The 3D item", "Box faces")

Queries and rules only; files are saved by image_utils.save_photo (under
FACES_FOLDER) and removed by image_utils.delete_image_file. Routes are in
blueprints/faces.py.
"""
from flask import url_for

from utils import image_utils, photos
from utils.media import BOOK, VIDEO, RECORD, is_digital, media_type_of

KINDS = photos.EDGES        # the faces a placeholder can stand in for

# Mediums, in the admin page's tab order: (label, a media type and format
# that have it, for the face labels: a book's side is its "Fore-edge")
MEDIA = {
    'book': ('Books', BOOK, None),
    'vinyl': ('Vinyl', RECORD, 'LP'),
    'cd': ('CDs', RECORD, 'CD'),
    'cassette': ('Cassettes', RECORD, 'Cassette'),
    'dvd': ('DVDs', VIDEO, 'DVD'),
    'vhs': ('VHS', VIDEO, 'VHS'),
}
NAME_MAX = 60


class FaceError(ValueError):
    """A request the rules refuse; the message is safe to show."""


def medium_label(medium):
    return MEDIA[medium][0]


def kind_label(medium, kind):
    """A face's name for this medium: "Fore-edge" on a book, "Left side" on a VHS."""
    _, media_type, fmt = MEDIA[medium]
    return photos.label(kind, fmt, media_type)


def medium_for(media_type, fmt=None):
    """The medium whose placeholders an item may use; None for an audiobook
    or ebook, which has no box."""
    if media_type == BOOK:
        return None if is_digital(fmt) else 'book'
    if media_type == VIDEO:
        return 'vhs' if fmt == 'VHS' else 'dvd'
    if media_type == RECORD:
        return {'CD': 'cd', 'Cassette': 'cassette'}.get(fmt, 'vinyl')
    return None


def _clean_name(name):
    name = ' '.join((name or '').split())[:NAME_MAX]
    if not name:
        raise FaceError('Give it a name.')
    return name


def _url(row):
    return url_for('static', filename=row['path'])


# --- The library (admin) ------------------------------------------------------

def placeholder(conn, placeholder_id):
    return conn.execute('SELECT * FROM face_placeholders WHERE id = ?', (placeholder_id,)).fetchone()


def library(conn):
    """Everything the admin page shows, by medium in MEDIA's order:
    [{'medium', 'label', 'kinds': [{'kind', 'label', 'rows': [rows]}],
      'sets': [{'row', 'members': {kind: placeholder row}}]}]."""
    by_medium = {m: {kind: [] for kind in KINDS} for m in MEDIA}
    for row in conn.execute('SELECT * FROM face_placeholders ORDER BY name COLLATE NOCASE, id'):
        if row['medium'] in by_medium:
            by_medium[row['medium']][row['kind']].append(row)
    members = {}
    for row in conn.execute('SELECT m.set_id, m.kind, p.* FROM face_set_members m '
                            'JOIN face_placeholders p ON p.id = m.placeholder_id'):
        members.setdefault(row['set_id'], {})[row['kind']] = row
    sets = {m: [] for m in MEDIA}
    for row in conn.execute('SELECT * FROM face_sets ORDER BY name COLLATE NOCASE, id'):
        if row['medium'] in sets:
            sets[row['medium']].append({'row': row, 'members': members.get(row['id'], {})})
    return [{'medium': m, 'label': medium_label(m),
             'kinds': [{'kind': kind, 'label': kind_label(m, kind), 'rows': by_medium[m][kind]}
                       for kind in KINDS],
             'sets': sets[m]}
            for m in MEDIA]


def add_placeholder(conn, medium, kind, name, path):
    """Insert a placeholder (its file already saved). Returns its id. The
    caller commits."""
    if medium not in MEDIA or kind not in KINDS:
        raise FaceError('Unknown kind of placeholder.')
    return conn.execute('INSERT INTO face_placeholders (medium, kind, name, path) VALUES (?, ?, ?, ?)',
                        (medium, kind, _clean_name(name), path)).lastrowid


def rename_placeholder(conn, placeholder_id, name):
    conn.execute('UPDATE face_placeholders SET name = ? WHERE id = ?', (_clean_name(name), placeholder_id))


def replace_image(conn, placeholder_id, new_path):
    """Point a placeholder at a new file (a crop) and remove the old one.
    Every item using it shows the new image. The caller commits first."""
    old = placeholder(conn, placeholder_id)
    conn.execute('UPDATE face_placeholders SET path = ? WHERE id = ?', (new_path, placeholder_id))
    return old['path'] if old else None


def delete_placeholder(conn, placeholder_id):
    """Delete a placeholder's row; its set places and item choices go with
    it (CASCADE), so those faces fall back. Returns the file to remove once
    committed, or None."""
    row = placeholder(conn, placeholder_id)
    if not row:
        return None
    conn.execute('DELETE FROM face_placeholders WHERE id = ?', (placeholder_id,))
    return row['path']


def remove_file(path):
    if path:
        image_utils.delete_image_file(path, image_utils.STATIC_ROOT)


def face_set(conn, set_id):
    return conn.execute('SELECT * FROM face_sets WHERE id = ?', (set_id,)).fetchone()


def create_set(conn, medium, name):
    if medium not in MEDIA:
        raise FaceError('Unknown kind of set.')
    return conn.execute('INSERT INTO face_sets (medium, name) VALUES (?, ?)',
                        (medium, _clean_name(name))).lastrowid


def update_set(conn, set_id, name, members):
    """Rename a set and set its members ({kind: placeholder id or None}).
    Every member must be a placeholder of the set's medium and of that
    face. Items it was applied to keep the faces it gave them."""
    row = face_set(conn, set_id)
    if not row:
        raise FaceError('That set is gone.')
    conn.execute('UPDATE face_sets SET name = ? WHERE id = ?', (_clean_name(name), set_id))
    for kind in KINDS:
        pid = members.get(kind)
        conn.execute('DELETE FROM face_set_members WHERE set_id = ? AND kind = ?', (set_id, kind))
        if not pid:
            continue
        ph = placeholder(conn, pid)
        if not ph or ph['medium'] != row['medium'] or ph['kind'] != kind:
            raise FaceError("That placeholder doesn't fit this set.")
        conn.execute('INSERT INTO face_set_members (set_id, kind, placeholder_id) VALUES (?, ?, ?)',
                     (set_id, kind, pid))


def delete_set(conn, set_id):
    """Items that used the set keep their choices (a set fills them in once)."""
    conn.execute('DELETE FROM face_sets WHERE id = ?', (set_id,))


# --- On an item ---------------------------------------------------------------

def options_for(conn, item):
    """What the edit page offers an item: {'kinds': {kind: [placeholder rows
    of its medium]}, 'sets': [set rows with at least one member], 'chosen':
    {kind: placeholder row}}. Empty when it has no medium."""
    medium = medium_for(media_type_of(item), item['format'])
    out = {'kinds': {kind: [] for kind in KINDS}, 'sets': [], 'chosen': chosen(conn, item['id'])}
    if not medium:
        return out
    for row in conn.execute('SELECT * FROM face_placeholders WHERE medium = ? '
                            'ORDER BY name COLLATE NOCASE, id', (medium,)):
        out['kinds'][row['kind']].append(row)
    out['sets'] = conn.execute(
        'SELECT s.* FROM face_sets s WHERE s.medium = ? '
        'AND EXISTS (SELECT 1 FROM face_set_members m WHERE m.set_id = s.id) '
        'ORDER BY s.name COLLATE NOCASE, s.id', (medium,)).fetchall()
    return out


def chosen(conn, book_id):
    """{kind: placeholder row} an item's owner picked."""
    return {row['kind']: row for row in conn.execute(
        'SELECT f.kind, p.* FROM item_faces f JOIN face_placeholders p ON p.id = f.placeholder_id '
        'WHERE f.book_id = ?', (book_id,))}


def choose(conn, item, kind, placeholder_id):
    """Set (or with None, clear) the placeholder for one face of an item.
    It must be for that face and the item's medium."""
    if kind not in KINDS:
        raise FaceError('Unknown face.')
    conn.execute('DELETE FROM item_faces WHERE book_id = ? AND kind = ?', (item['id'], kind))
    if not placeholder_id:
        return
    ph = placeholder(conn, placeholder_id)
    if not ph or ph['kind'] != kind or ph['medium'] != medium_for(media_type_of(item), item['format']):
        raise FaceError("That placeholder doesn't fit this item.")
    conn.execute('INSERT INTO item_faces (book_id, kind, placeholder_id) VALUES (?, ?, ?)',
                 (item['id'], kind, placeholder_id))


def apply_set(conn, item, set_id):
    """Fill an item's choices from a set: each of the set's faces replaces
    the item's choice for that face; faces the set leaves out are kept."""
    row = face_set(conn, set_id)
    if not row or row['medium'] != medium_for(media_type_of(item), item['format']):
        raise FaceError("That set doesn't fit this item.")
    for member in conn.execute('SELECT kind, placeholder_id FROM face_set_members WHERE set_id = ?', (set_id,)):
        choose(conn, item, member['kind'], member['placeholder_id'])
    return row


def sets_for_type(conn, media_type):
    """The sets an add form offers before the format is known: every set,
    with members, of the mediums this media type has, by medium:
    [(medium label, [set rows])]."""
    mediums = [m for m, (_, mt, _f) in MEDIA.items() if mt == media_type]
    rows = conn.execute(
        'SELECT s.* FROM face_sets s WHERE EXISTS (SELECT 1 FROM face_set_members m WHERE m.set_id = s.id) '
        'ORDER BY s.name COLLATE NOCASE, s.id').fetchall()
    return [(medium_label(m), [r for r in rows if r['medium'] == m]) for m in mediums
            if any(r['medium'] == m for r in rows)]


def apply_on_add(conn, book_id, set_id):
    """The add form's set (`face_set`), applied once the item exists. A set
    that doesn't fit the format picked (a DVD set on a VHS) is skipped:
    returns False. The caller commits."""
    if not set_id:
        return True
    item = conn.execute('SELECT * FROM books WHERE id = ?', (book_id,)).fetchone()
    try:
        apply_set(conn, item, int(set_id))
        return True
    except (FaceError, ValueError):
        return False


def placeholder_urls(conn, item, item_photos, choices=None):
    """{kind: URL} of the placeholders an item's owner picked for faces it
    has no photo of (spec section 5, step 3); a VHS sleeve's right side is
    left to its left side's photo (step 2). `choices` may be passed in,
    read once for a page of items."""
    if not medium_for(media_type_of(item), item['format']):
        return {}
    if choices is None:
        choices = chosen(conn, item['id'])
    sleeve = item_photos.get(photos.TOP) and item_photos.get(photos.SPINE)
    out = {}
    for kind in KINDS:
        if item_photos.get(kind):
            continue
        if kind == photos.SIDE and item['format'] == 'VHS' and sleeve:
            continue
        row = choices.get(kind)
        if row and image_utils.upload_exists(row['path']):
            out[kind] = _url(row)
    return out
