"""Deactivating and deleting accounts, unowned books, and exports.

The rule being protected: removing a person or a book never erases anyone
else's reviews, ratings or reading history.
"""
import csv
import io
import zipfile

from conftest import add_book, add_review, fk_violations, login, scalar


def test_admin_deactivate_keeps_everything(client, db, people):
    book = add_book(db, people['bob'])
    add_review(db, people['bob'], book)
    login(client, 'alice')
    client.post('/admin/delete_user', data={'user_id': people['bob'], 'action': 'deactivate'})
    assert scalar(db, 'SELECT is_active FROM users WHERE id = ?', people['bob']) == 0
    assert scalar(db, 'SELECT added_by FROM books WHERE id = ?', book) == people['bob']
    assert scalar(db, 'SELECT COUNT(*) FROM read_data WHERE user_id = ?', people['bob']) == 1


def test_delete_user_needs_a_choice_for_their_books(client, db, people):
    add_book(db, people['bob'])
    login(client, 'alice')
    client.post('/admin/delete_user', data={'user_id': people['bob'], 'action': 'delete'})
    assert scalar(db, 'SELECT COUNT(*) FROM users WHERE id = ?', people['bob']) == 1
    client.post('/admin/delete_user', data={'user_id': people['bob'], 'action': 'delete',
                                            'books_to': str(people['bob'])})
    assert scalar(db, 'SELECT COUNT(*) FROM users WHERE id = ?', people['bob']) == 1


def test_delete_user_books_go_to_someone_and_others_reviews_survive(client, db, people):
    bobs_book = add_book(db, people['bob'], "Bob's book")
    add_review(db, people['alice'], bobs_book)    # someone else's review on bob's book
    alices_book = add_book(db, people['alice'], "Alice's book")
    add_review(db, people['bob'], alices_book)    # bob's own review goes with him
    login(client, 'alice')
    client.post('/admin/delete_user', data={'user_id': people['bob'], 'action': 'delete',
                                            'books_to': str(people['alice'])})
    assert scalar(db, 'SELECT COUNT(*) FROM users WHERE id = ?', people['bob']) == 0
    assert scalar(db, 'SELECT added_by FROM books WHERE id = ?', bobs_book) == people['alice']
    assert scalar(db, 'SELECT COUNT(*) FROM read_data WHERE user_id = ?', people['alice']) == 1
    assert scalar(db, 'SELECT COUNT(*) FROM read_data WHERE user_id = ?', people['bob']) == 0
    assert fk_violations(db) == []


def test_delete_user_books_to_no_owner_then_reassign(client, db, people):
    book = add_book(db, people['bob'], 'Left behind')
    add_review(db, people['carol'], book)
    login(client, 'alice')
    client.post('/admin/delete_user', data={'user_id': people['bob'], 'action': 'delete', 'books_to': 'none'})
    assert scalar(db, 'SELECT added_by FROM books WHERE id = ?', book) is None
    assert scalar(db, 'SELECT COUNT(*) FROM read_data WHERE book_id = ?', book) == 1
    assert 'Left behind' in client.get('/admin/unowned_books').get_data(as_text=True)
    assert client.get('/feed/activity').status_code == 200   # used to crash on unowned books

    client.post('/admin/reassign_books', data={'book_id': book, 'new_owner_id': people['carol']})
    assert scalar(db, 'SELECT added_by FROM books WHERE id = ?', book) == people['carol']
    assert fk_violations(db) == []


def test_delete_user_wishlist_book_kept_if_someone_else_uses_it(client, db, people):
    lonely = add_book(db, people['bob'], 'Only on my wishlist')
    shared = add_book(db, people['bob'], 'Carol reviewed my wishlist book')
    for b in (lonely, shared):
        db.execute('INSERT INTO wishlist (user_id, book_id) VALUES (?, ?)', (people['bob'], b))
    add_review(db, people['carol'], shared)
    login(client, 'alice')
    client.post('/admin/delete_user', data={'user_id': people['bob'], 'action': 'delete', 'books_to': 'none'})
    assert scalar(db, 'SELECT COUNT(*) FROM books WHERE id = ?', lonely) == 0
    assert scalar(db, 'SELECT added_by FROM books WHERE id = ?', shared) is None
    assert scalar(db, 'SELECT COUNT(*) FROM read_data WHERE book_id = ?', shared) == 1
    assert fk_violations(db) == []


def test_last_admin_cannot_be_deleted(client, db, people):
    login(client, 'alice')
    client.post('/user/delete_account', data={'action': 'delete', 'password': 'correct-horse-battery',
                                              'books_to': 'none'})
    assert scalar(db, 'SELECT COUNT(*) FROM users WHERE id = ?', people['alice']) == 1


def test_self_delete_needs_password(client, db, people):
    add_book(db, people['bob'])
    login(client, 'bob')
    client.post('/user/delete_account', data={'action': 'delete', 'password': 'wrong', 'books_to': 'none'})
    assert scalar(db, 'SELECT COUNT(*) FROM users WHERE id = ?', people['bob']) == 1
    client.post('/user/delete_account', data={'action': 'delete', 'password': 'correct-horse-battery',
                                              'books_to': str(people['alice'])})
    assert scalar(db, 'SELECT COUNT(*) FROM users WHERE id = ?', people['bob']) == 0
    assert fk_violations(db) == []


def test_self_delete_can_only_give_books_to_household(client, db, people):
    book = add_book(db, people['bob'])
    login(client, 'bob')
    client.post('/user/delete_account', data={'action': 'delete', 'password': 'correct-horse-battery',
                                              'books_to': str(people['carol'])})   # not household
    assert scalar(db, 'SELECT COUNT(*) FROM users WHERE id = ?', people['bob']) == 1
    assert scalar(db, 'SELECT added_by FROM books WHERE id = ?', book) == people['bob']


def test_self_deactivate_logs_out(client, db, people):
    login(client, 'bob')
    client.post('/user/delete_account', data={'action': 'deactivate'})
    assert scalar(db, 'SELECT is_active FROM users WHERE id = ?', people['bob']) == 0
    assert client.get('/base/index').status_code == 302


# --- exports ------------------------------------------------------------------------

def test_library_export_is_only_your_books(client, db, people):
    add_book(db, people['bob'], 'Bobs book')
    add_book(db, people['carol'], 'Carols book')
    reviewed = add_book(db, people['carol'], 'Carol owns, Bob reviewed')
    add_review(db, people['bob'], reviewed)
    login(client, 'bob')
    r = client.get('/user/export_library')
    assert r.status_code == 200
    titles = {row['Title'] for row in csv.DictReader(io.StringIO(r.get_data(as_text=True)))}
    assert titles == {'Bobs book', 'Carol owns, Bob reviewed'}


def test_data_export_zip(client, db, people):
    book = add_book(db, people['bob'], 'Exported')
    add_review(db, people['bob'], book, comment='Five stars')
    login(client, 'bob')
    r = client.get('/user/export_data')
    assert r.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(r.data))
    assert {'library.csv', 'reviews.csv', 'reading_sessions.csv', 'shelves.csv', 'wishlist.csv',
            'profile.csv'} <= set(z.namelist())
    assert 'Five stars' in z.read('reviews.csv').decode()


def test_only_admins_export_someone_else(client, db, people):
    add_book(db, people['bob'], 'Private to bob')
    login(client, 'carol')
    body = client.get(f'/user/export_library?user_id={people["bob"]}').get_data(as_text=True)
    assert 'Private to bob' not in body
