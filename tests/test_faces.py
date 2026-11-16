"""Placeholder faces (ROADMAP 16.0c, docs/FACES-SPEC.md; utils/faces.py,
blueprints/faces.py): the admin's library and sets, an owner's choices,
and which image each face shows."""
import os
import re

from conftest import add_book, login, scalar
from test_photos import jpeg_bytes, upload, real_cover, add_item, box_of


def add_placeholder(client, body, kind, name='Plastic', size=(400, 60)):
    return client.post('/faces/admin/add', data={'body': body, 'kind': kind, 'name': name,
                                                 'photo': (jpeg_bytes(size), 'p.jpg')},
                       content_type='multipart/form-data')


def placeholder_id(db, name):
    return scalar(db, 'SELECT id FROM face_placeholders WHERE name = ?', name)


def make_set(client, db, body, name, members, default=False):
    """A set of `body` with {kind: placeholder name} members. Returns its id."""
    client.post('/faces/admin/sets/add', data={'body': body, 'name': name})
    set_id = scalar(db, 'SELECT id FROM face_sets WHERE name = ?', name)
    data = {'name': name, **{f'face_{k}': placeholder_id(db, n) for k, n in members.items()}}
    if default:
        data['is_default'] = '1'
    client.post(f'/faces/admin/sets/{set_id}/update', data=data)
    return set_id


def test_admin_only(client, db, people, static_root):
    login(client, 'bob')
    assert client.get('/faces/admin').status_code in (302, 403)
    assert add_placeholder(client, 'vhs_clamshell', 'top').status_code in (302, 403)
    assert scalar(db, 'SELECT COUNT(*) FROM face_placeholders') == 0
    login(client, 'alice')
    page = client.get('/faces/admin').get_data(as_text=True)
    assert 'data-face-body="vhs_clamshell"' in page and 'Fore-edge' in page
    # linked from Settings' Maintenance
    assert '/faces/admin' in client.get('/user/settings').get_data(as_text=True)


def test_upload_rename_crop_delete(client, db, people, static_root):
    login(client, 'alice')
    r = add_placeholder(client, 'vhs_clamshell', 'top', 'Black clamshell')
    assert r.status_code == 302 and r.headers['Location'].endswith('#body-vhs_clamshell')
    pid = placeholder_id(db, 'Black clamshell')
    path = scalar(db, 'SELECT path FROM face_placeholders WHERE id = ?', pid)
    assert path.startswith('uploads/faces/') and (static_root / path).is_file()
    # a body or face that isn't one is refused
    assert add_placeholder(client, 'laserdisc', 'top').status_code == 400
    assert add_placeholder(client, 'vhs_clamshell', 'back').status_code == 400

    client.post(f'/faces/admin/{pid}/rename', data={'name': '  Black   clamshell top '})
    assert scalar(db, 'SELECT name FROM face_placeholders WHERE id = ?', pid) == 'Black clamshell top'

    geom = {'v': 1, 'rotate': 0, 'mode': 'rect', 'box': [0, 0, 0.5, 1.0]}
    r = client.post(f'/faces/admin/{pid}/crop', json={'geometry': geom})
    assert r.status_code == 200 and r.get_json()['success']
    new = scalar(db, 'SELECT path FROM face_placeholders WHERE id = ?', pid)
    assert new != path and not (static_root / path).exists() and (static_root / new).is_file()

    client.post(f'/faces/admin/{pid}/delete')
    assert scalar(db, 'SELECT COUNT(*) FROM face_placeholders') == 0
    assert not (static_root / new).exists()


def test_sets_and_one_default_per_body(client, db, people, static_root):
    login(client, 'alice')
    for kind, name in (('top', 'Top'), ('side', 'Side'), ('bottom', 'Bottom')):
        add_placeholder(client, 'vhs_clamshell', kind, name)
    add_placeholder(client, 'dvd', 'top', 'DVD top')
    first = make_set(client, db, 'vhs_clamshell', 'Clamshell', {'top': 'Top', 'side': 'Side', 'bottom': 'Bottom'},
                     default=True)
    assert scalar(db, 'SELECT COUNT(*) FROM face_set_members WHERE set_id = ?', first) == 3
    second = make_set(client, db, 'vhs_clamshell', 'Nickelodeon', {'bottom': 'Bottom'}, default=True)
    assert [r[0] for r in db.execute('SELECT id FROM face_sets WHERE is_default = 1')] == [second]
    # a placeholder of another body, or of another face, doesn't fit
    client.post(f'/faces/admin/sets/{first}/update',
                data={'name': 'Clamshell', 'face_top': placeholder_id(db, 'DVD top')})
    client.post(f'/faces/admin/sets/{first}/update',
                data={'name': 'Clamshell', 'face_top': placeholder_id(db, 'Side')})
    assert scalar(db, 'SELECT COUNT(*) FROM face_set_members WHERE set_id = ?', first) == 3
    page = client.get('/faces/admin').get_data(as_text=True)
    assert f'data-face-set="{first}"' in page and f'data-face-set="{second}"' in page
    client.post(f'/faces/admin/sets/{second}/delete')
    assert scalar(db, 'SELECT COUNT(*) FROM face_sets') == 1


def test_faces_resolve_photo_then_choice_then_default(client, db, people, static_root):
    """Spec section 5 and 6: a VHS without a top photo is a clamshell and
    falls back on the clamshell default; a top photo makes it a sleeve; the
    owner's choice beats the default; a photo beats both; deleting a
    placeholder drops the choice."""
    login(client, 'alice')
    for kind, name in (('top', 'Shell top'), ('side', 'Shell side'), ('bottom', 'Shell bottom')):
        add_placeholder(client, 'vhs_clamshell', kind, name)
    add_placeholder(client, 'vhs_sleeve', 'bottom', 'Orange tape')
    make_set(client, db, 'vhs_clamshell', 'Clamshell',
             {'top': 'Shell top', 'side': 'Shell side', 'bottom': 'Shell bottom'}, default=True)
    nick = make_set(client, db, 'vhs_sleeve', 'Nickelodeon', {'bottom': 'Orange tape'})
    url = {n: '/static/' + scalar(db, 'SELECT path FROM face_placeholders WHERE name = ?', n)
           for n in ('Shell top', 'Shell side', 'Shell bottom', 'Orange tape')}

    bob = people['bob']
    login(client, 'bob')
    vhs = add_item(db, bob, 'video', 'VHS', real_cover(static_root, 'v.jpg', (400, 720)))
    # A cover only: a clamshell, so its flat box shows the default's top and side
    page = client.get(f'/videos/{vhs}').get_data(as_text=True)
    stand = page[page.index('class="cover-stand'):]
    stand = stand[:stand.index('>')]
    assert url['Shell top'] in stand and url['Shell side'] in stand
    # The 3D box: back and a left side; the clamshell's plastic for the rest
    upload(client, vhs, 'back', jpeg_bytes((400, 720)))
    upload(client, vhs, 'spine', jpeg_bytes((200, 720)))
    box = box_of(client.get(f'/videos/{vhs}').get_data(as_text=True))
    for name in ('Shell top', 'Shell side', 'Shell bottom'):
        assert url[name] in box
    # The owner picks the Nickelodeon set: its bottom replaces the default's
    edit = client.get(f'/videos/edit/{vhs}').get_data(as_text=True)
    assert f'value="{nick}"' in edit
    client.post(f'/faces/item/{vhs}/set', data={'set_id': nick})
    box = box_of(client.get(f'/videos/{vhs}').get_data(as_text=True))
    assert url['Orange tape'] in box and url['Shell bottom'] not in box
    # A top photo: now a sleeve. Its right side is its left side's photo,
    # not the clamshell's, and its bottom is still the chosen tape
    upload(client, vhs, 'top', jpeg_bytes((400, 100)))
    box = box_of(client.get(f'/videos/{vhs}').get_data(as_text=True))
    assert url['Shell side'] not in box and url['Shell top'] not in box and url['Orange tape'] in box
    side = re.search(r'item3d-side">\s*<img src="([^"]+)"', box).group(1)
    assert side == re.search(r'item3d-spine">\s*<img src="([^"]+)"', box).group(1)
    # A bottom photo beats the choice
    upload(client, vhs, 'bottom', jpeg_bytes((400, 100)))
    assert url['Orange tape'] not in box_of(client.get(f'/videos/{vhs}').get_data(as_text=True))
    # Deleting the placeholder drops the choice
    login(client, 'alice')
    client.post(f'/faces/admin/{placeholder_id(db, "Orange tape")}/delete')
    assert scalar(db, 'SELECT COUNT(*) FROM item_faces') == 0


def test_choosing_is_for_the_owner_and_must_fit(client, db, people, static_root):
    login(client, 'alice')
    add_placeholder(client, 'dvd', 'top', 'Clear case top')
    add_placeholder(client, 'book', 'side', 'Deckle edge', size=(60, 400))
    clear, deckle = placeholder_id(db, 'Clear case top'), placeholder_id(db, 'Deckle edge')
    dvd = add_item(db, people['bob'], 'video', 'DVD', None)
    login(client, 'carol')                  # a friend of alice's, not bob's
    assert client.post(f'/faces/item/{dvd}/choose', data={'kind': 'top', 'placeholder_id': clear}).status_code == 404
    login(client, 'bob')
    # a book's placeholder doesn't fit a DVD
    r = client.post(f'/faces/item/{dvd}/choose', data={'kind': 'side', 'placeholder_id': deckle},
                    headers={'X-Requested-With': 'XMLHttpRequest'})
    assert r.status_code == 400
    r = client.post(f'/faces/item/{dvd}/choose', data={'kind': 'top', 'placeholder_id': clear})
    assert r.status_code == 302 and r.headers['Location'].endswith('#photos')
    assert scalar(db, 'SELECT placeholder_id FROM item_faces WHERE book_id = ?', dvd) == clear
    # shown on the edit page as the choice, and on the Movies grid's box
    edit = client.get(f'/videos/edit/{dvd}').get_data(as_text=True)
    assert f'<option value="{clear}" selected' in edit
    card = re.search(r'<div class="book-item group" data-format="DVD"[^>]*>',
                     client.get('/videos/').get_data(as_text=True)).group(0)
    assert '--face-top: url(' in card
    # back to the default
    client.post(f'/faces/item/{dvd}/choose', data={'kind': 'top', 'placeholder_id': ''})
    assert scalar(db, 'SELECT COUNT(*) FROM item_faces') == 0


def test_orphan_cleanup_keeps_placeholders(app, db, people, static_root, monkeypatch, tmp_path):
    from utils import image_utils
    db.execute("INSERT INTO face_placeholders (body, kind, name, path) "
               "VALUES ('dvd', 'top', 'x', 'uploads/faces/kept.jpg')")
    db.commit()
    with app.test_request_context():
        monkeypatch.setattr(app, 'root_path', str(tmp_path))
        faces_dir = tmp_path / 'static' / 'uploads' / 'faces'
        faces_dir.mkdir(parents=True)
        (faces_dir / 'kept.jpg').write_bytes(b'x')
        (faces_dir / 'stray.jpg').write_bytes(b'x')
        found = image_utils.find_orphaned_images(db)
    names = {os.path.basename(f['path'] if isinstance(f, dict) else f) for f in found['orphaned_files']}
    assert names == {'stray.jpg'}


def test_add_form_offers_and_applies_a_set(client, db, people, static_root):
    """Adding a VHS with the Clamshell set fills its faces; a set for
    another format (a DVD case on a VHS) is skipped with a note."""
    login(client, 'alice')
    add_placeholder(client, 'vhs_clamshell', 'top', 'Shell top')
    add_placeholder(client, 'dvd', 'side', 'Clear edge', size=(40, 400))
    shell = make_set(client, db, 'vhs_clamshell', 'Clamshell', {'top': 'Shell top'})
    clear = make_set(client, db, 'dvd', 'Clear case', {'side': 'Clear edge'})
    login(client, 'bob')
    page = client.get('/videos/add').get_data(as_text=True)
    assert 'name="face_set"' in page and f'<option value="{shell}"' in page and 'label="VHS clamshells"' in page
    assert 'name="face_set"' not in client.get('/records/add').get_data(as_text=True)   # no record sets
    base = {'title': 'Ghostbusters', 'author': 'Ivan Reitman', 'format': 'VHS'}
    client.post('/videos/add', data={**base, 'face_set': shell})
    vhs = scalar(db, "SELECT id FROM books WHERE title = 'Ghostbusters'")
    assert scalar(db, 'SELECT placeholder_id FROM item_faces WHERE book_id = ?', vhs) == placeholder_id(db, 'Shell top')
    r = client.post('/videos/add', data={**base, 'title': 'Big', 'face_set': clear}, follow_redirects=True)
    assert 'for this format, so it wasn' in r.get_data(as_text=True)
    big = scalar(db, "SELECT id FROM books WHERE title = 'Big'")
    assert scalar(db, 'SELECT COUNT(*) FROM item_faces WHERE book_id = ?', big) == 0


def test_add_book_with_a_page_set(client, db, people, static_root):
    login(client, 'alice')
    add_placeholder(client, 'book', 'side', 'Deckle edge', size=(40, 400))
    deckle = make_set(client, db, 'book', 'Deckle', {'side': 'Deckle edge'})
    login(client, 'bob')
    assert f'<option value="{deckle}"' in client.get('/books/add').get_data(as_text=True)
    client.post('/books/add', data={'submit_book': '1', 'title': 'Dune', 'author': 'Frank Herbert', 'face_set': deckle})
    book = scalar(db, "SELECT id FROM books WHERE title = 'Dune'")
    assert scalar(db, 'SELECT kind FROM item_faces WHERE book_id = ?', book) == 'side'
