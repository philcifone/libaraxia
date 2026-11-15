"""Item photos (ROADMAP 16.0a, docs/PHOTOS-VALUE-SPEC.md sections 3 and 11)."""
import io
import os

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


def test_spine_is_books_only(client, db, people):
    record = db.execute("INSERT INTO books (title, author, added_by, media_type, format) "
                        "VALUES ('Blue', 'Joni', ?, 'record', 'LP')", (people['bob'],)).lastrowid
    db.commit()
    login(client, 'bob')
    assert upload(client, record, 'spine', jpeg_bytes()).status_code == 404
    assert upload(client, record, 'back', jpeg_bytes()).status_code == 200


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
