"""Adding, editing, removing and deleting books; who may do what; the
2026-10-28 security fixes (cover paths, SSRF guard, POST-only delete)."""
import os
from unittest import mock

import pytest

from conftest import add_book, add_review, fk_violations, login, scalar

BOOK_FORM = {
    'submit_book': '1', 'title': 'Piranesi', 'author': 'Susanna Clarke', 'publisher': 'Bloomsbury',
    'year': '2020', 'isbn': '9781635575637', 'page_count': '272', 'description': 'A house of halls.',
    'subtitle': '', 'genre': 'Fantasy',
}


def edit_form(**changes):
    form = {k: v for k, v in BOOK_FORM.items() if k != 'submit_book'}
    form.update(changes)
    return form


# --- add / edit -------------------------------------------------------------

def test_add_book(client, db, people):
    login(client, 'bob')
    r = client.post('/books/add', data=BOOK_FORM)
    assert r.status_code == 302
    row = db.execute("SELECT * FROM books WHERE title = 'Piranesi'").fetchone()
    assert row['added_by'] == people['bob'] and row['page_count'] == 272 and row['cover_image_url'] is None


def test_add_book_bad_page_count_becomes_zero(client, db, people):
    login(client, 'bob')
    client.post('/books/add', data={**BOOK_FORM, 'page_count': 'lots'})
    assert scalar(db, "SELECT page_count FROM books WHERE title = 'Piranesi'") == 0


def test_owner_can_edit(client, db, people):
    book = add_book(db, people['bob'], 'Old title')
    login(client, 'bob')
    assert client.post(f'/books/edit/{book}', data=edit_form(title='New title')).status_code == 302
    assert scalar(db, 'SELECT title FROM books WHERE id = ?', book) == 'New title'


def test_admin_can_edit_anyones_book(client, db, people):
    book = add_book(db, people['bob'], 'Old title')
    login(client, 'alice')
    client.post(f'/books/edit/{book}', data=edit_form(title='Admin fixed it'))
    assert scalar(db, 'SELECT title FROM books WHERE id = ?', book) == 'Admin fixed it'


def test_non_owner_cannot_edit_remove_delete_or_transfer(client, db, people):
    book = add_book(db, people['bob'], 'Bob owns this')
    login(client, 'carol')
    client.post(f'/books/edit/{book}', data=edit_form(title='Hijacked'))
    client.post(f'/books/remove/{book}')
    client.post(f'/books/delete/{book}')
    client.post(f'/books/transfer/{book}', data={'new_owner_id': people['carol']})
    row = db.execute('SELECT * FROM books WHERE id = ?', (book,)).fetchone()
    assert row['title'] == 'Bob owns this'
    assert row['removed_at'] is None
    assert row['added_by'] == people['bob']


def test_transfer_within_household_only(client, db, people):
    book = add_book(db, people['bob'])
    login(client, 'bob')
    client.post(f'/books/transfer/{book}', data={'new_owner_id': people['carol']})  # not household
    assert scalar(db, 'SELECT added_by FROM books WHERE id = ?', book) == people['bob']
    client.post(f'/books/transfer/{book}', data={'new_owner_id': people['alice']})  # household
    assert scalar(db, 'SELECT added_by FROM books WHERE id = ?', book) == people['alice']


# --- remove from library (deaccession) ---------------------------------------

def test_remove_and_restore_keeps_reviews(client, db, people):
    book = add_book(db, people['alice'], 'Little Free Library')
    add_review(db, people['bob'], book)
    login(client, 'alice')

    client.post(f'/books/remove/{book}', data={'removed_note': 'Left at the LFL'})
    client.get(f'/books/book/{book}')  # shows (and uses up) the "removed" flash, which names the book
    row =db.execute('SELECT removed_at, removed_note FROM books WHERE id = ?', (book,)).fetchone()
    assert row['removed_at'] and row['removed_note'] == 'Left at the LFL'
    assert scalar(db, 'SELECT COUNT(*) FROM read_data WHERE book_id = ?', book) == 1

    library = client.get('/base/index').get_data(as_text=True)
    assert 'Little Free Library' not in library
    assert 'Little Free Library' in client.get('/base/index?show_removed=1').get_data(as_text=True)

    client.post(f'/books/restore/{book}')
    assert scalar(db, 'SELECT removed_at FROM books WHERE id = ?', book) is None
    assert 'Little Free Library' in client.get('/base/index').get_data(as_text=True)


# --- hard delete --------------------------------------------------------------

def test_delete_is_post_only(client, db, people):
    book = add_book(db, people['alice'])
    login(client, 'alice')
    assert client.get(f'/books/delete/{book}').status_code == 405
    assert scalar(db, 'SELECT COUNT(*) FROM books WHERE id = ?', book) == 1


def test_delete_needs_csrf_token(app, client, db, people):
    book = add_book(db, people['alice'])
    login(client, 'alice')
    app.config['WTF_CSRF_ENABLED'] = True
    try:
        assert client.post(f'/books/delete/{book}').status_code == 400
    finally:
        app.config['WTF_CSRF_ENABLED'] = False
    assert scalar(db, 'SELECT COUNT(*) FROM books WHERE id = ?', book) == 1


def test_delete_own_mistake_cascades_cleanly(client, db, people):
    book = add_book(db, people['alice'], 'Duplicate scan')
    add_review(db, people['alice'], book)
    db.execute("INSERT INTO book_tags (book_id, user_id, tag_name) VALUES (?, ?, 'oops')", (book, people['alice']))
    db.commit()
    login(client, 'alice')
    client.post(f'/books/delete/{book}')
    assert scalar(db, 'SELECT COUNT(*) FROM books WHERE id = ?', book) == 0
    for table in ['read_data', 'collections', 'reading_sessions', 'book_tags']:
        assert scalar(db, f'SELECT COUNT(*) FROM {table} WHERE book_id = ?', book) == 0, table
    assert fk_violations(db) == []


def test_delete_refused_while_someone_else_has_reviews(client, db, people):
    book = add_book(db, people['alice'], 'Bob reviewed this')
    add_review(db, people['bob'], book)
    login(client, 'alice')
    r = client.post(f'/books/delete/{book}')
    assert r.status_code == 302 and f'/books/book/{book}' in r.location
    assert scalar(db, 'SELECT COUNT(*) FROM books WHERE id = ?', book) == 1
    assert scalar(db, 'SELECT COUNT(*) FROM read_data WHERE book_id = ?', book) == 1


# --- wishlist ---------------------------------------------------------------------

def test_wishlist_remove_cannot_delete_someone_elses_book(client, db, people):
    """Regression: POST /wishlist/remove/<id> used to delete any book with no reviews."""
    book = add_book(db, people['alice'], 'Alice owns this')
    login(client, 'carol')
    client.post(f'/wishlist/remove/{book}')
    assert scalar(db, 'SELECT COUNT(*) FROM books WHERE id = ?', book) == 1


def test_wishlist_remove_deletes_own_wishlist_book(client, db, people):
    book = add_book(db, people['carol'], 'Want this')
    db.execute('INSERT INTO wishlist (user_id, book_id) VALUES (?, ?)', (people['carol'], book))
    db.commit()
    login(client, 'carol')
    client.post(f'/wishlist/remove/{book}')
    assert scalar(db, 'SELECT COUNT(*) FROM wishlist WHERE book_id = ?', book) == 0
    assert scalar(db, 'SELECT COUNT(*) FROM books WHERE id = ?', book) == 0
    assert fk_violations(db) == []


def test_wishlist_remove_keeps_rated_book_out_of_library(client, db, people):
    """Phase 5 leftover: a rated wishlist book (e.g. a Goodreads to-read row
    with a rating) used to land in your library when removed from the
    wishlist. Now it's marked removed and kept on "Read but not owned"."""
    carol = people['carol']
    book = add_book(db, carol, 'Read it, never bought it')
    db.execute('INSERT INTO wishlist (user_id, book_id) VALUES (?, ?)', (carol, book))
    db.execute("INSERT INTO read_data (user_id, book_id, rating, comment) VALUES (?, ?, 4, 'Good')", (carol, book))
    db.commit()
    login(client, 'carol')
    client.post(f'/wishlist/remove/{book}')

    assert scalar(db, 'SELECT COUNT(*) FROM read_data WHERE book_id = ?', book) == 1      # review kept
    assert scalar(db, 'SELECT removed_at IS NOT NULL FROM books WHERE id = ?', book) == 1
    assert 'Read it, never bought it' not in client.get('/base/index').get_data(as_text=True)
    assert scalar(db, """SELECT COUNT(*) FROM collection_books cb
                         JOIN user_collections uc ON uc.collection_id = cb.collection_id
                         WHERE uc.user_id = ? AND uc.name = 'Read but not owned' AND cb.book_id = ?""",
                  carol, book) == 1
    assert fk_violations(db) == []


def test_wishlist_remove_unread_book_with_data_is_not_shelved_as_read(client, db, people):
    """Data that isn't reading it (here a tag) keeps the book out of the library
    but doesn't call it read."""
    carol = people['carol']
    book = add_book(db, carol, 'Tagged only')
    db.execute('INSERT INTO wishlist (user_id, book_id) VALUES (?, ?)', (carol, book))
    db.execute("INSERT INTO book_tags (user_id, book_id, tag_name) VALUES (?, ?, 'gift')", (carol, book))
    db.commit()
    login(client, 'carol')
    client.post(f'/wishlist/remove/{book}')
    assert scalar(db, 'SELECT removed_at IS NOT NULL FROM books WHERE id = ?', book) == 1
    assert scalar(db, "SELECT COUNT(*) FROM user_collections WHERE name = 'Read but not owned'") == 0


# --- cover paths (arbitrary file deletion fix) --------------------------------------

UNSAFE_PATHS = ['../library.db', '/etc/passwd', 'uploads/../../app.py', 'C:\\x.jpg',
                'static/uploads/x.jpg', 'uploads\\..\\x.jpg', '']


@pytest.mark.parametrize('path', UNSAFE_PATHS)
def test_is_safe_upload_path_rejects(path):
    from utils.image_utils import is_safe_upload_path
    assert not is_safe_upload_path(path)


@pytest.mark.parametrize('path', ['uploads/cover_1.jpg', 'uploads/avatars/user_4_1.jpeg'])
def test_is_safe_upload_path_accepts(path):
    from utils.image_utils import is_safe_upload_path
    assert is_safe_upload_path(path)


def test_add_book_ignores_unsafe_existing_cover(client, db, people):
    login(client, 'bob')
    client.post('/books/add', data={**BOOK_FORM, 'existing_cover_url': '../library.db'})
    assert scalar(db, "SELECT cover_image_url FROM books WHERE title = 'Piranesi'") is None


def test_edit_book_ignores_unsafe_fetched_cover(client, db, people):
    book = add_book(db, people['bob'], cover='uploads/real_cover.jpg')
    login(client, 'bob')
    client.post(f'/books/edit/{book}', data=edit_form(fetched_cover_url='../library.db'))
    assert scalar(db, 'SELECT cover_image_url FROM books WHERE id = ?', book) == 'uploads/real_cover.jpg'


def test_delete_image_file_refuses_outside_uploads(app, tmp_path):
    from utils.image_utils import delete_image_file
    victim = os.path.join(app.root_path, 'static', 'not-an-upload.txt')
    open(victim, 'w').close()
    try:
        with app.app_context():
            assert delete_image_file('../static/not-an-upload.txt') is False
            assert delete_image_file('not-an-upload.txt') is False
        assert os.path.exists(victim)
    finally:
        os.remove(victim)


def test_deleting_book_with_planted_cover_path_keeps_the_file(client, db, people, db_path):
    """Even a bad path already in the DB never reaches os.remove."""
    book = add_book(db, people['alice'], cover=f'../{os.path.relpath(db_path, "/")}')
    login(client, 'alice')
    client.post(f'/books/delete/{book}')
    assert os.path.exists(db_path)


# --- SSRF guard on cover downloads ------------------------------------------------

@pytest.mark.parametrize('url', [
    'http://127.0.0.1/cover.jpg', 'http://localhost:5000/', 'http://192.168.1.10/x.jpg',
    'http://10.0.0.1/', 'http://169.254.169.254/latest/meta-data/', 'http://[::1]/',
    'file:///etc/passwd', 'ftp://example.com/x.jpg', 'http:///nohost',
])
def test_private_and_odd_urls_are_not_public(url):
    from utils.book_utils import _is_public_http_url
    assert not _is_public_http_url(url)


def test_public_ip_is_allowed():
    from utils.book_utils import _is_public_http_url
    assert _is_public_http_url('http://8.8.8.8/cover.jpg')


def test_redirect_to_private_address_is_blocked(app):
    """A public URL that redirects to the LAN is stopped at the redirect."""
    from utils import book_utils
    redirect = mock.Mock(is_redirect=True, headers={'Location': 'http://192.168.1.1/admin'})
    with app.app_context(), mock.patch.object(book_utils._session, 'get', return_value=redirect) as get:
        assert book_utils._get_public('http://8.8.8.8/cover.jpg') is None
    assert get.call_count == 1


# --- book tools on the edit page (Phase 7.2) ---------------------------------

def test_book_tools_live_on_the_edit_page(client, db, people):
    """Transfer and permanent delete moved from the book page into a "Book
    tools" disclosure on the edit page (owner/admin only, like the edit page)."""
    book = add_book(db, people['bob'], 'Dune', 'Frank Herbert')
    login(client, 'bob')
    edit = client.get(f'/books/edit/{book}').get_data(as_text=True)
    assert 'id="book-tools"' in edit
    assert f'action="/books/transfer/{book}"' in edit          # bob shares a household with alice
    assert f'action="/books/delete/{book}"' in edit
    assert '<option value="%d">alice</option>' % people['alice'] in edit

    page = client.get(f'/books/book/{book}').get_data(as_text=True)
    assert f'/books/delete/{book}' not in page and f'/books/transfer/{book}' not in page
    assert f'/books/remove/{book}' in page                      # the everyday action stays
    assert f'/books/edit/{book}#book-tools' in page


def test_book_tools_refuse_delete_while_others_have_data(client, db, people):
    book = add_book(db, people['bob'], 'Dune', 'Frank Herbert')
    add_review(db, people['alice'], book)
    login(client, 'bob')
    edit = ' '.join(client.get(f'/books/edit/{book}').get_data(as_text=True).split())
    assert "Can't delete: alice has reviews" in edit and f'action="/books/delete/{book}"' not in edit


def test_book_tools_without_a_household_have_no_transfer(client, db, people):
    book = add_book(db, people['carol'], 'Dune', 'Frank Herbert')   # carol has no household
    login(client, 'carol')
    edit = client.get(f'/books/edit/{book}').get_data(as_text=True)
    assert 'id="book-tools"' in edit and '/books/transfer/' not in edit


def test_friend_reviews_are_cards_with_read_more(client, db, people):
    """7.3: friends' reviews on the book page are cards with the text in
    place (the shared "Read more" clamp), not a collapsed accordion inside a
    scroll box."""
    book = add_book(db, people['alice'], 'Dune', 'Frank Herbert')
    add_review(db, people['bob'], book)             # bob shares alice's household
    login(client, 'alice')
    page = client.get(f'/books/book/{book}').get_data(as_text=True)
    assert 'Friend Reviews' in page
    assert '<article class="bg-primary rounded-lg p-4 card">' in page
    assert 'toggleFriendReview' not in page and 'max-h-[600px]' not in page


def test_read_more_is_one_shared_helper():
    """Description and reviews (book page, profile) all use common.js's
    toggleReadMore; the three old hand-rolled toggles are gone."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parent.parent
    common = (root / 'static/common.js').read_text()
    assert 'function toggleReadMore' in common and 'function initReadMore' in common
    for name in ('toggleDescription', 'toggleFriendReview', 'toggleReviewText'):
        for path in list((root / 'static').glob('*.js')) + list((root / 'templates').rglob('*.html')):
            assert name not in path.read_text(), f'{name} still in {path.name}'
    for template in ('book_detail.html', 'user.html'):
        text = (root / 'templates' / template).read_text()
        assert 'data-click="toggleReadMore"' in text
