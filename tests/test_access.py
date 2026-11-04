"""Phase 4 access rules (see "Access Model" in CLAUDE.md).

A user's circle is themselves, their household and their friends. A book's
page is open to admins and to anyone whose circle owns the book or has data
on it; routes that attach your own data to a book id use the same check.

people: alice (admin) + bob share a household; carol is alice's friend.
dave is added here as a stranger to everyone.
"""
import pytest

from conftest import add_book, add_review, add_user, login, scalar


@pytest.fixture
def dave(db, people):
    return add_user(db, 'dave')


# --- book detail -------------------------------------------------------------

def test_household_and_friends_can_open_book(client, db, people):
    book = add_book(db, people['alice'], 'Alice book')
    for who in ('bob', 'carol'):
        login(client, who)
        assert client.get(f'/books/book/{book}').status_code == 200, who


def test_stranger_gets_404(client, db, people, dave):
    book = add_book(db, people['alice'])
    login(client, 'dave')
    assert client.get(f'/books/book/{book}').status_code == 404


def test_friend_of_a_household_member_is_not_in_the_circle(client, db, people):
    # carol is alice's friend, not bob's
    book = add_book(db, people['bob'], 'Bob book')
    login(client, 'carol')
    assert client.get(f'/books/book/{book}').status_code == 404


def test_circle_activity_opens_the_book(client, db, people):
    # alice reviewing bob's book puts it in carol's feed, so carol can open it
    book = add_book(db, people['bob'], 'Bob book')
    add_review(db, people['alice'], book)
    login(client, 'carol')
    assert client.get(f'/books/book/{book}').status_code == 200


def test_own_history_keeps_access_to_unowned_book(client, db, people, dave):
    book = add_book(db, None, 'Orphan')
    add_review(db, dave, book)
    login(client, 'dave')
    assert client.get(f'/books/book/{book}').status_code == 200


def test_admin_can_open_any_book(client, db, people, dave):
    book = add_book(db, dave, 'Dave book')
    login(client, 'alice')
    assert client.get(f'/books/book/{book}').status_code == 200


def test_wishlist_notes_only_from_circle(client, db, people, dave):
    book = add_book(db, people['bob'])
    db.execute("INSERT INTO wishlist (user_id, book_id, notes) VALUES (?, ?, 'dave secret')", (dave, book))
    db.execute("INSERT INTO wishlist (user_id, book_id, notes) VALUES (?, ?, 'alice note')",
               (people['alice'], book))
    db.commit()
    login(client, 'bob')
    page = client.get(f'/books/book/{book}?wishlist_owner=dave').get_data(as_text=True)
    assert 'dave secret' not in page
    assert 'alice note' in page


# --- attaching data can't be used as a back door -----------------------------

def test_stranger_cannot_attach_data(client, db, people, dave):
    book = add_book(db, people['alice'])
    login(client, 'dave')
    client.post('/collections/collections/status/add', data={'id': book, 'status': 'read'})
    client.post(f'/wishlist/quick_add/{book}')
    client.post(f'/read/manage_session/{book}', data={'date_started': '2024-01-01'})
    r = client.post(f'/read/rate_review/{book}', data={'rating': '5', 'comment': 'x'})
    assert r.status_code == 404
    assert client.get(f'/read/rate_review/{book}').status_code == 404
    r = client.post('/tags/add', json={'book_id': book, 'tags': ['x']})
    assert r.status_code == 404
    for table in ('collections', 'wishlist', 'reading_sessions', 'read_data', 'book_tags'):
        assert scalar(db, f'SELECT COUNT(*) FROM {table} WHERE user_id = ?', dave) == 0, table
    # and so the page is still closed to them
    assert client.get(f'/books/book/{book}').status_code == 404


def test_stranger_cannot_add_book_to_own_custom_collection(client, db, people, dave):
    book = add_book(db, people['alice'])
    cid = db.execute("INSERT INTO user_collections (user_id, name) VALUES (?, 'mine')", (dave,)).lastrowid
    db.commit()
    login(client, 'dave')
    r = client.post(f'/collections/collections/{cid}/add', data={'book_id': book})
    assert r.status_code == 404
    client.post('/collections/manage_book_collections', data={'book_id': book, 'collection_id': cid})
    assert scalar(db, 'SELECT COUNT(*) FROM collection_books WHERE collection_id = ?', cid) == 0


def test_household_member_can_track_shared_book(client, db, people):
    book = add_book(db, people['alice'])
    login(client, 'bob')
    client.post('/collections/collections/status/add', data={'id': book, 'status': 'currently reading'})
    assert scalar(db, 'SELECT status FROM collections WHERE user_id = ? AND book_id = ?',
                  people['bob'], book) == 'currently reading'
