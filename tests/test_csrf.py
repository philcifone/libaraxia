"""A stale or missing CSRF token (ROADMAP 14c): flash and go back, not a bare 400."""
from conftest import add_book, add_review, login, scalar


def test_tokens_do_not_expire_on_a_timer(app):
    # Bound to the session only; an hour-old page still posts.
    assert app.config['WTF_CSRF_TIME_LIMIT'] is None


def test_stale_form_post_flashes_and_goes_back(app, client, db, people, monkeypatch):
    book = add_book(db, people['alice'])
    add_review(db, people['alice'], book)
    session_id = scalar(db, 'SELECT session_id FROM reading_sessions WHERE book_id = ?', book)
    login(client, 'alice')
    monkeypatch.setitem(app.config, 'WTF_CSRF_ENABLED', True)

    page = f'http://localhost/books/book/{book}'
    r = client.post(f'/read/delete_reading_session/{session_id}',
                    data={'csrf_token': 'stale'}, headers={'Referer': page})
    assert r.status_code == 302
    assert r.headers['Location'] == page
    # Nothing was deleted, and the next page shows why
    assert scalar(db, 'SELECT COUNT(*) FROM reading_sessions WHERE session_id = ?', session_id) == 1
    with client.session_transaction() as s:
        assert any('out of date' in msg for _, msg in s.get('_flashes', []))


def test_stale_post_never_redirects_off_site(app, client, people, monkeypatch):
    login(client, 'alice')
    monkeypatch.setitem(app.config, 'WTF_CSRF_ENABLED', True)
    r = client.post('/read/delete_reading_session/1', data={},
                    headers={'Referer': 'https://evil.example/phish'})
    assert r.status_code == 302
    assert 'evil.example' not in r.headers['Location']


def test_stale_fetch_gets_json(app, client, people, monkeypatch):
    login(client, 'alice')
    monkeypatch.setitem(app.config, 'WTF_CSRF_ENABLED', True)
    r = client.post('/read/delete_reading_session/1', headers={'X-CSRFToken': 'stale'})
    assert r.status_code == 400
    assert r.get_json() == {'success': False, 'error': 'That page was out of date, try again.'}
