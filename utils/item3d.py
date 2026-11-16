"""The 3D view of an item: which shape it is and whether it has the photos
for it (ROADMAP 16.0a; Shelf style only for now).

An item turns in 3D only when every printed face of its shape is a photo
(Phil, 2026-11-15: "no fake or placeholder text in 3D renderings"). Until
then its cover opens the gallery or the plain zoom. The one exception is a
CD's spine, a few millimetres of small type, which is drawn from the title
when there's no photo.

Shapes, by media type and format:

    book    a book: cover, back and spine; the other three sides are paper
    sleeve  vinyl (LP, EP, 7in, 10in, 12in): cover and back on a card
            sleeve a few millimetres thick
    jewel   a CD, in a jewel case or a card sleeve: the cover photo is the
            whole front, the hinge's bar and all (Phil, 2026-11-15: nothing
            drawn), the back the same size; the thickness from a spine
            photo (a thin card sleeve) or a jewel case's; the spines drawn
            from the title until there's a photo
    case    a DVD or a cassette: cover, back and spine, on black plastic
    tape    a VHS slip sleeve: cover, back and at least one long side
            (Phil, 2026-11-15); one side's photo does for both, a missing
            top is card in the cover's colour, and the open bottom is
            black, the tape inside. A double box is simply a wider spine
            photo: the thickness comes from it.

`model()` answers with everything the template needs (templates/_item3d.html):
the faces' URLs and the proportions, read from the photos themselves, so
the box is the shape of the thing photographed. Sizes are read from the
files' headers and remembered per file.
"""
import os
from functools import lru_cache

from flask import url_for
from PIL import Image

from utils import image_utils, photos
from utils.book_utils import on_shelf
from utils.media import BOOK, VIDEO, RECORD, media_type_of

BOOK_SHAPE, SLEEVE, JEWEL, CASE, TAPE = 'book', 'sleeve', 'jewel', 'case', 'tape'

# Photos (besides the cover) a shape must have before it turns. A tuple
# inside is "any one of these".
NEEDS = {
    BOOK_SHAPE: (photos.BACK, photos.SPINE),
    SLEEVE: (photos.BACK,),
    JEWEL: (photos.BACK,),
    CASE: (photos.BACK, photos.SPINE),
    TAPE: (photos.BACK, (photos.SPINE, photos.SIDE)),
}

# Thickness as a share of the height, where no spine photo gives it: a
# 12in sleeve is about 3 mm on 315; a jewel case 10.4 mm on 125
FIXED_DEPTH = {SLEEVE: 0.012, JEWEL: 0.083}


def shape_for(media_type, fmt=None):
    """The shape an item of this type and format is, or None (an
    audiobook has no box to turn)."""
    if media_type == BOOK:
        return None if fmt == 'Audiobook' else BOOK_SHAPE
    if media_type == VIDEO:
        return TAPE if fmt == 'VHS' else CASE
    if media_type == RECORD:
        if fmt == 'CD':
            return JEWEL
        return CASE if fmt == 'Cassette' else SLEEVE
    return None


@lru_cache(maxsize=4096)
def _size_at(full_path, mtime):
    with Image.open(full_path) as img:
        return img.size


def _aspect(path):
    """Width over height of an upload, or None if it can't be read. The
    file's mtime is part of the memo's key, so a replaced file is re-read."""
    try:
        full = os.path.join(image_utils.STATIC_ROOT, path)
        w, h = _size_at(full, os.stat(full).st_mtime_ns)
        return w / h if w and h else None
    except Exception:
        return None


def missing(item, item_photos):
    """Labels of what this item still needs before it turns in 3D ("Back",
    "Spine"), cover first; [] when it's ready or has no shape at all."""
    fmt = item['format']
    shape = shape_for(media_type_of(item), fmt)
    if not shape:
        return []
    out = [] if image_utils.upload_exists(item['cover_image_url']) else ['Cover']
    for need in NEEDS[shape]:
        choices = need if isinstance(need, tuple) else (need,)
        if not any(item_photos[kind] for kind in choices):
            out.append(' or '.join(photos.label(kind, fmt) for kind in choices))
    return out


def model(item, item_photos):
    """What templates/_item3d.html draws, or None when the item isn't ready.

    {'shape', 'faces': {'front', 'back', 'spine', 'side', 'top'} (URLs; a
    face without one is plain), 'aspect' (the box's width over its height),
    'depth' (thickness over height), 'title', 'author'}.
    """
    fmt = item['format']
    shape = shape_for(media_type_of(item), fmt)
    if not shape or missing(item, item_photos):
        return None
    aspect = _aspect(item['cover_image_url'])
    if not aspect:
        return None
    faces = {'front': url_for('static', filename=item['cover_image_url'])}
    for kind in photos.SINGLE:
        if item_photos[kind] and kind in photos.kinds_for(media_type_of(item), fmt):
            faces[kind] = url_for('static', filename=item_photos[kind]['path'])
    if shape == TAPE:
        # One long side's photo does for the other (most sleeves print
        # both alike); the thickness comes from whichever there is
        faces.setdefault('spine', faces.get('side'))
        faces.setdefault('side', faces['spine'])
    # The spine photo's own shape gives the thickness (its width over its
    # height); a sleeve, and a CD without a spine photo, have a fixed one
    edge = item_photos[photos.SPINE] or item_photos[photos.SIDE]
    depth = FIXED_DEPTH.get(shape) if shape == SLEEVE or not edge else None
    if depth is None:
        depth = _aspect(edge['path']) or 0.08
    return {
        'shape': shape, 'faces': faces,
        'aspect': round(aspect, 4), 'depth': round(min(0.6, max(0.008, depth)), 4),
        'title': item['title'], 'author': item['author'],
    }


# --- Books standing on the Shelves heading (ROADMAP 16.0a) -------------------

HEADING_BOOKS = 10      # at most: five each side of the title, which a phone has room for


def heading_books(conn, user_id, seed):
    """Up to HEADING_BOOKS models of the user's own books that turn in 3D,
    for the Shelves heading's ledge (Shelf style, their own Shelves page
    only; drawn still, upright with spines out, by templates/_icons.html
    page_heading).

    `seed` is drawn at login (session['heading_seed']), so the choice
    stays put for a visit and changes with the next. Each book's place in
    the order comes from the seed and its own id, not from a shuffle of
    the list: a book that gets its photos joins the ones standing there
    without moving them.
    """
    import random
    rows = conn.execute(f"""
        SELECT b.* FROM library_books b
        WHERE b.added_by = ? AND {on_shelf('b')}
          AND b.cover_image_url IS NOT NULL
          AND (b.format IS NULL OR b.format <> 'Audiobook')
          AND (SELECT COUNT(*) FROM item_photos p
               WHERE p.book_id = b.id AND p.kind IN ('back', 'spine')) = 2
    """, (user_id,)).fetchall()
    rows.sort(key=lambda b: random.Random(f"{seed}:{b['id']}").random())
    out = []
    for book in rows:
        m = model(book, photos.photos_of(conn, book['id']))
        if m:
            out.append(m)
            if len(out) == HEADING_BOOKS:
                break
    return out
