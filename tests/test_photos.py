"""Item photos (ROADMAP 16.0a, docs/PHOTOS-VALUE-SPEC.md sections 3 and 11)."""
import io
import os
import re

from PIL import Image

from conftest import add_book, add_user, login, scalar


def jpeg_bytes(size=(600, 400), exif=None, color='red'):
    out = io.BytesIO()
    img = Image.new('RGB', size, color)
    if exif is not None:
        img.save(out, 'JPEG', exif=exif)
    else:
        img.save(out, 'JPEG')
    out.seek(0)
    return out


def upload(client, book_id, kind, *files, json=True):
    data = {'photo': [(f, f'p{i}.jpg') for i, f in enumerate(files)]}
    headers = {'X-Requested-With': 'XMLHttpRequest'} if json else {}
    return client.post(f'/photos/{book_id}/{kind}', data=data, headers=headers,
                       content_type='multipart/form-data')


def gps_exif(orientation=None):
    """EXIF with a GPS block (and an orientation, if given)."""
    exif = Image.Exif()
    exif[0x8825] = {1: 'N', 2: (40.0, 26.0, 46.0), 3: 'W', 4: (79.0, 58.0, 56.0)}
    if orientation:
        exif[0x0112] = orientation
    return exif.tobytes()


# --- save_photo ---------------------------------------------------------------

def test_save_photo_strips_metadata_and_turns_upright(app, static_root):
    from utils.image_utils import save_photo
    # 600 wide x 400 high pixels, tagged "rotate 90 CW to view" (6)
    with app.app_context():
        path = save_photo(jpeg_bytes((600, 400), exif=gps_exif(orientation=6)), 7)
    assert path.startswith('uploads/photos/7/') and path.endswith('.jpg')
    with Image.open(static_root / path) as img:
        assert img.size == (400, 600)               # upright: portrait now
        assert not img.getexif()                    # no EXIF, so no GPS
        assert 'exif' not in img.info and 'xmp' not in img.info


def test_save_photo_resizes_long_side_and_keeps_a_spine_narrow(app, static_root):
    from utils.image_utils import save_photo
    with app.app_context():
        path = save_photo(jpeg_bytes((300, 4000)), 7)
    with Image.open(static_root / path) as img:
        assert img.size == (150, 2000)


def test_save_photo_refuses_a_non_image(app):
    import pytest
    from utils.image_utils import PhotoError, save_photo
    with app.app_context(), pytest.raises(PhotoError):
        save_photo(io.BytesIO(b'not an image at all'), 7)


# --- routes and access --------------------------------------------------------

def test_owner_adds_back_spine_and_gallery(client, db, people, static_root):
    book = add_book(db, people['bob'])
    login(client, 'bob')
    r = upload(client, book, 'back', jpeg_bytes())
    assert r.status_code == 200 and r.get_json()['success']
    r = upload(client, book, 'spine', jpeg_bytes((80, 600)))
    assert r.status_code == 200
    r = upload(client, book, 'gallery', jpeg_bytes(), jpeg_bytes(), jpeg_bytes())
    assert len(r.get_json()['photos']) == 3
    kinds = [row[0] for row in db.execute('SELECT kind FROM item_photos WHERE book_id = ? ORDER BY id', (book,))]
    assert kinds == ['back', 'spine', 'gallery', 'gallery', 'gallery']


def test_replacing_the_back_deletes_the_old_file(client, db, people, static_root):
    book = add_book(db, people['bob'])
    login(client, 'bob')
    upload(client, book, 'back', jpeg_bytes())
    first = scalar(db, "SELECT path FROM item_photos WHERE kind = 'back'")
    upload(client, book, 'back', jpeg_bytes(color='blue'))
    second = scalar(db, "SELECT path FROM item_photos WHERE kind = 'back'")
    assert first != second
    assert not (static_root / first).exists() and (static_root / second).exists()
    assert scalar(db, "SELECT COUNT(*) FROM item_photos WHERE kind = 'back'") == 1


def test_every_type_takes_every_face(client, db, people):
    """Every type takes every face (16.0c, docs/FACES-SPEC.md section 2):
    a vinyl sleeve a spine (a gatefold's is printed), a book a bottom edge;
    the edit page names a book's page faces as pages."""
    rec = db.execute("INSERT INTO books (title, author, added_by, media_type, format) "
                     "VALUES ('Blue', 'Joni', ?, 'record', 'LP')", (people['bob'],)).lastrowid
    book = add_book(db, people['bob'])
    db.commit()
    login(client, 'bob')
    for kind in ('back', 'spine', 'side', 'top', 'bottom'):
        assert upload(client, rec, kind, jpeg_bytes()).status_code == 200
    assert upload(client, book, 'bottom', jpeg_bytes()).status_code == 200
    assert upload(client, book, 'front', jpeg_bytes()).status_code == 404
    edit = client.get(f'/books/edit/{book}').get_data(as_text=True)
    assert 'Fore-edge' in edit and 'Top edge' in edit and 'Bottom edge' in edit
    record_edit = client.get(f'/records/edit/{rec}').get_data(as_text=True)
    assert 'Right side' in record_edit and 'Fore-edge' not in record_edit


def test_bad_file_is_refused_with_a_message(client, db, people):
    book = add_book(db, people['bob'])
    login(client, 'bob')
    r = upload(client, book, 'gallery', io.BytesIO(b'hello'))
    assert r.status_code == 400 and 'image' in r.get_json()['error']
    assert scalar(db, 'SELECT COUNT(*) FROM item_photos') == 0


def test_gallery_stops_at_the_limit(client, db, people, monkeypatch):
    from utils import photos
    monkeypatch.setattr(photos, 'MAX_PER_ITEM', 2)
    book = add_book(db, people['bob'])
    login(client, 'bob')
    r = upload(client, book, 'gallery', jpeg_bytes(), jpeg_bytes(), jpeg_bytes())
    assert r.status_code == 400 and len(r.get_json()['photos']) == 2


def test_only_owner_or_admin_changes_photos(client, db, people):
    """A friend (carol, of alice) can see alice's book but not change its
    photos; a household member (bob) can't either; a stranger gets 404."""
    stranger = add_user(db, 'dave')
    book = add_book(db, people['alice'])
    login(client, 'carol')
    assert upload(client, book, 'gallery', jpeg_bytes()).status_code == 403
    client.get('/auth/logout')
    login(client, 'bob')
    assert upload(client, book, 'gallery', jpeg_bytes()).status_code == 403
    client.get('/auth/logout')
    login(client, 'dave')
    assert upload(client, book, 'gallery', jpeg_bytes()).status_code == 404
    assert stranger


def test_admin_may_add_and_stranger_gets_404_on_photo_routes(client, db, people):
    book = add_book(db, people['bob'])
    add_user(db, 'dave')
    login(client, 'alice')       # admin
    assert upload(client, book, 'gallery', jpeg_bytes()).status_code == 200
    photo = scalar(db, 'SELECT id FROM item_photos')
    client.get('/auth/logout')
    login(client, 'dave')
    assert client.post(f'/photos/photo/{photo}/delete').status_code == 404
    assert client.post(f'/photos/photo/{photo}/caption', data={'caption': 'x'}).status_code == 404
    assert scalar(db, 'SELECT COUNT(*) FROM item_photos') == 1


def test_delete_and_caption(client, db, people, static_root):
    book = add_book(db, people['bob'])
    login(client, 'bob')
    upload(client, book, 'gallery', jpeg_bytes())
    photo, path = db.execute('SELECT id, path FROM item_photos').fetchone()
    r = client.post(f'/photos/photo/{photo}/caption', data={'caption': '  Inner sleeve '},
                    headers={'X-Requested-With': 'XMLHttpRequest'})
    assert r.get_json()['caption'] == 'Inner sleeve'
    assert scalar(db, 'SELECT caption FROM item_photos') == 'Inner sleeve'
    # A plain form post redirects back to the edit page's Photos section
    r = client.post(f'/photos/photo/{photo}/delete')
    assert r.status_code == 302 and r.headers['Location'].endswith(f'/books/edit/{book}#photos')
    assert scalar(db, 'SELECT COUNT(*) FROM item_photos') == 0
    assert not (static_root / path).exists()


def test_deleting_an_item_removes_its_photo_folder(client, db, people, static_root):
    book = add_book(db, people['bob'])
    login(client, 'bob')
    upload(client, book, 'gallery', jpeg_bytes())
    folder = static_root / 'uploads' / 'photos' / str(book)
    assert folder.is_dir()
    client.post(f'/books/delete/{book}')
    assert scalar(db, 'SELECT COUNT(*) FROM books WHERE id = ?', book) == 0
    assert scalar(db, 'SELECT COUNT(*) FROM item_photos') == 0
    assert not folder.exists()


def test_orphan_cleanup_keeps_photos(app, db, people, monkeypatch, tmp_path):
    """The admin's orphan cleanup must count item_photos as referenced, or
    its first run would delete every photo."""
    from utils.image_utils import find_orphaned_images
    root = tmp_path / 'approot'
    photos_dir = root / 'static' / 'uploads' / 'photos' / '1'
    photos_dir.mkdir(parents=True)
    (photos_dir / 'kept.jpg').write_bytes(b'x')
    (photos_dir / 'stray.jpg').write_bytes(b'x')
    book = add_book(db, people['bob'])
    db.execute("INSERT INTO item_photos (book_id, kind, path) VALUES (?, 'gallery', 'uploads/photos/1/kept.jpg')",
               (book,))
    db.commit()
    monkeypatch.setattr(app, 'root_path', str(root))
    with app.app_context():
        found = find_orphaned_images(db)
    assert [f['path'] for f in found['orphaned_files']] == ['uploads/photos/1/stray.jpg']


def test_item_page_more_photos_for_a_friend(client, db, people, static_root):
    """carol (alice's friend) sees alice's photos and their caption, escaped;
    an item with none has no More photos link."""
    book = add_book(db, people['alice'])
    bare = add_book(db, people['alice'], title='Bare')
    login(client, 'alice')
    upload(client, book, 'back', jpeg_bytes())
    upload(client, book, 'gallery', jpeg_bytes())
    photo = scalar(db, "SELECT id FROM item_photos WHERE kind = 'gallery'")
    client.post(f'/photos/photo/{photo}/caption', data={'caption': '<b>Scuff</b> on side B'})
    client.get('/auth/logout')
    login(client, 'carol')
    html = client.get(f'/books/book/{book}').get_data(as_text=True)
    assert 'data-click="openGallery"' in html and 'More photos (2)' in html
    assert html.count('data-slide') == 2
    assert '&lt;b&gt;Scuff&lt;/b&gt; on side B' in html and '<b>Scuff' not in html
    assert 'openGallery' not in client.get(f'/books/book/{bare}').get_data(as_text=True)


def real_cover(static_root, name='c.jpg', size=(400, 600)):
    (static_root / 'uploads').mkdir(exist_ok=True)
    (static_root / 'uploads' / name).write_bytes(jpeg_bytes(size).getvalue())
    return f'uploads/{name}'


def add_item(db, user, media_type, fmt, cover):
    row = db.execute("INSERT INTO books (title, author, added_by, media_type, format, cover_image_url) "
                     "VALUES ('Blue', 'Joni', ?, ?, ?, ?)", (user, media_type, fmt, cover)).lastrowid
    db.commit()
    return row


def box_of(html):
    box = html[html.index('<dialog id="item-3d"'):]
    return box[:box.index('</dialog>')]


def test_3d_only_with_every_photo_its_shape_needs(client, db, people, static_root):
    """No drawn stand-ins (Phil, 2026-11-15): a book turns in 3D once it has
    a cover, a back and a spine, and not before; the edit page says what's
    still missing. The box's proportions come from the photos."""
    book = add_book(db, people['bob'], cover=real_cover(static_root))
    login(client, 'bob')
    assert 'item-3d' not in client.get(f'/books/book/{book}').get_data(as_text=True)
    upload(client, book, 'back', jpeg_bytes((400, 600)))
    assert 'item-3d' not in client.get(f'/books/book/{book}').get_data(as_text=True)
    edit = client.get(f'/books/edit/{book}').get_data(as_text=True)
    assert 'data-3d-status="needs"' in edit and 'still needs: spine.' in edit
    upload(client, book, 'spine', jpeg_bytes((60, 600)))
    box = box_of(client.get(f'/books/book/{book}').get_data(as_text=True))
    assert 'item3d-book' in box and box.count('/static/uploads/photos/') == 2
    assert '--a: 0.6667; --dr: 0.1;' in box
    assert 'item3d-spine-print' not in box
    assert 'data-3d-status="ready"' in client.get(f'/books/edit/{book}').get_data(as_text=True)


def test_3d_shapes_for_music_and_movies(client, db, people, static_root):
    """An LP is a thin sleeve of cover and back; a CD the shape of its
    cover photo (the whole case front, nothing drawn), its spine drawn until there's a
    photo; a DVD needs its spine; a VHS sleeve its back and a side."""
    bob = people['bob']
    login(client, 'bob')
    square = real_cover(static_root, 's.jpg', (500, 500))
    lp = add_item(db, bob, 'record', 'LP', square)
    upload(client, lp, 'back', jpeg_bytes((500, 500)))
    box = box_of(client.get(f'/records/{lp}').get_data(as_text=True))
    assert 'item3d-sleeve' in box and '--a: 1.0; --dr: 0.012;' in box
    assert 'data-angle="90"' not in box            # no Spine button: nothing to see
    # A gatefold: its spine photo sets the thickness and earns a Spine button
    upload(client, lp, 'spine', jpeg_bytes((20, 500)))
    box = box_of(client.get(f'/records/{lp}').get_data(as_text=True))
    assert '--dr: 0.04;' in box and 'data-angle="90"' in box

    cd = add_item(db, bob, 'record', 'CD', square)
    upload(client, cd, 'back', jpeg_bytes((500, 500)))
    box = box_of(client.get(f'/records/{cd}').get_data(as_text=True))
    assert 'item3d-jewel' in box and 'hinge' not in box and '--a: 1.0; --dr: 0.083;' in box
    assert box.count('item3d-spine-print') == 2 and '>Blue<' in box
    # A card sleeve: its thin spine photo sets the thickness
    upload(client, cd, 'spine', jpeg_bytes((10, 500)))
    box = box_of(client.get(f'/records/{cd}').get_data(as_text=True))
    assert 'item3d-spine-print' not in box and '--dr: 0.02;' in box
    # the right end is the same spine, upside down, as on the inlay
    css = open(os.path.join(os.path.dirname(__file__), '..', 'static', 'styles.css')).read()
    assert '.item3d-jewel .item3d-side > * { transform: rotate(180deg); }' in css

    tall = real_cover(static_root, 't.jpg', (400, 720))
    dvd = add_item(db, bob, 'video', 'DVD', tall)
    upload(client, dvd, 'back', jpeg_bytes((400, 720)))
    assert 'item-3d' not in client.get(f'/videos/{dvd}').get_data(as_text=True)
    upload(client, dvd, 'spine', jpeg_bytes((40, 720)))
    assert 'item3d-case' in box_of(client.get(f'/videos/{dvd}').get_data(as_text=True))

    # A VHS: back and at least one long side (Phil, 2026-11-15); one side
    # does for both, and a double box is just a wider side photo
    vhs = add_item(db, bob, 'video', 'VHS', tall)
    upload(client, vhs, 'back', jpeg_bytes((400, 720)))
    edit = client.get(f'/videos/edit/{vhs}').get_data(as_text=True)
    assert 'still needs: left side or right side.' in edit and 'Left side' in edit and 'Right side' in edit
    assert 'item-3d' not in client.get(f'/videos/{vhs}').get_data(as_text=True)
    upload(client, vhs, 'side', jpeg_bytes((200, 720)))
    box = box_of(client.get(f'/videos/{vhs}').get_data(as_text=True))
    assert 'item3d-tape' in box and '--dr: 0.2778;' in box
    side = re.search(r'item3d-side">\s*<img src="([^"]+)"', box).group(1)
    assert re.search(r'item3d-spine">\s*<img src="([^"]+)"', box).group(1) == side
    assert 'item3d-top">\n        \n    </div>' in box or re.search(r'item3d-top">\s*</div>', box)
    upload(client, vhs, 'top', jpeg_bytes((400, 100)))
    box = box_of(client.get(f'/videos/{vhs}').get_data(as_text=True))
    assert box.count('/static/uploads/photos/') == 4
    # and a bottom (16.0c): the open end's photo replaces the black
    upload(client, vhs, 'bottom', jpeg_bytes((400, 100)))
    box = box_of(client.get(f'/videos/{vhs}').get_data(as_text=True))
    assert re.search(r'item3d-bottom">\s*<img src="/static/uploads/photos/', box)

    # The item page's flat cover box wears the top and right side photos on
    # its faces (Phil, 2026-11-15; every type since 16.0c, below)
    page = client.get(f'/videos/{vhs}').get_data(as_text=True)
    stand = page[page.index('class="cover-stand'):]
    stand = stand[:stand.index('>')]
    assert '--face-top: url(' in stand and '--face-side: url(' in stand
    dvd_page = client.get(f'/videos/{dvd}').get_data(as_text=True)
    assert '--face-' not in dvd_page
    # and so does its card on the Movies grid; the DVD's doesn't
    grid = client.get('/videos/').get_data(as_text=True)
    card = re.search(r'<div class="book-item group" data-format="VHS"[^>]*>', grid).group(0)
    assert '--face-top: url(' in card and '--face-side: url(' in card
    assert 'style=' not in re.search(r'<div class="book-item group" data-format="DVD"[^>]*>', grid).group(0)
    assert 'data-angle="270"' in box
    # Every type since 16.0c: the DVD's top photo goes on its box too, the
    # side stays plain; and on the next page's cards (infinite scroll)
    upload(client, dvd, 'top', jpeg_bytes((400, 40)))
    card = re.search(r'<div class="book-item group" data-format="DVD"[^>]*>',
                     client.get('/videos/').get_data(as_text=True)).group(0)
    assert '--face-top: url(' in card and '--face-side' not in card
    from utils.book_utils import card_json
    with client.application.test_request_context():
        rows = db.execute('SELECT * FROM books WHERE id = ?', (dvd,)).fetchall()
        assert '--face-top: url(' in card_json(db, bob, rows)[0]['faces']


def test_crop_a_photo(client, db, people, static_root):
    """A photo's Crop (the cover's crop tool, photo mode) replaces its file
    with the cropped one; owner only; a bad geometry is refused."""
    book = add_book(db, people['bob'])
    login(client, 'bob')
    upload(client, book, 'back', jpeg_bytes((800, 600)))
    photo, old = db.execute('SELECT id, path FROM item_photos').fetchone()
    html = client.get(f'/books/edit/{book}').get_data(as_text=True)
    assert f'data-url="/photos/photo/{photo}/crop"' in html and 'data-click="cropPhoto"' in html
    geom = {'v': 1, 'rotate': 0, 'mode': 'rect', 'box': [0.25, 0.0, 0.5, 1.0]}
    r = client.post(f'/photos/photo/{photo}/crop', json={'geometry': geom})
    assert r.status_code == 200 and r.get_json()['success']
    new = scalar(db, 'SELECT path FROM item_photos WHERE id = ?', photo)
    assert new != old and not (static_root / old).exists()
    with Image.open(static_root / new) as img:
        assert img.size == (400, 600)
    assert client.post(f'/photos/photo/{photo}/crop', json={'geometry': {'v': 9}}).status_code == 400
    client.get('/auth/logout')
    login(client, 'carol')
    assert client.post(f'/photos/photo/{photo}/crop', json={'geometry': geom}).status_code == 404


# --- Books on the Shelves heading (ROADMAP 16.0a) -----------------------------

def heading_books_of(html):
    return re.findall(r'<span class="heading-book"[^>]*>.*?item3d-front">\s*<img src="([^"]+)"', html, re.S)


def test_your_3d_books_stand_on_the_shelves_heading(client, db, people, static_root):
    """Shelf style, your own Shelves page: the books of yours that turn in
    3D stand on the heading, one by one as they get their photos. They're
    decoration: no links, hidden from screen readers. A book without all
    its photos, one that left the shelf and other people's aren't there;
    the same ones stand there for the whole visit."""
    bob = people['bob']
    db.execute("UPDATE users SET theme_style = 'shelf' WHERE id = ?", (bob,))
    ready = add_book(db, bob, cover=real_cover(static_root, 'a.jpg'))
    half = add_book(db, bob, cover=real_cover(static_root, 'b.jpg'))
    gone = add_book(db, bob, cover=real_cover(static_root, 'c2.jpg'))
    login(client, 'bob')
    assert 'data-heading-books' not in client.get('/base/index').get_data(as_text=True)

    for book in (ready, gone):
        upload(client, book, 'back', jpeg_bytes((400, 600)))
        upload(client, book, 'spine', jpeg_bytes((60, 600)))
    upload(client, half, 'back', jpeg_bytes((400, 600)))
    db.execute("UPDATE books SET removed_at = CURRENT_TIMESTAMP WHERE id = ?", (gone,))
    db.commit()
    html = client.get('/base/index').get_data(as_text=True)
    assert heading_books_of(html) == ['/static/uploads/a.jpg']
    start = html.index('<div class="heading-books')
    group = html[start:html.index('<h1', start)]
    assert 'heading-books-left" aria-hidden="true"' in group and '<a ' not in group
    assert 'heading-books-right' not in group      # one book: one side

    upload(client, half, 'spine', jpeg_bytes((60, 600)))
    first = heading_books_of(client.get('/base/index').get_data(as_text=True))
    assert sorted(first) == ['/static/uploads/a.jpg', '/static/uploads/b.jpg']
    assert heading_books_of(client.get('/base/index').get_data(as_text=True)) == first

    # Only on your own Shelves, and only in the style that has a shelf
    assert 'data-heading-books' not in client.get('/base/shared-library').get_data(as_text=True)
    db.execute("UPDATE users SET theme_style = 'house' WHERE id = ?", (bob,))
    db.commit()
    assert 'data-heading-books' not in client.get('/base/index').get_data(as_text=True)


def test_heading_shelf_is_never_crammed(client, app, db, people, static_root):
    """At most HEADING_BOOKS of them, however many could stand there;
    spines out, upright, split evenly either side of the title, five a
    side at most (Phil, 2026-11-15)."""
    from utils import item3d, photos
    bob = people['bob']
    cover = real_cover(static_root, 'k.jpg')
    for kind in ('back', 'spine'):
        (static_root / 'uploads' / f'{kind}.jpg').write_bytes(jpeg_bytes((60, 600)).getvalue())

    def one_more():
        book = add_book(db, bob, cover=cover)
        for kind in ('back', 'spine'):
            photos.add(db, book, kind, f'uploads/{kind}.jpg')
        db.commit()

    with app.test_request_context():
        for _ in range(3):
            one_more()
        three = [m['faces'] for m in item3d.heading_books(db, bob, 7)]
        assert len(three) == 3
        for _ in range(item3d.HEADING_BOOKS + 2):
            one_more()
        assert len(item3d.heading_books(db, bob, 7)) == item3d.HEADING_BOOKS
    db.execute("UPDATE users SET theme_style = 'shelf' WHERE id = ?", (bob,))
    db.commit()
    login(client, 'bob')
    html = client.get('/base/index').get_data(as_text=True)
    left = html[html.index('heading-books-left'):html.index('heading-books-right')]
    right = html[html.index('heading-books-right'):html.index('<h1', html.index('heading-books-right'))]
    assert left.count('class="heading-book"') == right.count('class="heading-book"') == 5


def test_records_stand_at_their_real_sizes(client, db, people):
    """The Music grid carries each record's format, and the Shelf style
    (only) stands each format smaller than a 12" sleeve, in the real order
    but not to scale (Phil, 2026-11-15)."""
    for fmt in ('LP', 'CD', '7in'):
        book = add_book(db, people['bob'], title=f'Album {fmt}')
        db.execute("UPDATE books SET media_type = 'record', format = ? WHERE id = ?", (fmt, book))
    db.commit()
    login(client, 'bob')
    grid = client.get('/records/').get_data(as_text=True)
    for fmt in ('LP', 'CD', '7in'):
        assert f'<div class="book-item group" data-format="{fmt}"' in grid
    css = open(os.path.join(os.path.dirname(__file__), '..', 'static', 'styles.css')).read()
    sizes = dict(re.findall(r':root\[data-style="shelf"\] #book-container\[data-media="record"\] \.book-item\[data-format="(\w+)"\] \{ --size: ([.\d]+); \}', css))
    assert sizes == {'10in': '.9', '7in': '.72', 'CD': '.6', 'Cassette': '.55'}
    # and only there: no other style sizes records by format
    assert css.count('--size: ') == 5
    assert 'max-height: calc(var(--cover-h) * var(--size, 1))' in css
