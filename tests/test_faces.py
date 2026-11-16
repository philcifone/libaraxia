"""Placeholder faces (ROADMAP 16.0c, docs/FACES-SPEC.md; utils/faces.py,
blueprints/faces.py): the admin's library and sets, an owner's choices,
and which image each face shows."""
import os
import re

from conftest import add_book, login, scalar
from test_photos import jpeg_bytes, upload, real_cover, add_item, box_of


def add_placeholder(client, medium, kind, name='Plastic', size=(400, 60)):
    return client.post('/faces/admin/add', data={'medium': medium, 'kind': kind, 'name': name,
                                                 'photo': (jpeg_bytes(size), 'p.jpg')},
                       content_type='multipart/form-data')


def placeholder_id(db, name):
    return scalar(db, 'SELECT id FROM face_placeholders WHERE name = ?', name)


def make_set(client, db, medium, name, members):
    """A set of `medium` with {kind: placeholder name} members. Returns its id."""
    client.post('/faces/admin/sets/add', data={'medium': medium, 'name': name})
    set_id = scalar(db, 'SELECT id FROM face_sets WHERE name = ?', name)
    data = {'name': name, **{f'face_{k}': placeholder_id(db, n) for k, n in members.items()}}
    client.post(f'/faces/admin/sets/{set_id}/update', data=data)
    return set_id


def test_admin_only(client, db, people, static_root):
    login(client, 'bob')
    assert client.get('/faces/admin').status_code in (302, 403)
    assert add_placeholder(client, 'vhs', 'top').status_code in (302, 403)
    assert scalar(db, 'SELECT COUNT(*) FROM face_placeholders') == 0
    login(client, 'alice')
    page = client.get('/faces/admin').get_data(as_text=True)
    # one tab per medium, VHS sleeves and clamshells together
    assert 'id="tab-medium-vhs"' in page and 'data-face-medium="vhs"' in page and 'Fore-edge' in page
    assert 'vhs_clamshell' not in page and 'vhs_sleeve' not in page
    # linked from Settings' Maintenance
    assert '/faces/admin' in client.get('/user/settings').get_data(as_text=True)


def test_upload_rename_crop_delete(client, db, people, static_root):
    login(client, 'alice')
    r = add_placeholder(client, 'vhs', 'top', 'Black clamshell')
    assert r.status_code == 302 and r.headers['Location'].endswith('#medium-vhs')
    pid = placeholder_id(db, 'Black clamshell')
    path = scalar(db, 'SELECT path FROM face_placeholders WHERE id = ?', pid)
    assert path.startswith('uploads/faces/') and (static_root / path).is_file()
    # a medium or face that isn't one is refused
    assert add_placeholder(client, 'laserdisc', 'top').status_code == 400
    assert add_placeholder(client, 'vhs', 'back').status_code == 400

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


def test_upload_turns_strips_the_right_way(client, db, people, static_root):
    """A top or bottom lies wide and a spine or side stands tall, whichever
    way the photo was taken."""
    from PIL import Image
    login(client, 'alice')
    add_placeholder(client, 'vhs', 'top', 'Upright top', size=(60, 400))
    add_placeholder(client, 'vhs', 'side', 'Wide side', size=(400, 60))
    add_placeholder(client, 'vhs', 'bottom', 'Wide bottom', size=(400, 60))
    for name, (w, h) in (('Upright top', (400, 60)), ('Wide side', (60, 400)), ('Wide bottom', (400, 60))):
        path = scalar(db, 'SELECT path FROM face_placeholders WHERE name = ?', name)
        with Image.open(static_root / path) as img:
            assert img.size == (w, h), name


def test_sets(client, db, people, static_root):
    login(client, 'alice')
    for kind, name in (('top', 'Top'), ('side', 'Side'), ('bottom', 'Bottom')):
        add_placeholder(client, 'vhs', kind, name)
    add_placeholder(client, 'dvd', 'top', 'DVD top')
    first = make_set(client, db, 'vhs', 'White clamshell', {'top': 'Top', 'side': 'Side', 'bottom': 'Bottom'})
    assert scalar(db, 'SELECT COUNT(*) FROM face_set_members WHERE set_id = ?', first) == 3
    second = make_set(client, db, 'vhs', 'Nickelodeon', {'bottom': 'Bottom'})
    # a placeholder of another medium, or of another face, doesn't fit
    client.post(f'/faces/admin/sets/{first}/update',
                data={'name': 'White clamshell', 'face_top': placeholder_id(db, 'DVD top')})
    client.post(f'/faces/admin/sets/{first}/update',
                data={'name': 'White clamshell', 'face_top': placeholder_id(db, 'Side')})
    assert scalar(db, 'SELECT COUNT(*) FROM face_set_members WHERE set_id = ?', first) == 3
    page = client.get('/faces/admin').get_data(as_text=True)
    assert f'data-face-set="{first}"' in page and f'data-face-set="{second}"' in page
    client.post(f'/faces/admin/sets/{second}/delete')
    assert scalar(db, 'SELECT COUNT(*) FROM face_sets') == 1


def test_faces_resolve_photo_then_choice(client, db, people, static_root):
    """Spec section 5: nothing is automatic, so a cover-only VHS keeps the
    plain look until its owner picks a set; a later set replaces the faces
    it has; a top photo makes it a sleeve, whose right side is its left
    side's photo; a photo beats a choice; deleting a placeholder drops the
    choice."""
    login(client, 'alice')
    for kind, name in (('top', 'Shell top'), ('side', 'Shell side'), ('bottom', 'Shell bottom')):
        add_placeholder(client, 'vhs', kind, name)
    add_placeholder(client, 'vhs', 'bottom', 'Orange tape')
    shell = make_set(client, db, 'vhs', 'White clamshell',
                     {'top': 'Shell top', 'side': 'Shell side', 'bottom': 'Shell bottom'})
    nick = make_set(client, db, 'vhs', 'Nickelodeon', {'bottom': 'Orange tape'})
    url = {n: '/static/' + scalar(db, 'SELECT path FROM face_placeholders WHERE name = ?', n)
           for n in ('Shell top', 'Shell side', 'Shell bottom', 'Orange tape')}

    bob = people['bob']
    login(client, 'bob')
    vhs = add_item(db, bob, 'video', 'VHS', real_cover(static_root, 'v.jpg', (400, 720)))

    def stand():
        page = client.get(f'/videos/{vhs}').get_data(as_text=True)
        tag = page[page.index('class="cover-stand'):]
        return tag[:tag.index('>')]
    # A cover only, nothing picked: the plain look
    assert '/static/uploads/faces/' not in stand()
    # The owner picks the clamshell set: its top and side on the flat box
    edit = client.get(f'/videos/edit/{vhs}').get_data(as_text=True)
    assert f'value="{shell}"' in edit and f'value="{nick}"' in edit
    client.post(f'/faces/item/{vhs}/set', data={'set_id': shell})
    assert url['Shell top'] in stand() and url['Shell side'] in stand()
    # The 3D box: back and a left side; the clamshell's plastic for the rest
    upload(client, vhs, 'back', jpeg_bytes((400, 720)))
    upload(client, vhs, 'spine', jpeg_bytes((200, 720)))
    box = box_of(client.get(f'/videos/{vhs}').get_data(as_text=True))
    for name in ('Shell top', 'Shell side', 'Shell bottom'):
        assert url[name] in box
    # The Nickelodeon set: its bottom replaces the clamshell's, the rest stay
    client.post(f'/faces/item/{vhs}/set', data={'set_id': nick})
    box = box_of(client.get(f'/videos/{vhs}').get_data(as_text=True))
    assert url['Orange tape'] in box and url['Shell bottom'] not in box and url['Shell top'] in box
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
    # Deleting a placeholder drops the choices of it
    login(client, 'alice')
    client.post(f'/faces/admin/{placeholder_id(db, "Orange tape")}/delete')
    assert scalar(db, "SELECT COUNT(*) FROM item_faces WHERE kind = 'bottom'") == 0


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
    # back to the plain look
    client.post(f'/faces/item/{dvd}/choose', data={'kind': 'top', 'placeholder_id': ''})
    assert scalar(db, 'SELECT COUNT(*) FROM item_faces') == 0


def test_orphan_cleanup_keeps_placeholders(app, db, people, static_root, monkeypatch, tmp_path):
    from utils import image_utils
    db.execute("INSERT INTO face_placeholders (medium, kind, name, path) "
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
    add_placeholder(client, 'vhs', 'top', 'Shell top')
    add_placeholder(client, 'dvd', 'side', 'Clear edge', size=(40, 400))
    shell = make_set(client, db, 'vhs', 'Clamshell', {'top': 'Shell top'})
    clear = make_set(client, db, 'dvd', 'Clear case', {'side': 'Clear edge'})
    login(client, 'bob')
    page = client.get('/videos/add').get_data(as_text=True)
    assert 'name="face_set"' in page and f'<option value="{shell}"' in page and 'label="VHS"' in page
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


def test_vhs_tapes_stand_on_the_movies_heading(client, db, people, static_root):
    """Shelf style, your own Movies page (16.0c): your VHS tapes that turn
    in 3D stand on the heading as books do on Shelves; a DVD doesn't, nor
    a tape still missing its side, and not on the household's page."""
    from test_photos import heading_books_of
    bob = people['bob']
    db.execute("UPDATE users SET theme_style = 'shelf' WHERE id = ?", (bob,))
    vhs = add_item(db, bob, 'video', 'VHS', real_cover(static_root, 'v.jpg', (400, 720)))
    half = add_item(db, bob, 'video', 'VHS', real_cover(static_root, 'h.jpg', (400, 720)))
    dvd = add_item(db, bob, 'video', 'DVD', real_cover(static_root, 'd.jpg', (400, 560)))
    login(client, 'bob')
    for item, side in ((vhs, 'side'), (dvd, 'spine')):
        upload(client, item, 'back', jpeg_bytes((400, 720)))
        upload(client, item, side, jpeg_bytes((140, 720)))
    upload(client, half, 'back', jpeg_bytes((400, 720)))
    html = client.get('/videos/').get_data(as_text=True)
    assert heading_books_of(html) == ['/static/uploads/v.jpg']
    assert 'item3d-tape' in html[html.index('data-heading-books'):]
    assert 'data-heading-books' not in client.get('/records/').get_data(as_text=True)
    assert 'data-heading-books' not in client.get('/videos/shared').get_data(as_text=True)


def test_a_cd_spine_placeholder_makes_a_jewel_case(client, db, people, static_root):
    """A CD with front and back only is a paper sleeve; with a CD spine
    placeholder picked it's a jewel case, as thick
    as one, the placeholder on both ends."""
    login(client, 'alice')
    add_placeholder(client, 'cd', 'spine', 'Clear spine', size=(40, 480))
    make_set(client, db, 'cd', 'Jewel case', {'spine': 'Clear spine'})
    login(client, 'bob')
    cd = add_item(db, people['bob'], 'record', 'CD', real_cover(static_root, 'cd.jpg', (500, 440)))
    upload(client, cd, 'back', jpeg_bytes((500, 440)))
    assert 'item3d-paper' in box_of(client.get(f'/records/{cd}').get_data(as_text=True))
    client.post(f'/faces/item/{cd}/choose', data={'kind': 'spine', 'placeholder_id': placeholder_id(db, 'Clear spine')})
    box = box_of(client.get(f'/records/{cd}').get_data(as_text=True))
    url = '/static/' + scalar(db, 'SELECT path FROM face_placeholders')
    assert 'item3d-paper' not in box and '--dr: 0.083;' in box and box.count(url) == 2
    # and the spine is on the flat box's right side, on the grid and the
    # item page (Phil, 2026-11-16, as a VHS); a spine photo beats it
    card = re.search(r'<div class="book-item group" data-format="CD"[^>]*>',
                     client.get('/records/').get_data(as_text=True)).group(0)
    assert f'--face-side: url(&#34;{url}&#34;)' in card
    upload(client, cd, 'spine', jpeg_bytes((40, 480)))
    page = client.get(f'/records/{cd}').get_data(as_text=True)
    stand = page[page.index('class="cover-stand'):]
    stand = stand[:stand.index('>')]
    assert '--face-side: url(&#34;/static/uploads/photos/' in stand


def test_bulk_edit_applies_a_set_and_undoes_it(client, db, people, static_root):
    """Bulk edit's Placeholder set (16.0c): the More menu offers it where
    the section has sets; it fills each selected tape's faces, skips items
    of another medium and items that aren't yours, and undoes to what each
    had before."""
    login(client, 'alice')
    for kind, name in (('top', 'Shell top'), ('side', 'Shell side'), ('bottom', 'Shell bottom')):
        add_placeholder(client, 'vhs', kind, name)
    add_placeholder(client, 'vhs', 'bottom', 'Orange tape')
    shell = make_set(client, db, 'vhs', 'White clamshell',
                     {'top': 'Shell top', 'side': 'Shell side', 'bottom': 'Shell bottom'})
    bob, alice = people['bob'], people['alice']
    tapes = [add_item(db, bob, 'video', 'VHS', None) for _ in range(2)]
    dvd = add_item(db, bob, 'video', 'DVD', None)
    hers = add_item(db, alice, 'video', 'VHS', None)
    login(client, 'bob')
    # one tape already has a bottom picked: it's replaced, and comes back on undo
    client.post(f'/faces/item/{tapes[0]}/choose',
                data={'kind': 'bottom', 'placeholder_id': placeholder_id(db, 'Orange tape')})

    assert 'data-action="faces"' in client.get('/videos/').get_data(as_text=True)
    assert 'data-action="faces"' not in client.get('/records/').get_data(as_text=True)   # no record sets
    opts = client.get('/bulk/options?type=video').get_json()
    assert opts['face_sets'] == [{'id': shell, 'name': 'White clamshell (VHS)'}]

    ids = [*tapes, dvd, hers]
    plan = client.post('/bulk/plan', json={'action': 'faces', 'params': {'set_id': shell}, 'ids': ids}).get_json()
    assert plan['success'] and plan['plan']['changes'] == 2
    reasons = {s['reason'] for s in plan['plan']['skipped']}
    assert reasons == {'Not for VHS', 'Not yours'}
    r = client.post('/bulk/apply', json={'action': 'faces', 'params': {'set_id': shell}, 'ids': ids,
                                         'fingerprint': plan['plan']['fingerprint']}).get_json()
    assert r['success'] and r['changed'] == 2
    picked = lambda book: {row[0]: row[1] for row in db.execute(
        'SELECT kind, placeholder_id FROM item_faces WHERE book_id = ?', (book,))}
    want = {k: placeholder_id(db, n) for k, n in (('top', 'Shell top'), ('side', 'Shell side'),
                                                  ('bottom', 'Shell bottom'))}
    assert picked(tapes[0]) == want and picked(tapes[1]) == want
    assert picked(dvd) == {} and picked(hers) == {}

    client.post(f'/bulk/{r["edit_id"]}/undo')
    assert picked(tapes[0]) == {'bottom': placeholder_id(db, 'Orange tape')}
    assert picked(tapes[1]) == {}
