"""Placeholder faces (ROADMAP 16.0c, docs/FACES-SPEC.md; migration 041).

The admin's images for a face of an item that has no photo of it: a
clamshell's plastic top, an orange tape's bottom, a clear DVD shell's edge,
a page texture. Each is for one face kind (spine, side, top, bottom) of one
**body**, the kind of thing it belongs to; named **sets** group a body's
placeholders (at most one per face), and one set per body may be its
default. An owner picks placeholders per item (`item_faces`), one face at a
time or a set at once.

Which image a face shows, first that exists (spec section 5):
    the item's photo of that face
    a VHS sleeve's right side: its left side's photo (16.0a)
    the item's chosen placeholder
    the default set of the item's body
    nothing: the plain look in styles.css ("The 3D item", "Box faces")

A VHS is a sleeve when it has a top photo and a clamshell otherwise
(spec section 6), so its body, and the default set it falls back on,
follow from its photos.

Queries and rules only; files are saved by image_utils.save_photo (under
FACES_FOLDER) and removed by image_utils.delete_image_file. Routes are in
blueprints/faces.py.
"""
from flask import url_for

from utils import image_utils, photos
from utils.media import BOOK, VIDEO, RECORD, AUDIOBOOK, media_type_of

KINDS = photos.EDGES        # the faces a placeholder can stand in for

# Bodies, in the admin page's order: (label, a media type and format that
# have it, for the face labels: a book's side is its "Fore-edge")
BODIES = {
    'book': ('Books', BOOK, None),
    'vinyl': ('Vinyl', RECORD, 'LP'),
    'cd': ('CDs', RECORD, 'CD'),
    'cassette': ('Cassettes', RECORD, 'Cassette'),
    'dvd': ('DVDs', VIDEO, 'DVD'),
    'vhs_sleeve': ('VHS sleeves', VIDEO, 'VHS'),
    'vhs_clamshell': ('VHS clamshells', VIDEO, 'VHS'),
}
VHS_SLEEVE, VHS_CLAMSHELL = 'vhs_sleeve', 'vhs_clamshell'
NAME_MAX = 60


class FaceError(ValueError):
    """A request the rules refuse; the message is safe to show."""


def body_label(body):
    return BODIES[body][0]


def kind_label(body, kind):
    """A face's name for this body: "Fore-edge" on a book, "Left side" on a VHS."""
    _, media_type, fmt = BODIES[body]
    return photos.label(kind, fmt, media_type)


def bodies_for(media_type, fmt=None):
    """The bodies whose placeholders an item may use: a VHS may be a sleeve
    or a clamshell, so it gets both; an audiobook has no box."""
    if media_type == BOOK:
        return () if fmt == AUDIOBOOK else ('book',)
    if media_type == VIDEO:
        return (VHS_SLEEVE, VHS_CLAMSHELL) if fmt == 'VHS' else ('dvd',)
    if media_type == RECORD:
        return {'CD': ('cd',), 'Cassette': ('cassette',)}.get(fmt, ('vinyl',))
    return ()


def body_of(item, item_photos):
    """The one body an item is now, whose default set it falls back on: a
    VHS is a sleeve once it has a top photo, a clamshell until then."""
    bodies = bodies_for(media_type_of(item), item['format'])
    if not bodies:
        return None
    if bodies == (VHS_SLEEVE, VHS_CLAMSHELL):
        return VHS_SLEEVE if item_photos.get(photos.TOP) else VHS_CLAMSHELL
    return bodies[0]


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
    """Everything the admin page shows, by body in BODIES' order:
    [{'body', 'label', 'kinds': [{'kind', 'label', 'rows': [rows]}],
      'sets': [{'row', 'members': {kind: placeholder row}}]}]."""
    by_body = {body: {kind: [] for kind in KINDS} for body in BODIES}
    for row in conn.execute('SELECT * FROM face_placeholders ORDER BY name COLLATE NOCASE, id'):
        if row['body'] in by_body:
            by_body[row['body']][row['kind']].append(row)
    sets = {body: [] for body in BODIES}
    members = {}
    for row in conn.execute('SELECT m.set_id, m.kind, p.* FROM face_set_members m '
                            'JOIN face_placeholders p ON p.id = m.placeholder_id'):
        members.setdefault(row['set_id'], {})[row['kind']] = row
    for row in conn.execute('SELECT * FROM face_sets ORDER BY name COLLATE NOCASE, id'):
        if row['body'] in sets:
            sets[row['body']].append({'row': row, 'members': members.get(row['id'], {})})
    return [{'body': body, 'label': body_label(body),
             'kinds': [{'kind': kind, 'label': kind_label(body, kind), 'rows': by_body[body][kind]}
                       for kind in KINDS],
             'sets': sets[body]}
            for body in BODIES]


def add_placeholder(conn, body, kind, name, path):
    """Insert a placeholder (its file already saved). Returns its id. The
    caller commits."""
    if body not in BODIES or kind not in KINDS:
        raise FaceError('Unknown kind of placeholder.')
    return conn.execute('INSERT INTO face_placeholders (body, kind, name, path) VALUES (?, ?, ?, ?)',
                        (body, kind, _clean_name(name), path)).lastrowid


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


def create_set(conn, body, name):
    if body not in BODIES:
        raise FaceError('Unknown kind of set.')
    return conn.execute('INSERT INTO face_sets (body, name) VALUES (?, ?)',
                        (body, _clean_name(name))).lastrowid


def update_set(conn, set_id, name, members, is_default):
    """Rename a set, set its members ({kind: placeholder id or None}) and
    whether it's its body's default (taking that from any other set). Every
    member must be a placeholder of the set's body and of that face."""
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
        if not ph or ph['body'] != row['body'] or ph['kind'] != kind:
            raise FaceError("That placeholder doesn't fit this set.")
        conn.execute('INSERT INTO face_set_members (set_id, kind, placeholder_id) VALUES (?, ?, ?)',
                     (set_id, kind, pid))
    if is_default:
        conn.execute('UPDATE face_sets SET is_default = 0 WHERE body = ? AND id <> ?', (row['body'], set_id))
    conn.execute('UPDATE face_sets SET is_default = ? WHERE id = ?', (1 if is_default else 0, set_id))


def delete_set(conn, set_id):
    """Items that used the set keep their choices (a set fills them in once)."""
    conn.execute('DELETE FROM face_sets WHERE id = ?', (set_id,))


# --- On an item ---------------------------------------------------------------

def options_for(conn, item):
    """What the edit page offers an item: {'kinds': {kind: [placeholder rows
    of its bodies]}, 'sets': [set rows with at least one member], 'chosen':
    {kind: placeholder row}}. Empty when it has no body."""
    bodies = bodies_for(media_type_of(item), item['format'])
    out = {'kinds': {kind: [] for kind in KINDS}, 'sets': [], 'chosen': chosen(conn, item['id'])}
    if not bodies:
        return out
    marks = ','.join('?' * len(bodies))
    for row in conn.execute(f'SELECT * FROM face_placeholders WHERE body IN ({marks}) '
                            f'ORDER BY body, name COLLATE NOCASE, id', bodies):
        out['kinds'][row['kind']].append(row)
    out['sets'] = conn.execute(
        f'SELECT s.* FROM face_sets s WHERE s.body IN ({marks}) '
        f'AND EXISTS (SELECT 1 FROM face_set_members m WHERE m.set_id = s.id) '
        f'ORDER BY s.body, s.name COLLATE NOCASE, s.id', bodies).fetchall()
    return out


def chosen(conn, book_id):
    """{kind: placeholder row} an item's owner picked."""
    return {row['kind']: row for row in conn.execute(
        'SELECT f.kind, p.* FROM item_faces f JOIN face_placeholders p ON p.id = f.placeholder_id '
        'WHERE f.book_id = ?', (book_id,))}


def choose(conn, item, kind, placeholder_id):
    """Set (or with None, clear) the placeholder for one face of an item.
    It must be for that face and one of the item's bodies."""
    if kind not in KINDS:
        raise FaceError('Unknown face.')
    conn.execute('DELETE FROM item_faces WHERE book_id = ? AND kind = ?', (item['id'], kind))
    if not placeholder_id:
        return
    ph = placeholder(conn, placeholder_id)
    if not ph or ph['kind'] != kind or ph['body'] not in bodies_for(media_type_of(item), item['format']):
        raise FaceError("That placeholder doesn't fit this item.")
    conn.execute('INSERT INTO item_faces (book_id, kind, placeholder_id) VALUES (?, ?, ?)',
                 (item['id'], kind, placeholder_id))


def apply_set(conn, item, set_id):
    """Fill an item's choices from a set: each of the set's faces replaces
    the item's choice for that face; faces the set leaves out are kept."""
    row = face_set(conn, set_id)
    if not row or row['body'] not in bodies_for(media_type_of(item), item['format']):
        raise FaceError("That set doesn't fit this item.")
    for member in conn.execute('SELECT kind, placeholder_id FROM face_set_members WHERE set_id = ?', (set_id,)):
        choose(conn, item, member['kind'], member['placeholder_id'])
    return row


def sets_for_type(conn, media_type):
    """The sets an add form offers before the format is known: every set,
    with members, of the bodies this media type has, by body:
    [(body label, [set rows])]."""
    bodies = [b for b, (_, mt, _f) in BODIES.items() if mt == media_type]
    rows = conn.execute(
        'SELECT s.* FROM face_sets s WHERE EXISTS (SELECT 1 FROM face_set_members m WHERE m.set_id = s.id) '
        'ORDER BY s.name COLLATE NOCASE, s.id').fetchall()
    return [(body_label(b), [r for r in rows if r['body'] == b]) for b in bodies
            if any(r['body'] == b for r in rows)]


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


def defaults(conn):
    """{body: {kind: placeholder row}} from each body's default set."""
    out = {}
    for row in conn.execute('SELECT s.body, m.kind, p.* FROM face_sets s '
                            'JOIN face_set_members m ON m.set_id = s.id '
                            'JOIN face_placeholders p ON p.id = m.placeholder_id '
                            'WHERE s.is_default = 1'):
        out.setdefault(row['body'], {})[row['kind']] = row
    return out


def placeholder_urls(conn, item, item_photos, default_sets=None, choices=None):
    """{kind: URL} of the placeholders an item's faces show where it has no
    photo of that face (spec section 5, steps 3 and 4); a VHS sleeve's right
    side is left to its left side's photo (step 2). `default_sets` and
    `choices` may be passed in, read once for a page of items."""
    body = body_of(item, item_photos)
    if not body:
        return {}
    if choices is None:
        choices = chosen(conn, item['id'])
    if default_sets is None:
        default_sets = defaults(conn)
    fallback = default_sets.get(body, {})
    out = {}
    for kind in KINDS:
        if item_photos.get(kind):
            continue
        if (kind == photos.SIDE and body == VHS_SLEEVE and item_photos.get(photos.SPINE)):
            continue
        row = choices.get(kind) or fallback.get(kind)
        if row and image_utils.upload_exists(row['path']):
            out[kind] = _url(row)
    return out
