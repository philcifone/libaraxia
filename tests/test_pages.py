"""Registration, login, and every page loading."""
import pytest

from conftest import add_book, add_review, add_user, login, scalar


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
SKIP = {'static', 'auth.logout', 'auth.verify_email'}


def test_every_page_loads(app, client, db, people):
    """Every GET route answers without a server error, as an admin with real-ish data."""
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
        checked.append(url)
    assert len(checked) > 35

    extra = ['/base/index?show_removed=1', f'/books/book/{removed}', '/user/alice', '/user/bob',
             '/base/library/carol', '/wishlist/user/carol', '/books/search?q=dune',
             '/admin/users/%d/removal' % alice]
    for url in extra:
        assert client.get(url).status_code < 400, url


def test_missing_book_is_404(client, people):
    login(client, 'alice')
    assert client.get('/books/book/99999').status_code == 404


def test_orphaned_images_page_without_uploads_folder(app, client, people, tmp_path, monkeypatch):
    """Regression (found by CI): a fresh checkout has no static/uploads/, and the
    admin orphaned-images page crashed on the missing total_size_mb."""
    monkeypatch.setattr(app, 'root_path', str(tmp_path))   # tmp_path/static/uploads doesn't exist
    login(client, 'alice')
    assert client.get('/admin/orphaned_images').status_code == 200
