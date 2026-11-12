"""Undated reading sessions (ROADMAP 14c): allowed, but only once confirmed."""
from conftest import add_book, login, scalar


def _sessions(db, book):
    return scalar(db, 'SELECT COUNT(*) FROM reading_sessions WHERE book_id = ?', book)


def test_unconfirmed_undated_session_is_not_saved(client, db, people):
    # The stray-Save case: an empty form posted without the page's question
    book = add_book(db, people['alice'])
    login(client, 'alice')
    r = client.post(f'/read/manage_session/{book}', data={'date_started': '', 'date_completed': ''})
    assert r.status_code == 302
    assert _sessions(db, book) == 0


def test_several_confirmed_undated_sessions_are_kept(client, db, people):
    book = add_book(db, people['alice'])
    login(client, 'alice')
    for _ in range(2):
        client.post(f'/read/manage_session/{book}', data={'undated': '1'})
    assert _sessions(db, book) == 2
    assert scalar(db, 'SELECT COUNT(*) FROM reading_sessions WHERE book_id = ? '
                      'AND date_started IS NULL AND date_completed IS NULL', book) == 2


def test_dated_session_needs_no_confirmation(client, db, people):
    book = add_book(db, people['alice'])
    login(client, 'alice')
    client.post(f'/read/manage_session/{book}', data={'date_completed': '2024-03-01'})
    assert _sessions(db, book) == 1


def test_clearing_both_dates_on_edit_also_asks(client, db, people):
    book = add_book(db, people['alice'])
    db.execute("INSERT INTO reading_sessions (user_id, book_id, date_completed) VALUES (?, ?, '2024-01-01')",
               (people['alice'], book))
    db.commit()
    sid = scalar(db, 'SELECT session_id FROM reading_sessions WHERE book_id = ?', book)
    login(client, 'alice')
    client.post(f'/read/manage_session/{book}', data={'session_id': sid})
    assert scalar(db, 'SELECT date_completed FROM reading_sessions WHERE session_id = ?', sid) == '2024-01-01'
    client.post(f'/read/manage_session/{book}', data={'session_id': sid, 'undated': '1'})
    assert scalar(db, 'SELECT date_completed FROM reading_sessions WHERE session_id = ?', sid) is None


def test_pages_carry_the_question(client, db, people):
    book = add_book(db, people['alice'])
    login(client, 'alice')
    page = client.get(f'/books/book/{book}').get_data(as_text=True)
    assert 'Add a reading session with no dates?' in page
    assert 'data-submit="saveSession"' in page
    review = client.get(f'/read/rate_review/{book}').get_data(as_text=True)
    assert 'Add a reading session with no dates?' in review
