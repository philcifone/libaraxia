"""ROADMAP 15.3: the cover crop and perspective tool, server side.

The browser sends only geometry (fractions of the image); the server crops
its own copy. Covered here: the geometry validation, the Pillow rendering
(rect, perspective, rotation), the two /covers/crop/* routes and the four
save routes honouring a crop. The tool's JS helpers are in
tests/test_cover_crop_js.py.

people: alice (admin) + bob share a household; carol is alice's friend.
"""
import io
import json
import math
import os
import time
import uuid

import pytest
from PIL import Image

from conftest import add_book, login, scalar
from utils import cover_crop

RECT = {'v': 1, 'rotate': 0, 'mode': 'rect', 'box': [0.1, 0.1, 0.5, 0.5]}
QUAD = {'v': 1, 'rotate': 0, 'mode': 'quad',
        'quad': [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]], 'aspect': None}


def geom(**changes):
    return {**RECT, **changes}


# --- parse_geometry ---------------------------------------------------------

@pytest.mark.parametrize('raw', [RECT, QUAD, json.dumps(RECT),
                                 geom(rotate=270), geom(box=[0, 0, 1, 1]),
                                 {**QUAD, 'aspect': 0.6667},
                                 geom(flip_h=True), {**QUAD, 'flip_v': True},
                                 geom(mask='disc'), {**QUAD, 'mask': 'disc'}, geom(mask=None),
                                 geom(box=[0.5, 0.5, 0.5 + 1e-9, 0.5])])    # float fuzz is clamped
def test_parse_accepts_valid(raw):
    out = cover_crop.parse_geometry(raw)
    assert out['v'] == 1 and out['mode'] in ('rect', 'quad')


@pytest.mark.parametrize('raw', [
    geom(v=2), geom(v=True), geom(rotate=45), geom(rotate='90'), geom(rotate=True),
    geom(flip_h=1), geom(flip_v='true'), geom(flip_h=None),
    geom(mask='circle'), geom(mask=True), geom(mask=['disc']),
    geom(box=[0.1, 0.1, float('nan'), 0.5]), geom(box=[0.1, 0.1, float('inf'), 0.5]),
    geom(box=[-0.1, 0, 0.5, 0.5]), geom(box=[0.1, 0.1, 1.5, 0.5]),
    geom(box=[0.6, 0.1, 0.5, 0.5]),            # runs off the right edge
    geom(box=[0.1, 0.1, 0.01, 0.5]),           # too small
    geom(box=[0.1, 0.1, 0.5]), geom(box='x'), geom(box=[0.1, 0.1, '0.5', 0.5]),
    geom(mode='circle'), {'v': 1}, [], 'null', '{not json', 'x' * 2000,
    {**QUAD, 'quad': [[0.1, 0.1], [0.9, 0.9], [0.9, 0.1], [0.1, 0.9]]},   # bow-tie
    {**QUAD, 'quad': [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.1]]},   # degenerate
    {**QUAD, 'quad': [[0.1, 0.1], [0.5, 0.4], [0.9, 0.1], [0.5, 0.9]]},   # dented (concave)
    {**QUAD, 'quad': [[0.1, 0.9], [0.9, 0.9], [0.9, 0.1], [0.1, 0.1]]},   # mirrored
    {**QUAD, 'quad': [[0.1, 0.1], [0.15, 0.1], [0.15, 0.15], [0.1, 0.15]]},   # tiny area
    {**QUAD, 'quad': [[0.1, 0.1], [0.9, 0.1], [1.5, 0.9], [0.1, 0.9]]},   # off the image
    {**QUAD, 'quad': [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9]]},
    {**QUAD, 'aspect': 0},
    {**QUAD, 'aspect': 'wide'},
])
def test_parse_rejects_bad(raw):
    with pytest.raises(ValueError):
        cover_crop.parse_geometry(raw)


# --- perspective solver -----------------------------------------------------

def test_perspective_coefficients_map_output_corners_to_quad():
    quad = [(12.0, 8.0), (91.0, 3.0), (95.0, 97.0), (7.0, 92.0)]
    w, h = 60, 90
    a, b, c, d, e, f, g, hh = cover_crop.perspective_coeffs(quad, w, h)
    for (u, v), (x, y) in zip([(0, 0), (w, 0), (w, h), (0, h)], quad):
        denom = g * u + hh * v + 1
        assert (a * u + b * v + c) / denom == pytest.approx(x, abs=1e-6)
        assert (d * u + e * v + f) / denom == pytest.approx(y, abs=1e-6)


def test_perspective_rejects_collinear_points():
    with pytest.raises(ValueError):
        cover_crop.perspective_coeffs([(0, 0), (1, 1), (2, 2), (3, 3)], 10, 10)


def test_output_size():
    quad = [(0, 0), (100, 0), (100, 200), (0, 200)]
    assert cover_crop.output_size(quad) == (100, 200)
    assert cover_crop.output_size(quad, aspect=0.5) == (100, 200)
    assert cover_crop.output_size(quad, aspect=1) == (100, 100)
    big = [(0, 0), (6000, 0), (6000, 3000), (0, 3000)]
    assert max(cover_crop.output_size(big)) == cover_crop.OUTPUT_MAX


# --- render -----------------------------------------------------------------

def quadrants():
    """100x100: red top-left, green top-right, blue bottom-left, yellow bottom-right."""
    img = Image.new('RGB', (100, 100))
    for box, colour in [((0, 0, 50, 50), (255, 0, 0)), ((50, 0, 100, 50), (0, 255, 0)),
                        ((0, 50, 50, 100), (0, 0, 255)), ((50, 50, 100, 100), (255, 255, 0))]:
        img.paste(colour, box)
    return img


def test_render_rect_picks_one_quadrant():
    out = cover_crop.render(quadrants(), cover_crop.parse_geometry(geom(box=[0.5, 0.5, 0.5, 0.5])))
    assert out.size == (50, 50)
    assert out.getpixel((25, 25)) == (255, 255, 0)
    assert out.getpixel((0, 0)) == (255, 255, 0)


def test_render_rect_too_small_in_pixels():
    tiny = Image.new('RGB', (100, 100))
    with pytest.raises(ValueError):
        cover_crop.render(tiny, cover_crop.parse_geometry(geom(box=[0.1, 0.1, 0.05, 0.05])))


def test_render_quad_straightens_a_skewed_shape():
    """A white parallelogram-ish quad on black comes out (nearly) all white."""
    img = Image.new('RGB', (400, 400), 'black')
    pts = [(60, 40), (340, 70), (320, 360), (40, 330)]
    from PIL import ImageDraw
    ImageDraw.Draw(img).polygon(pts, fill='white')
    quad = [[x / 400, y / 400] for x, y in pts]
    out = cover_crop.render(img, cover_crop.parse_geometry({**QUAD, 'quad': quad}))
    pixels = list(out.convert('L').get_flattened_data())
    white = sum(1 for p in pixels if p > 200) / len(pixels)
    assert white > 0.95


def test_rotate_90_is_clockwise():
    """A red pixel at the top-left goes to the top-right."""
    img = Image.new('RGB', (40, 20), 'white')
    img.putpixel((0, 0), (255, 0, 0))
    out = cover_crop.render(img, cover_crop.parse_geometry(geom(rotate=90, box=[0, 0, 1, 1])))
    assert out.size == (20, 40)
    assert out.getpixel((19, 0)) == (255, 0, 0)
    # the normalized mapping the JS uses: (x, y) -> (1 - y, x)
    assert (1 - 0, 0) == (1, 0)


@pytest.mark.parametrize('rotate, corner', [(180, (39, 19)), (270, (0, 39))])
def test_other_rotations(rotate, corner):
    img = Image.new('RGB', (40, 20), 'white')
    img.putpixel((0, 0), (255, 0, 0))
    out = cover_crop.render(img, cover_crop.parse_geometry(geom(rotate=rotate, box=[0, 0, 1, 1])))
    assert out.getpixel(corner) == (255, 0, 0)


def test_flips_mirror_the_source_before_the_turn():
    """A red pixel at the top-left: flip_h sends it top-right, flip_v
    bottom-left; flip_h then a quarter turn clockwise lands it bottom-right."""
    img = Image.new('RGB', (40, 20), 'white')
    img.putpixel((0, 0), (255, 0, 0))
    whole = dict(box=[0, 0, 1, 1])
    assert cover_crop.render(img, cover_crop.parse_geometry(geom(flip_h=True, **whole))).getpixel((39, 0)) == (255, 0, 0)
    assert cover_crop.render(img, cover_crop.parse_geometry(geom(flip_v=True, **whole))).getpixel((0, 19)) == (255, 0, 0)
    out = cover_crop.render(img, cover_crop.parse_geometry(geom(flip_h=True, rotate=90, **whole)))
    assert out.size == (20, 40) and out.getpixel((19, 39)) == (255, 0, 0)


def test_disc_cuts_a_round_disc_with_a_see_through_spindle_hole():
    """Outside the disc and in the 15 mm hole of a 120 mm disc: clear. The
    clear hub ring between the hole and the label: kept."""
    img = Image.new('RGB', (400, 400), 'navy')
    out = cover_crop.render(img, cover_crop.parse_geometry(geom(mask='disc', box=[0, 0, 1, 1])))
    assert out.mode == 'RGBA' and out.size == (400, 400)
    alpha = lambda x, y: out.getpixel((x, y))[3]
    assert alpha(0, 0) == 0 and alpha(399, 399) == 0              # corners
    assert alpha(200, 200) == 0 and alpha(200 + 20, 200) == 0     # hole: radius 25 px
    assert alpha(200 + 32, 200) == 255                            # hub ring, just outside it
    assert alpha(200 + 150, 200) == 255 and alpha(5, 200) == 255  # body, near the rim
    assert out.getpixel((0, 0))[:3] == (255, 255, 255)            # clear pixels carry no photo


def test_disc_in_perspective_comes_out_square():
    """A disc photographed at a slant: the quad's own shape would give a
    squashed result, so a disc forces the aspect to 1."""
    slanted = {**QUAD, 'mask': 'disc', 'aspect': 0.5,
               'quad': [[0.1, 0.3], [0.9, 0.2], [0.95, 0.6], [0.05, 0.55]]}
    parsed = cover_crop.parse_geometry(slanted)
    assert parsed['aspect'] == 1.0
    out = cover_crop.render(Image.new('RGB', (400, 300), 'navy'), parsed)
    assert out.mode == 'RGBA' and out.width == out.height


def test_other_crops_stay_rgb():
    assert cover_crop.render(Image.new('RGB', (40, 40)), cover_crop.parse_geometry(RECT)).mode == 'RGB'


def test_parse_defaults_flips_off():
    out = cover_crop.parse_geometry(RECT)
    assert out['flip_h'] is False and out['flip_v'] is False


# --- helpers that guard paths -----------------------------------------------

def test_is_staged():
    token = 'A' * 22
    assert cover_crop.is_staged(f'uploads/crop/{token}.jpg')
    for bad in ['uploads/crop/short.jpg', f'uploads/crop/{token}.png', f'uploads/{token}.jpg',
                f'uploads/crop/../{token}.jpg', f'uploads/crop/{token}/x.jpg', None, '',
                f'uploads/avatars/{token}.jpg']:
        assert not cover_crop.is_staged(bad)


def jpeg_bytes(size=(300, 450), colour='navy', **save_args):
    out = io.BytesIO()
    Image.new('RGB', size, colour).save(out, 'JPEG', **save_args)
    out.seek(0)
    return out


def put_cover(app, size=(300, 450), colour='navy', subdir=''):
    """A real file under static/uploads; returns its relative path."""
    relative = f"uploads/{subdir}test_crop_{uuid.uuid4().hex}.jpg"
    full = os.path.join(app.root_path, 'static', relative)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    Image.new('RGB', size, colour).save(full, 'JPEG')
    return relative


def exists(app, relative):
    return os.path.exists(os.path.join(app.root_path, 'static', relative))


@pytest.fixture
def made(app):
    """Files a test makes under static/uploads, removed afterwards."""
    paths = []
    yield paths
    for relative in paths:
        try:
            os.remove(os.path.join(app.root_path, 'static', relative))
        except FileNotFoundError:
            pass


# --- /covers/crop/source ----------------------------------------------------

def test_crop_source_requires_login(client):
    assert client.post('/covers/crop/source').status_code == 302   # redirected to log in


def test_crop_source_rejects_non_image(client, people):
    login(client, 'bob')
    r = client.post('/covers/crop/source', data={'image': (io.BytesIO(b'not an image'), 'x.jpg')})
    assert r.status_code == 400 and r.get_json()['success'] is False
    r = client.post('/covers/crop/source', data={'image': (io.BytesIO(b'GIF89a'), 'x.txt')})
    assert r.status_code == 400
    assert client.post('/covers/crop/source').status_code == 400


def test_crop_source_stages_a_stripped_shrunken_jpeg(client, app, people, made):
    # A big photo with an EXIF block that has an orientation and a GPS pointer
    exif = Image.Exif()
    exif[0x0112] = 6                       # orientation: rotate to upright
    exif.get_ifd(0x8825)[1] = 'N'          # GPS latitude ref
    big = io.BytesIO()
    Image.new('RGB', (4000, 3000), 'teal').save(big, 'JPEG', exif=exif)
    big.seek(0)

    login(client, 'bob')
    r = client.post('/covers/crop/source', data={'image': (big, 'photo.jpg')})
    assert r.status_code == 200
    data = r.get_json()
    made.append(data['source'])
    assert cover_crop.is_staged(data['source'])
    assert data['source'].startswith('uploads/crop/')
    with Image.open(os.path.join(app.root_path, 'static', data['source'])) as staged:
        assert max(staged.size) <= 2400
        assert staged.size == (data['width'], data['height'])
        assert staged.size[0] < staged.size[1]            # the orientation was applied (3000 x 4000)
        assert not staged.getexif()                       # EXIF, including GPS, is gone
        assert 0x8825 not in staged.getexif()


# --- /covers/crop/preview ---------------------------------------------------

def post_preview(client, source, geometry=RECT):
    return client.post('/covers/crop/preview', json={'source': source, 'geometry': geometry})


def test_preview_requires_login(client):
    assert post_preview(client, 'uploads/x.jpg').status_code == 302   # redirected to log in


def test_preview_returns_a_jpeg(client, app, people, made):
    source = put_cover(app)
    made.append(source)
    login(client, 'bob')
    r = post_preview(client, source)
    assert r.status_code == 200 and r.mimetype == 'image/jpeg'
    assert r.headers['Cache-Control'] == 'no-store'
    with Image.open(io.BytesIO(r.data)) as img:
        assert img.size == (150, 225)
    r = post_preview(client, source, QUAD)
    assert r.status_code == 200 and r.mimetype == 'image/jpeg'


def test_preview_of_a_disc_is_a_transparent_webp(client, app, people, made):
    source = put_cover(app, size=(300, 300))
    made.append(source)
    login(client, 'bob')
    r = post_preview(client, source, geom(mask='disc', box=[0, 0, 1, 1]))
    assert r.status_code == 200 and r.mimetype == 'image/webp'
    with Image.open(io.BytesIO(r.data)) as img:
        assert img.mode == 'RGBA' and img.getpixel((0, 0))[3] == 0


def test_preview_downscales_big_sources(client, app, people, made):
    source = put_cover(app, size=(2000, 3000))
    made.append(source)
    login(client, 'bob')
    with Image.open(io.BytesIO(post_preview(client, source, geom(box=[0, 0, 1, 1])).data)) as img:
        assert max(img.size) == cover_crop.PREVIEW_MAX


@pytest.mark.parametrize('source', ['../library.db', '/etc/passwd', 'uploads/../app.py',
                                    'uploads/avatars/user_1.jpg', 'uploads/missing.jpg',
                                    'uploads', '', None, 5, 'static/uploads/x.jpg'])
def test_preview_refuses_bad_sources(client, people, source):
    login(client, 'bob')
    r = post_preview(client, source)
    assert r.status_code == 400 and r.get_json()['success'] is False


def test_preview_refuses_an_avatar_that_exists(client, app, people, made):
    avatar = put_cover(app, subdir='avatars/')
    made.append(avatar)
    login(client, 'bob')
    assert post_preview(client, avatar).status_code == 400


def test_preview_refuses_a_symlink_out_of_uploads(client, app, people, tmp_path):
    outside = tmp_path / 'secret.jpg'
    Image.new('RGB', (50, 50)).save(outside)
    link = os.path.join(app.root_path, 'static', 'uploads', f'test_link_{uuid.uuid4().hex}.jpg')
    os.symlink(outside, link)
    try:
        login(client, 'bob')
        assert post_preview(client, 'uploads/' + os.path.basename(link)).status_code == 400
    finally:
        os.remove(link)


def test_preview_bad_geometry(client, app, people, made):
    source = put_cover(app)
    made.append(source)
    login(client, 'bob')
    for bad in [None, {'v': 9}, geom(box=[0.5, 0.5, 0.9, 0.9])]:
        r = post_preview(client, source, bad)
        assert r.status_code == 400 and 'error' in r.get_json()


# --- sweep_staged -----------------------------------------------------------

def test_sweep_staged_removes_only_old_staged_files(app):
    folder = os.path.join(app.root_path, 'static', 'uploads', 'crop')
    os.makedirs(folder, exist_ok=True)
    old, fresh, stranger = (f'{uuid.uuid4().hex}{uuid.uuid4().hex[:6]}', f'{uuid.uuid4().hex}{uuid.uuid4().hex[:6]}', 'keep-me.jpg')
    for name in (old + '.jpg', fresh + '.jpg', stranger):
        Image.new('RGB', (20, 20)).save(os.path.join(folder, name), 'JPEG')
    long_ago = time.time() - 3 * 24 * 3600
    os.utime(os.path.join(folder, old + '.jpg'), (long_ago, long_ago))
    os.utime(os.path.join(folder, stranger), (long_ago, long_ago))
    try:
        with app.app_context():
            cover_crop.sweep_staged()
        assert not os.path.exists(os.path.join(folder, old + '.jpg'))
        assert os.path.exists(os.path.join(folder, fresh + '.jpg'))
        assert os.path.exists(os.path.join(folder, stranger))      # not one of ours
    finally:
        for name in (old + '.jpg', fresh + '.jpg', stranger):
            try:
                os.remove(os.path.join(folder, name))
            except FileNotFoundError:
                pass


# --- the save routes --------------------------------------------------------

BOOK = {'title': 'Piranesi', 'author': 'Susanna Clarke', 'publisher': 'B', 'year': '2020',
        'isbn': '9781635575637', 'page_count': '272', 'description': 'd', 'subtitle': '', 'genre': 'F'}
MOVIE = {'title': 'Jaws', 'author': 'Spielberg', 'format': 'DVD', 'year': '1975'}
RECORD = {'title': 'Blue', 'author': 'Joni Mitchell', 'format': 'LP', 'year': '1971'}
CROP = json.dumps(geom(box=[0.1, 0.1, 0.5, 0.5]))


def stage(client, made):
    r = client.post('/covers/crop/source', data={'image': (jpeg_bytes((800, 1200)), 'p.jpg')})
    source = r.get_json()['source']
    made.append(source)
    return source


def track(app, made, db_value):
    """Register a stored cover path for cleanup and return it."""
    if db_value:
        made.append(db_value)
    return db_value


def test_edit_book_with_crop_replaces_cover_and_removes_old_files(client, app, db, people, made):
    old = put_cover(app)
    book = add_book(db, people['bob'], cover=old)
    login(client, 'bob')
    source = stage(client, made)
    r = client.post(f'/books/edit/{book}', data={**BOOK, 'crop_source': source, 'cover_crop': CROP})
    assert r.status_code == 302
    new = track(app, made, scalar(db, 'SELECT cover_image_url FROM books WHERE id = ?', book))
    assert new != old and new.startswith('uploads/')
    assert exists(app, new)
    assert not exists(app, old)              # the old cover is deleted
    assert not exists(app, source)           # so is the staged original
    with Image.open(os.path.join(app.root_path, 'static', new)) as img:
        assert img.size == (400, 600)        # half of the staged 800x1200


def test_edit_book_crop_of_its_own_cover(client, app, db, people, made):
    old = put_cover(app, size=(200, 300))
    book = add_book(db, people['bob'], cover=old)
    login(client, 'bob')
    client.post(f'/books/edit/{book}', data={**BOOK, 'crop_source': old, 'cover_crop': CROP})
    new = track(app, made, scalar(db, 'SELECT cover_image_url FROM books WHERE id = ?', book))
    assert new != old and not exists(app, old)
    with Image.open(os.path.join(app.root_path, 'static', new)) as img:
        assert img.size == (100, 150)


def test_edit_book_crop_wins_over_an_upload(client, app, db, people, made):
    old = put_cover(app)
    book = add_book(db, people['bob'], cover=old)
    login(client, 'bob')
    source = stage(client, made)
    client.post(f'/books/edit/{book}', data={**BOOK, 'crop_source': source, 'cover_crop': CROP,
                                             'image': (jpeg_bytes(colour='red'), 'u.jpg')})
    new = track(app, made, scalar(db, 'SELECT cover_image_url FROM books WHERE id = ?', book))
    with Image.open(os.path.join(app.root_path, 'static', new)) as img:
        assert img.size == (400, 600)        # from the staged 800x1200, not the 300x450 upload


def test_edit_book_bad_geometry_keeps_cover_and_saves_the_rest(client, app, db, people, made):
    old = track(app, made, put_cover(app))
    book = add_book(db, people['bob'], cover=old)
    login(client, 'bob')
    source = stage(client, made)
    r = client.post(f'/books/edit/{book}', data={**BOOK, 'title': 'Renamed', 'crop_source': source,
                                                 'cover_crop': json.dumps(geom(rotate=45))},
                    follow_redirects=True)
    assert 'apply the crop' in r.get_data(as_text=True)
    assert scalar(db, 'SELECT cover_image_url FROM books WHERE id = ?', book) == old
    assert scalar(db, 'SELECT title FROM books WHERE id = ?', book) == 'Renamed'
    assert exists(app, old)


def test_crop_source_naming_another_cover_is_refused_and_not_deleted(client, app, db, people, made):
    """A crafted post can't crop, or delete, a cover that isn't this book's own."""
    mine = track(app, made, put_cover(app))
    theirs = track(app, made, put_cover(app))
    book = add_book(db, people['bob'], cover=mine)
    add_book(db, people['carol'], title='Other', cover=theirs)
    login(client, 'bob')
    r = client.post(f'/books/edit/{book}', data={**BOOK, 'crop_source': theirs, 'cover_crop': CROP},
                    follow_redirects=True)
    assert 'apply the crop' in r.get_data(as_text=True)
    assert scalar(db, 'SELECT cover_image_url FROM books WHERE id = ?', book) == mine
    assert exists(app, theirs) and exists(app, mine)


def test_crop_source_may_be_a_fetched_cover(client, app, db, people, made):
    old = put_cover(app)
    fetched = track(app, made, put_cover(app, size=(200, 300), subdir='staged/'))    # what a lookup saves (16.0g)
    book = add_book(db, people['bob'], cover=old)
    login(client, 'bob')
    client.post(f'/books/edit/{book}', data={**BOOK, 'existing_cover_url': fetched,
                                             'crop_source': fetched, 'cover_crop': CROP})
    new = track(app, made, scalar(db, 'SELECT cover_image_url FROM books WHERE id = ?', book))
    assert new not in (old, fetched) and exists(app, new)
    assert not exists(app, old)
    assert exists(app, fetched)              # unused now: left for the day's sweep


def test_non_owner_cannot_crop_someone_elses_book(client, app, db, people, made):
    old = track(app, made, put_cover(app))
    book = add_book(db, people['bob'], cover=old)
    login(client, 'carol')
    source = stage(client, made)
    client.post(f'/books/edit/{book}', data={**BOOK, 'crop_source': source, 'cover_crop': CROP})
    assert scalar(db, 'SELECT cover_image_url FROM books WHERE id = ?', book) == old
    assert exists(app, source)               # nothing was rendered, so nothing was consumed


def test_add_book_with_staged_crop(client, app, db, people, made):
    login(client, 'bob')
    source = stage(client, made)
    r = client.post('/books/add', data={**BOOK, 'submit_book': '1', 'crop_source': source, 'cover_crop': CROP})
    assert r.status_code == 302
    new = track(app, made, scalar(db, "SELECT cover_image_url FROM books WHERE title = 'Piranesi'"))
    assert new and exists(app, new) and not exists(app, source)


def test_add_book_crop_of_an_arbitrary_path_is_refused(client, app, db, people, made):
    theirs = track(app, made, put_cover(app))
    login(client, 'bob')
    client.post('/books/add', data={**BOOK, 'submit_book': '1', 'crop_source': theirs, 'cover_crop': CROP})
    assert scalar(db, "SELECT cover_image_url FROM books WHERE title = 'Piranesi'") is None
    assert exists(app, theirs)


@pytest.mark.parametrize('section, form, media_type', [('videos', MOVIE, 'video'), ('records', RECORD, 'record')])
def test_media_edit_with_crop(client, app, db, people, made, section, form, media_type):
    old = put_cover(app)
    cur = db.execute('INSERT INTO books (title, author, added_by, media_type, cover_image_url, format) '
                     "VALUES ('X', 'Y', ?, ?, ?, ?)", (people['bob'], media_type, old, form['format']))
    db.commit()
    item = cur.lastrowid
    login(client, 'bob')
    source = stage(client, made)
    r = client.post(f'/{section}/edit/{item}', data={**form, 'crop_source': source, 'cover_crop': CROP})
    assert r.status_code == 302
    new = track(app, made, scalar(db, 'SELECT cover_image_url FROM books WHERE id = ?', item))
    assert new != old and exists(app, new)
    assert not exists(app, old) and not exists(app, source)


@pytest.mark.parametrize('section, form', [('videos', MOVIE), ('records', RECORD)])
def test_media_add_with_crop(client, app, db, people, made, section, form):
    login(client, 'bob')
    source = stage(client, made)
    r = client.post(f'/{section}/add', data={**form, 'crop_source': source, 'cover_crop': CROP})
    assert r.status_code == 302
    new = track(app, made, scalar(db, "SELECT cover_image_url FROM books WHERE title = ?", form['title']))
    assert new and exists(app, new) and not exists(app, source)


def test_media_edit_non_owner_gets_404(client, app, db, people, made):
    cur = db.execute("INSERT INTO books (title, author, added_by, media_type) VALUES ('X', 'Y', ?, 'video')",
                     (people['bob'],))
    db.commit()
    login(client, 'carol')
    source = stage(client, made)
    r = client.post(f'/videos/edit/{cur.lastrowid}', data={**MOVIE, 'crop_source': source, 'cover_crop': CROP})
    assert r.status_code == 404


def test_wishlist_add_with_crop(client, app, db, people, made):
    login(client, 'bob')
    source = stage(client, made)
    r = client.post('/wishlist/add?type=video', data={**MOVIE, 'media_type': 'video',
                                                      'crop_source': source, 'cover_crop': CROP})
    assert r.status_code == 302
    new = track(app, made, scalar(db, "SELECT cover_image_url FROM books WHERE title = 'Jaws'"))
    assert new and exists(app, new) and not exists(app, source)


# --- Save at once on an Edit page (covers.crop_save; Phil, 2026-11-15) ---------

def test_crop_save_replaces_the_cover_at_once(client, app, db, people, made):
    """The crop tool's Save on an Edit page saves the cover there and then,
    from the item's own cover or a staged pick; the old files go."""
    old = put_cover(app, size=(200, 300))
    book = add_book(db, people['bob'], cover=old)
    login(client, 'bob')
    assert f'data-save-url="/covers/crop/save/{book}"' in client.get(f'/books/edit/{book}').get_data(as_text=True)
    assert 'data-save-url' not in client.get('/books/add').get_data(as_text=True)
    r = client.post(f'/covers/crop/save/{book}', json={'source': old, 'geometry': json.loads(CROP)})
    first = track(app, made, scalar(db, 'SELECT cover_image_url FROM books WHERE id = ?', book))
    assert r.get_json() == {'success': True, 'message': 'Cropped cover saved.', 'path': first,
                            'url': f'/static/{first}'}
    assert first != old and exists(app, first) and not exists(app, old)
    source = stage(client, made)
    client.post(f'/covers/crop/save/{book}', json={'source': source, 'geometry': json.loads(CROP)})
    second = track(app, made, scalar(db, 'SELECT cover_image_url FROM books WHERE id = ?', book))
    assert exists(app, second) and not exists(app, first) and not exists(app, source)


def test_crop_save_of_a_disc_keeps_its_transparency(client, app, db, people, made):
    """A bare CD as the cover: saved as WebP with alpha, not flattened to a
    white JPEG like every other cover."""
    old = put_cover(app, size=(300, 300))
    book = add_book(db, people['bob'], cover=old)
    login(client, 'bob')
    r = client.post(f'/covers/crop/save/{book}',
                    json={'source': old, 'geometry': geom(mask='disc', box=[0, 0, 1, 1])})
    assert r.get_json()['success']
    path = track(app, made, scalar(db, 'SELECT cover_image_url FROM books WHERE id = ?', book))
    from utils.image_utils import ALPHA_FORMAT
    assert path.endswith(ALPHA_FORMAT[1]) and not exists(app, old)
    with Image.open(os.path.join(app.root_path, 'static', path)) as img:
        assert img.mode == 'RGBA' and img.getpixel((0, 0))[3] == 0 and img.getpixel((150, 150))[3] == 0
        assert img.getpixel((150, 60))[3] == 255


def test_crop_save_is_the_owners_and_only_of_its_own_sources(client, app, db, people, made):
    mine = track(app, made, put_cover(app))
    theirs = track(app, made, put_cover(app))
    book = add_book(db, people['bob'], cover=mine)
    add_book(db, people['carol'], title='Other', cover=theirs)
    login(client, 'bob')
    r = client.post(f'/covers/crop/save/{book}', json={'source': theirs, 'geometry': json.loads(CROP)})
    assert r.status_code == 400 and exists(app, theirs)
    assert client.post(f'/covers/crop/save/{book}', json={'source': mine, 'geometry': {'v': 9}}).status_code == 400
    assert scalar(db, 'SELECT cover_image_url FROM books WHERE id = ?', book) == mine
    client.get('/auth/logout')
    login(client, 'carol')                   # no circle with bob: can't see it
    r = client.post(f'/covers/crop/save/{book}', json={'source': mine, 'geometry': json.loads(CROP)})
    assert r.status_code == 404
    client.get('/auth/logout')
    login(client, 'alice')                   # bob's household, and admin
    db.execute('UPDATE users SET is_admin = 0 WHERE id = ?', (people['alice'],))
    db.commit()
    r = client.post(f'/covers/crop/save/{book}', json={'source': mine, 'geometry': json.loads(CROP)})
    assert r.status_code == 403 and exists(app, mine)


def test_crop_tool_opens_in_perspective(client, db, people):
    """Perspective is the crop tool's default mode, app wide (Phil,
    2026-11-15): the dialog shows it pressed and first, and the script
    starts, resets and undoes to it."""
    book = add_book(db, people['bob'])
    login(client, 'bob')
    page = client.get(f'/books/edit/{book}').get_data(as_text=True)
    modes = page[page.index('id="crop-l-mode"'):]
    assert modes.index('data-crop-mode="quad" aria-pressed="true"') < modes.index('data-crop-mode="rect" aria-pressed="false"')
    js = open(os.path.join(os.path.dirname(__file__), '..', 'static', 'cover_crop.js')).read()
    assert "const DEFAULT_MODE = 'quad';" in js and "mode = 'rect';" not in js


# --- fetched covers are staged (16.0g step 8) --------------------------------

def test_fetched_covers_are_staged_swept_and_never_orphans(app, db, static_root):
    import time
    from utils import book_utils
    with app.test_request_context():
        path = book_utils.save_cover_image(Image.new('RGB', (300, 450), 'navy'), staged=True)
        assert book_utils.is_staged_cover(path) and (static_root / path).exists()
        old = book_utils.save_cover_image(Image.new('RGB', (300, 450), 'red'), staged=True)
        a_day_ago = time.time() - book_utils.STAGED_COVER_MAX_AGE - 60
        os.utime(static_root / old, (a_day_ago, a_day_ago))
        book_utils.sweep_staged_covers()
        assert (static_root / path).exists() and not (static_root / old).exists()
        # A right-looking path outside staged/ isn't staged
        assert not book_utils.is_staged_cover('uploads/' + path.rsplit('/', 1)[1])
        assert not book_utils.is_staged_cover('uploads/staged/../cover_x.jpg')


def test_an_expired_staged_cover_saves_the_item_without_it(client, db, people, static_root):
    login(client, 'bob')
    gone = 'uploads/staged/' + 'c' * 22 + '.jpg'
    r = client.post('/books/add', data={**BOOK, 'submit_book': '1', 'existing_cover_url': gone},
                    follow_redirects=True)
    assert 'The cover you picked expired' in r.get_data(as_text=True)
    assert scalar(db, "SELECT cover_image_url FROM books WHERE title = 'Piranesi'") is None


def test_a_bad_upload_on_edit_keeps_the_cover(client, app, db, people, made):
    """It used to delete the file first and keep the path: a dead cover."""
    from io import BytesIO
    old = track(app, made, put_cover(app))
    book = add_book(db, people['bob'], cover=old)
    login(client, 'bob')
    client.post(f'/books/edit/{book}', data={**BOOK, 'image': (BytesIO(b'x'), 'notes.txt')},
                content_type='multipart/form-data')
    assert scalar(db, 'SELECT cover_image_url FROM books WHERE id = ?', book) == old and exists(app, old)
