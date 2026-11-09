"""Grid sort orders (ROADMAP 11.4, utils/sorting.py)."""
from conftest import add_book, login
from test_videos import add_video

XHR = {'X-Requested-With': 'XMLHttpRequest'}


def finish(db, user_id, book_id, date):
    db.execute('INSERT INTO reading_sessions (user_id, book_id, date_completed) VALUES (?, ?, ?)',
               (user_id, book_id, date))
    db.commit()


def rate(db, user_id, book_id, rating):
    db.execute('INSERT INTO read_data (user_id, book_id, rating) VALUES (?, ?, ?)', (user_id, book_id, rating))
    db.commit()


def titles(client, url):
    return [b['title'] for b in client.get(url, headers=XHR).get_json()['books']]


def in_page_order(page, names):
    """`names` sorted by where they first appear in the page."""
    return sorted(names, key=page.index)


def test_date_read_newest_first_unread_last(client, db, people):
    alice, bob = people['alice'], people['bob']
    old, new, unread, bobs = (add_book(db, alice, title=t) for t in ('Old', 'New', 'Unread', 'BobRead'))
    finish(db, alice, old, '2020-05-01')
    finish(db, alice, old, '2019-01-01')        # the latest session counts
    finish(db, alice, new, '2025-03-01')
    finish(db, bob, bobs, '2030-01-01')         # someone else's session doesn't
    login(client, 'alice')
    assert titles(client, '/base/index?sort_by=finished&sort_order=desc') == ['New', 'Old', 'BobRead', 'Unread']
    # Nulls stay last ascending too; ties by title
    assert titles(client, '/base/index?sort_by=finished&sort_order=asc') == ['Old', 'New', 'BobRead', 'Unread']


def test_rating_is_the_viewers_on_the_household_page(client, db, people):
    alice, bob = people['alice'], people['bob']      # one household
    a, b, c = add_book(db, alice, title='Ay'), add_book(db, bob, title='Bee'), add_book(db, bob, title='Cee')
    rate(db, alice, b, 5)
    rate(db, alice, a, 2)
    rate(db, bob, c, 5)                              # bob's rating, not alice's
    login(client, 'alice')
    assert titles(client, '/base/shared-library?sort_by=rating&sort_order=desc') == ['Bee', 'Ay', 'Cee']


def test_pages_puts_audiobooks_and_unknowns_last(client, db, people):
    alice = people['alice']
    for title, pages, fmt in (('Short', 90, None), ('Long', 900, None), ('Heard', 500, 'Audiobook'), ('Blank', None, None)):
        book = add_book(db, alice, title=title)
        db.execute('UPDATE books SET page_count = ?, format = ?, owned = 1 WHERE id = ?', (pages, fmt, book))
    db.commit()
    login(client, 'alice')
    assert titles(client, '/base/index?sort_by=page_count&sort_order=desc&show=all') == ['Long', 'Short', 'Blank', 'Heard']


def test_unknown_sort_falls_back_to_title(client, db, people):
    alice = people['alice']
    add_book(db, alice, title='beta')
    add_book(db, alice, title='Alpha')
    login(client, 'alice')
    # Not a column name passed through: an injection attempt is just "title"
    assert titles(client, '/base/index?sort_by=id;DROP TABLE books&sort_order=sideways') == ['Alpha', 'beta']
    # A section's own sort isn't offered elsewhere: books have no runtime
    assert titles(client, '/base/index?sort_by=runtime_minutes') == ['Alpha', 'beta']


def test_movies_sort_by_date_watched(client, db, people):
    alice = people['alice']
    early, late = add_video(db, alice, title='Early', barcode=None), add_video(db, alice, title='Late', barcode=None)
    add_video(db, alice, title='Unseen', barcode=None)
    finish(db, alice, early, '2001-01-01')
    finish(db, alice, late, '2024-01-01')
    login(client, 'alice')
    page = client.get('/videos/?sort_by=finished&sort_order=desc').get_data(as_text=True)
    assert in_page_order(page, ['Unseen', 'Early', 'Late']) == ['Late', 'Early', 'Unseen']
    assert '<option value="finished" selected>Date watched</option>' in page
    assert 'value="page_count"' not in page and 'value="runtime_minutes"' in page


def test_collection_page_honours_the_sort(client, db, people):
    alice = people['alice']
    zed, abe = add_book(db, alice, title='Zed'), add_book(db, alice, title='Abe')
    for book in (abe, zed):                          # Zed set last
        db.execute("INSERT INTO collections (user_id, book_id, status) VALUES (?, ?, 'read')", (alice, book))
    db.execute("UPDATE collections SET updated_at = '2020-01-01' WHERE book_id = ?", (abe,))
    db.commit()
    login(client, 'alice')
    page = client.get('/collections/collections/status/read').get_data(as_text=True)
    assert in_page_order(page, ['Abe', 'Zed'])[0] == 'Zed'          # newest first by default
    assert '<option value="collected" selected>Date added here</option>' in page
    page = client.get('/collections/collections/status/read?sort_by=title&sort_order=asc').get_data(as_text=True)
    assert in_page_order(page, ['Abe', 'Zed'])[0] == 'Abe'


def test_a_friends_grid_filters_and_sorts_by_their_data(client, db, people):
    """11.3 (Phil): on a friend's shelf, filters and sorts apply to the
    entries in view, so it's their statuses and ratings, not yours. Your
    own and the household's shelves keep yours."""
    alice, carol = people['alice'], people['carol']           # friends
    dune, emma, heat = (add_book(db, carol, title=t) for t in ('Dune', 'Emma', 'Zed'))
    db.execute("INSERT INTO collections (user_id, book_id, status) VALUES (?, ?, 'read')", (carol, dune))
    db.execute("INSERT INTO collections (user_id, book_id, status) VALUES (?, ?, 'read')", (alice, emma))
    rate(db, carol, heat, 5)
    rate(db, alice, dune, 5)
    db.commit()
    login(client, 'alice')
    page = client.get('/base/library/carol?read_status=read').get_data(as_text=True)
    assert 'Dune' in page and 'Emma' not in page
    assert titles(client, '/base/library/carol?sort_by=rating&sort_order=desc') == ['Zed', 'Dune', 'Emma']
    # Search, filter panel and the grid itself are the regular ones
    page = client.get('/base/library/carol').get_data(as_text=True)
    assert 'id="search_term"' in page and 'id="sort_by"' in page and 'book-container' in page
    assert '/wishlist/user/carol' in page
    # Movies too
    film = add_video(db, carol, title='Heat', barcode=None)
    add_video(db, carol, title='Alien', barcode=None)
    db.execute("INSERT INTO collections (user_id, book_id, status) VALUES (?, ?, 'watched')", (carol, film))
    db.commit()
    page = client.get('/videos/user/carol?read_status=watched').get_data(as_text=True)
    assert 'Heat' in page and 'Alien' not in page


def test_a_friends_grid_names_them(client, db, people):
    add_book(db, people['carol'], title='Dune')
    login(client, 'alice')
    page = client.get('/base/library/carol').get_data(as_text=True)
    assert 'Search carol&#39;s 1 book' in page and '>carol&#39;s rating</option>' in page
    page = client.get('/base/index').get_data(as_text=True)
    assert 'Search your' in page
    add_book(db, people['alice'], title='Emma')
    assert '>Your rating</option>' in client.get('/base/index').get_data(as_text=True)
