"""Registration, login, and every page loading."""
import pytest

from conftest import add_book, add_review, add_user, login, scalar
from test_layout import unbalanced_tags


def test_root_sends_first_visitor_to_register(client):
    r = client.get('/')
    assert r.status_code == 302 and '/auth/register' in r.location


def test_first_user_becomes_admin_and_can_log_in(client, db):
    r = client.post('/auth/register', data={'username': 'first', 'email': 'first@example.test',
                                            'password': 'long-enough-pw'})
    assert r.status_code == 302
    r = client.post('/auth/register', data={'username': 'second', 'email': 'second@example.test',
                                            'password': 'long-enough-pw'})
    assert r.status_code == 302
    admins = {row['username']: row['is_admin'] for row in db.execute('SELECT username, is_admin FROM users')}
    assert admins == {'first': 1, 'second': 0}

    r = client.post('/auth/login', data={'email': 'second@example.test', 'password': 'long-enough-pw'})
    assert r.status_code == 302
    assert client.get('/base/index').status_code == 200


@pytest.mark.parametrize('username', ['<script>', 'ab', 'has space', 'x' * 31])
def test_register_rejects_bad_usernames(client, db, username):
    client.post('/auth/register', data={'username': username, 'email': 'x@example.test',
                                        'password': 'long-enough-pw'})
    assert scalar(db, 'SELECT COUNT(*) FROM users') == 0


def test_register_rejects_short_password(client, db):
    client.post('/auth/register', data={'username': 'shorty', 'email': 's@example.test', 'password': 'short'})
    assert scalar(db, 'SELECT COUNT(*) FROM users') == 0


def test_wrong_password_does_not_log_in(client, people):
    r = client.post('/auth/login', data={'email': 'alice@example.test', 'password': 'wrong-password'})
    assert r.status_code == 200
    assert client.get('/base/index').status_code == 302  # back to login


def test_deactivated_user_cannot_log_in_and_is_logged_out(client, db, people):
    login(client, 'bob')
    assert client.get('/base/index').status_code == 200
    db.execute('UPDATE users SET is_active = 0 WHERE id = ?', (people['bob'],))
    db.commit()
    assert client.get('/base/index').status_code == 302  # existing session ends
    r = client.post('/auth/login', data={'email': 'bob@example.test', 'password': 'correct-horse-battery'})
    assert client.get('/base/index').status_code == 302


def test_pages_need_login(client, people):
    for url in ['/base/index', '/books/add', '/admin/settings', '/user/export_data']:
        r = client.get(url)
        assert r.status_code == 302 and '/auth/login' in r.location, url


def test_admin_pages_refuse_non_admins(client, people):
    login(client, 'bob')
    for url in ['/admin/settings', '/admin/unowned_books']:
        r = client.get(url)
        assert r.status_code in (302, 403), url


def test_security_headers(client):
    r = client.get('/auth/login')
    assert r.headers['X-Content-Type-Options'] == 'nosniff'
    assert r.headers['X-Frame-Options'] == 'SAMEORIGIN'


# Routes that are GET but act, or need arguments filled in below.
# books.thumbnail needs a ?url= and 404s without one; tests/test_csp.py covers it.
# videos.lookup needs ?barcode= or ?title= and answers 400 without; test_videos.py covers it.
SKIP = {'static', 'auth.verify_email', 'books.thumbnail', 'videos.lookup', 'videos.search'}


def test_every_page_loads(app, client, db, people):
    """Every GET route answers without a server error, as an admin with real-ish
    data, and every HTML page closes the tags it opens (see test_layout.py)."""
    alice, bob, carol = people['alice'], people['bob'], people['carol']
    book = add_book(db, alice, 'Dune', 'Frank Herbert')
    add_review(db, bob, book)
    add_book(db, None, 'Orphan', 'Nobody')
    removed = add_book(db, alice, 'Given away', 'Someone')
    db.execute("UPDATE books SET removed_at = CURRENT_TIMESTAMP WHERE id = ?", (removed,))
    shelf = db.execute("INSERT INTO user_collections (user_id, name) VALUES (?, 'Favourites')", (alice,)).lastrowid
    db.execute('INSERT INTO collection_books (collection_id, book_id) VALUES (?, ?)', (shelf, book))
    db.commit()
    login(client, 'alice')

    filled = {
        'id': book, 'book_id': book, 'collection_id': shelf, 'user_id': bob,
        'username': 'carol', 'status': 'read',
    }
    checked = []
    for rule in app.url_map.iter_rules():
        if 'GET' not in rule.methods or rule.endpoint in SKIP:
            continue
        url = rule.build({a: filled[a] for a in rule.arguments})[1]
        r = client.get(url)
        assert r.status_code < 400, f'{url} -> {r.status_code}'
        if r.status_code == 200 and r.mimetype == 'text/html':
            assert unbalanced_tags(r.get_data(as_text=True)) == [], url
        checked.append(url)
    assert len(checked) > 35

    # Videos (Phase 8): the routes above get a book id and redirect, so check a real one
    video = db.execute("INSERT INTO books (title, author, runtime_minutes, barcode, format, added_by, media_type) "
                       "VALUES ('Jaws', 'Steven Spielberg', 124, '0012345678905', 'VHS', ?, 'video')",
                       (alice,)).lastrowid
    db.commit()
    extra = ['/base/index?show_removed=1', f'/books/book/{removed}', '/user/alice', '/user/bob',
             '/base/library/carol', '/wishlist/user/carol', '/books/search?q=dune',
             '/admin/users/%d/removal' % alice,
             f'/videos/{video}', f'/videos/edit/{video}', f'/read/rate_review/{video}',
             '/videos/?q=jaws&format=VHS&sort_by=runtime_minutes&sort_order=desc',
             '/videos/add?barcode=012345678905', '/videos/user/alice']
    for url in extra:
        r = client.get(url)
        assert r.status_code < 400, url
        assert unbalanced_tags(r.get_data(as_text=True)) == [], url


def test_every_template_page_extends_base():
    """Phase 6: one layout. Every full-page template extends base.html; the
    partials (leading underscore) are included, never extended."""
    import pathlib
    templates = pathlib.Path(__file__).resolve().parent.parent / 'templates'
    pages = [p for p in templates.rglob('*.html') if not p.name.startswith('_') and p.name != 'base.html']
    assert len(pages) > 20
    standalone = [str(p.relative_to(templates)) for p in pages
                  if not p.read_text().startswith("{% extends 'base.html' %}")]
    assert standalone == []


def test_pages_render_the_shared_layout(client, people):
    """base.html supplies the CSRF meta tag and common.js; auth pages skip the sidebar."""
    html = client.get('/auth/login').get_data(as_text=True)
    assert html.count('<html') == 1 and 'name="csrf-token"' in html and 'common.js' in html
    assert 'id="hamburger"' not in html
    login(client, 'alice')
    html = client.get('/base/index').get_data(as_text=True)
    assert html.count('<html') == 1 and 'id="hamburger"' in html and 'sidebar.js' in html


def test_missing_book_is_404(client, people):
    login(client, 'alice')
    assert client.get('/books/book/99999').status_code == 404


def test_orphaned_images_page_without_uploads_folder(app, client, people, tmp_path, monkeypatch):
    """Regression (found by CI): a fresh checkout has no static/uploads/, and the
    admin orphaned-images page crashed on the missing total_size_mb."""
    monkeypatch.setattr(app, 'root_path', str(tmp_path))   # tmp_path/static/uploads doesn't exist
    login(client, 'alice')
    assert client.get('/admin/orphaned_images').status_code == 200


def test_no_global_rate_limit_but_login_is_limited(client, db, people, monkeypatch):
    """Phase 4: browsing isn't rate limited (the old 50/hour global default
    caused 429s); login still is. Limits are off in tests, so switch them on."""
    from utils.rate_limiting import limiter
    monkeypatch.setattr(limiter, 'enabled', True)
    limiter.reset()
    try:
        login(client, 'bob')
        for _ in range(60):
            assert client.get('/base/index').status_code == 200
        client.post('/auth/logout')
        codes = [client.post('/auth/login', data={'email': 'x@example.test', 'password': 'no'}).status_code
                 for _ in range(12)]
        assert 429 in codes
    finally:
        limiter.reset()


def test_scanner_scripts_are_served_locally(client, db, people):
    """Both scanning pages load quagga2 and the shared scanner from static/."""
    login(client, 'bob')
    for page in ('/books/add', '/videos/add', '/wishlist/add?type=book'):
        html = client.get(page, follow_redirects=True).get_data(as_text=True)
        assert 'vendor/quagga2-1.12.1.min.js' in html and 'cdnjs' not in html, page
        assert html.index('vendor/quagga2-1.12.1.min.js') < html.index('/static/scanner.js'), page
        assert 'id="camera-select"' in html, page
    for path in ('/static/vendor/quagga2-1.12.1.min.js', '/static/scanner.js'):
        assert client.get(path).status_code == 200, path


def test_edit_form_keeps_subtitle_and_genre(client, db, people):
    """Regression (Phase 6): the edit form tested `book.details` (always
    undefined) instead of `book_details`, so the subtitle field rendered empty
    and saving the form wiped the book's subtitle."""
    book = add_book(db, people['alice'], 'Dune', 'Frank Herbert')
    db.execute("UPDATE books SET subtitle = 'Book One', genre = 'Science Fiction' WHERE id = ?", (book,))
    db.commit()
    login(client, 'alice')
    html = client.get(f'/books/edit/{book}').get_data(as_text=True)
    assert 'value="Book One"' in html and 'value="Science Fiction"' in html and 'value="Dune"' in html


def test_book_grid_uses_named_columns(client, db, people):
    """Templates read rows by column name, so the grid links to the right book."""
    book = add_book(db, people['alice'], 'Dune', 'Frank Herbert')
    login(client, 'alice')
    html = client.get('/base/index').get_data(as_text=True)
    assert f'href="/books/book/{book}"' in html and 'by Frank Herbert' in html
