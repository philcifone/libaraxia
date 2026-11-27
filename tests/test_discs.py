"""A bare disc (Phil, 2026-11-26): a DVD or CD kept without its case. Its
cover is cut out with the crop tool's Disc shape (or, with no cover photo,
a picked Disc front stands in), so it draws no box in Shelf and turns in 3D
as a round disc, front and back. The admin's placeholders gain a Disc front
and Disc back on the DVD and CD tabs (migration 049)."""
import io
import re

from PIL import Image, ImageDraw

from conftest import login, scalar
from test_faces import add_placeholder, placeholder_id
from test_photos import add_item, box_of, jpeg_bytes, real_cover, upload


def disc_png(size=400):
    """A disc as the crop tool cuts one: see-through corners and spindle hole."""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((0, 0, size - 1, size - 1), fill=(200, 40, 40, 255))
    hole = size * 15 / 240
    draw.ellipse((size / 2 - hole, size / 2 - hole, size / 2 + hole, size / 2 + hole), fill=(0, 0, 0, 0))
    out = io.BytesIO()
    img.save(out, 'PNG')
    out.seek(0)
    return out


def disc_cover(static_root, name='disc.png'):
    (static_root / 'uploads').mkdir(exist_ok=True)
    (static_root / 'uploads' / name).write_bytes(disc_png().getvalue())
    return f'uploads/{name}'


def add_disc_placeholder(client, medium, kind, name):
    return client.post('/faces/admin/add', data={'medium': medium, 'kind': kind, 'name': name,
                                                 'photo': (disc_png(), 'd.png')},
                       content_type='multipart/form-data')


def cards_for(app, db, user, ids):
    """Infinite scroll's cards (book_utils.card_json) for these items."""
    from utils.book_utils import card_json
    rows = db.execute(f"SELECT * FROM books WHERE id IN ({','.join('?' * len(ids))})", ids).fetchall()
    with app.test_request_context():
        return card_json(db, user, rows, user)


def card_of(html, fmt):
    """The grid card's cover box (or placeholder) for an item of this format."""
    return re.search(rf'<div class="book-item group" data-format="{fmt}">.*?'
                     r'(<(?:span|div) class="(?:cover-box|no-cover)[^>]*>)', html, re.S).group(1)


def test_is_disc_reads_the_corners(app, static_root):
    from utils import image_utils
    with app.app_context():
        assert image_utils.is_disc(disc_cover(static_root))
        assert not image_utils.is_disc(real_cover(static_root))         # a plain photo
        # see-through, but not cut round: a corner is opaque
        img = Image.new('RGBA', (100, 100), (0, 0, 0, 0))
        ImageDraw.Draw(img).rectangle((0, 0, 50, 50), fill=(9, 9, 9, 255))
        img.save(static_root / 'uploads' / 'half.png')
        assert not image_utils.is_disc('uploads/half.png')
        assert not image_utils.is_disc('uploads/gone.png')               # no file
        assert not image_utils.is_disc('../etc/passwd')                  # not an upload


def test_a_disc_cover_draws_no_box_and_turns_as_a_disc(client, app, db, people, static_root):
    """On the grid, the item page and infinite scroll the cover box says it's
    a disc (the Shelf CSS draws no box); a cased DVD doesn't. In 3D it needs
    the back of the disc, then turns round and thin, with no Spine button."""
    login(client, 'bob')
    dvd = add_item(db, people['bob'], 'video', 'DVD', disc_cover(static_root))
    cased = add_item(db, people['bob'], 'video', 'Blu-ray', real_cover(static_root))
    grid = client.get('/videos/').get_data(as_text=True)
    assert 'data-shape="disc"' in card_of(grid, 'DVD')
    assert 'data-shape' not in card_of(grid, 'Blu-ray')
    cards = {c['id']: c for c in cards_for(app, db, people['bob'], (dvd, cased))}
    assert cards[dvd]['shape'] == 'disc' and cards[cased]['shape'] == ''

    page = client.get(f'/videos/{dvd}').get_data(as_text=True)
    stand = re.search(r'class="cover-stand.*?(<span class="cover-box[^>]*>)', page, re.S).group(1)
    assert 'data-shape="disc"' in stand
    assert 'item-3d' not in page                                         # no back yet
    edit = client.get(f'/videos/edit/{dvd}').get_data(as_text=True)
    assert 'still needs: back of the disc' in edit
    # a disc's photos card offers its back only, by that name
    photos = edit[edit.index('id="photos"'):]
    assert 'Back of the disc' in photos and 'Add spine' not in photos

    upload(client, dvd, 'back', jpeg_bytes((400, 400)))
    box = box_of(client.get(f'/videos/{dvd}').get_data(as_text=True))
    assert 'item3d-disc' in box and '--a: 1.0;' in box and '--dr: 0.01;' in box
    assert '>Spine</button>' not in box and '>Back</button>' in box


def test_disc_placeholders_are_dvd_and_cd_only(client, db, people, static_root):
    login(client, 'alice')
    for medium in ('dvd', 'cd'):
        for kind in ('front', 'back'):
            r = add_disc_placeholder(client, medium, kind, f'{medium} {kind}')
            assert r.status_code == 302, (medium, kind)
    for medium in ('vhs', 'vinyl', 'book', 'cassette'):
        assert add_disc_placeholder(client, medium, 'back', 'nope').status_code == 400
    page = client.get('/faces/admin').get_data(as_text=True)
    dvd_tab = page[page.index('data-face-medium="dvd"'):page.index('data-face-medium="vhs"')]
    assert 'Disc front' in dvd_tab and 'Disc back' in dvd_tab
    vhs_tab = page[page.index('data-face-medium="vhs"'):]
    assert 'Disc front' not in vhs_tab
    # a round placeholder is left as it came (not turned tall or wide)
    path = scalar(db, "SELECT path FROM face_placeholders WHERE name = 'dvd back'")
    with Image.open(static_root / path) as img:
        assert img.size[0] == img.size[1]


def test_a_disc_back_placeholder_lets_a_disc_turn(client, db, people, static_root):
    """A bare disc with no photo of its back turns with the Disc back
    placeholder; a cased DVD is never offered one, and one picked before
    its cover changed isn't used."""
    login(client, 'alice')
    add_disc_placeholder(client, 'dvd', 'back', 'Silver side')
    pid = placeholder_id(db, 'Silver side')
    url = '/static/' + scalar(db, 'SELECT path FROM face_placeholders WHERE id = ?', pid)
    login(client, 'bob')
    dvd = add_item(db, people['bob'], 'video', 'DVD', disc_cover(static_root))
    edit = client.get(f'/videos/edit/{dvd}').get_data(as_text=True)
    assert 'data-face-choice="back"' in edit and 'Silver side' in edit
    client.post(f'/faces/item/{dvd}/choose', data={'kind': 'back', 'placeholder_id': pid})
    box = box_of(client.get(f'/videos/{dvd}').get_data(as_text=True))
    assert 'item3d-disc' in box and url in box

    cased = add_item(db, people['bob'], 'video', 'DVD', real_cover(static_root, 'case.jpg'))
    assert 'data-face-choice="back"' not in client.get(f'/videos/edit/{cased}').get_data(as_text=True)
    # picked while it was a disc, then given a cased cover: ignored
    db.execute("INSERT INTO item_faces (book_id, kind, placeholder_id) VALUES (?, 'back', ?)", (cased, pid))
    db.commit()
    page = client.get(f'/videos/{cased}').get_data(as_text=True)
    assert url not in page


def test_a_disc_front_stands_in_for_a_missing_cover(client, app, db, people, static_root):
    """No cover photo: the owner can pick a Disc front, which shows as the
    disc on the grid (and in infinite scroll) and is the 3D front. Once
    there's a cover photo it isn't offered or used."""
    login(client, 'alice')
    add_disc_placeholder(client, 'cd', 'front', 'Silver label')
    add_disc_placeholder(client, 'cd', 'back', 'Silver side')
    front = placeholder_id(db, 'Silver label')
    front_path = scalar(db, 'SELECT path FROM face_placeholders WHERE id = ?', front)
    login(client, 'bob')
    cd = add_item(db, people['bob'], 'record', 'CD', None)
    edit = client.get(f'/records/edit/{cd}').get_data(as_text=True)
    assert 'data-disc-front' in edit and 'data-face-choice="front"' in edit
    client.post(f'/faces/item/{cd}/choose', data={'kind': 'front', 'placeholder_id': front})
    client.post(f'/faces/item/{cd}/choose', data={'kind': 'back', 'placeholder_id': placeholder_id(db, 'Silver side')})

    grid = client.get('/records/').get_data(as_text=True)
    card = grid[grid.index('data-format="CD"'):]
    card = card[:card.index('</a>')] if '</a>' in card else card
    assert 'class="no-cover-disc' in card and f'/static/{front_path}' in card
    card, = cards_for(app, db, people['bob'], (cd,))
    assert card['shape'] == 'disc' and card['disc_front'] == front_path
    box = box_of(client.get(f'/records/{cd}').get_data(as_text=True))
    assert 'item3d-disc' in box and f'/static/{front_path}' in box

    # given a cover photo (a case), the Disc front steps aside
    db.execute('UPDATE books SET cover_image_url = ? WHERE id = ?', (real_cover(static_root, 'cd.jpg', (500, 440)), cd))
    db.commit()
    assert 'data-disc-front' not in client.get(f'/records/edit/{cd}').get_data(as_text=True)
    assert 'no-cover-disc' not in client.get('/records/').get_data(as_text=True)
    assert 'item3d-disc' not in client.get(f'/records/{cd}').get_data(as_text=True)


def test_disc_css_and_js_twins():
    import pathlib
    css = pathlib.Path('static/styles.css').read_text()
    assert ':root[data-style="shelf"] .cover-box[data-shape="disc"]::after { content: none; }' in css
    assert '.item3d-disc :is(.item3d-spine, .item3d-side, .item3d-top, .item3d-bottom) { display: none; }' in css
    js = pathlib.Path('static/common.js').read_text()
    assert 'const disc = shape ? ` data-shape="${escapeHtml(shape)}"`' in js
    assert 'class="no-cover-disc relative' in js
    assert "discFront: book.disc_front" in pathlib.Path('static/script.js').read_text()
