"""16.0 step 8: the Friends page card, the profile's "friend at a glance"
(books in common) and its friend / household actions."""
from conftest import add_book, login

from utils.book_matching import books_in_common


def _book(db, owner, title, author='An Author', isbn=None, media_type='book', owned=1, removed=False):
    cur = db.execute(
        "INSERT INTO books (title, author, isbn, added_by, media_type, owned, removed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (title, author, isbn, owner, media_type, owned, '2026-01-01' if removed else None))
    db.commit()
    return cur.lastrowid


def test_books_in_common_counts_books_on_both_shelves(db, people):
    alice, carol, bob = people['alice'], people['carol'], people['bob']
    _book(db, alice, 'Dune', 'Frank Herbert'); _book(db, carol, 'Dune', 'Herbert, Frank')   # title + author
    _book(db, alice, 'Some Title', isbn='9780441013593'); _book(db, carol, 'Other Title', isbn='0441013597')  # ISBN 13 / 10
    _book(db, alice, 'Gone'); _book(db, carol, 'Gone', removed=True)              # removed: off their shelf
    _book(db, alice, 'Never Had'); _book(db, carol, 'Never Had', owned=0)        # read, never owned
    _book(db, alice, 'Film'); _book(db, carol, 'Film', media_type='video')       # not a book
    wanted = _book(db, carol, 'Wanted')                                          # their wishlist entry
    db.execute('INSERT INTO wishlist (user_id, book_id) VALUES (?, ?)', (carol, wanted)); db.commit()
    _book(db, alice, 'Wanted')
    _book(db, alice, 'Household Copy'); _book(db, bob, 'Household Copy')         # bob is alice's household, not carol
    with db:
        assert books_in_common(db, alice, carol) == 2
        assert books_in_common(db, carol, alice) == 2


def test_glance_line_for_friends_only(client, db, people):
    _book(db, people['alice'], 'Dune'); _book(db, people['carol'], 'Dune')
    login(client, 'alice')
    page = client.get('/user/carol').get_data(as_text=True)
    assert 'data-friend-glance>1 book in common</p>' in page
    page = client.get('/user/bob').get_data(as_text=True)          # household, not a friend
    assert 'data-friend-glance' not in page
    assert 'data-friend-glance' not in client.get('/user/alice').get_data(as_text=True)


def test_friends_nav_is_lit_on_someone_elses_profile(client, people):
    login(client, 'alice')
    page = client.get('/user/carol').get_data(as_text=True)
    nav = page[page.index('<!-- Navigation -->'):]
    friends = nav[:nav.index('href="/friends/"')].rsplit('<a', 1)[1] + nav[nav.index('href="/friends/"'):].split('>', 1)[0]
    assert 'nav-active' in friends
    profile = nav[nav.index('href="/user/alice"'):].split('>', 1)[0]
    assert 'nav-active' not in profile
    page = client.get('/user/alice').get_data(as_text=True)
    nav = page[page.index('<!-- Navigation -->'):]
    assert 'nav-active' in nav[nav.index('href="/user/alice"'):].split('>', 1)[0]


def test_profile_actions_say_what_happens(client, db, people):
    """Each removal is a plain button naming exactly what it does, and its
    confirm names the consequence (household vs friendship)."""
    login(client, 'alice')
    page = client.get('/user/carol').get_data(as_text=True)          # a friend, not household
    row = page[page.index('data-profile-actions'):]
    assert 'data-action="unfriend"' in row and '>Unfriend</button>' in row
    assert "You stay in the same household" not in row
    page = client.get('/user/bob').get_data(as_text=True)            # household, alice owns it
    row = page[page.index('data-profile-actions'):]
    assert '>Remove from your household</button>' in row and "books stay theirs" in row
    assert 'data-action="unfriend"' not in row                       # not friends
    assert 'sm:hidden' not in row                                    # no shortened phone label
