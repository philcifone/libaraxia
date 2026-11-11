"""collections.quiet (migration 031, ROADMAP 14a): status rows written in bulk
stay out of friends' feeds, and a status you set by hand is announced again."""
from conftest import add_book, login, scalar
from test_videos import add_video


def set_status(db, user, book, status, quiet):
    db.execute('INSERT INTO collections (user_id, book_id, status, quiet) VALUES (?, ?, ?, ?)',
               (user, book, status, quiet))
    db.commit()


def test_quiet_rows_stay_out_of_the_feed(client, db, people):
    alice, carol = people['alice'], people['carol']     # carol is alice's friend
    loud = add_book(db, alice, 'Loud Book')
    quiet = add_book(db, alice, 'Quiet Book')
    movie = add_video(db, alice, title='Quiet Movie')
    set_status(db, alice, loud, 'want to read', 0)
    set_status(db, alice, quiet, 'want to read', 1)
    set_status(db, alice, movie, 'want to watch', 1)
    login(client, 'carol')
    page = client.get('/feed/activity').get_data(as_text=True)
    # Added books and movies appear in the feed whatever their status; the
    # status line is what quiet suppresses: one "wants to read" (the loud
    # book's), no "wants to watch"
    assert page.count('wants to read') == 1
    assert 'wants to watch' not in page


def test_new_status_by_hand_is_not_quiet(client, db, people):
    book = add_book(db, people['alice'], 'Dune')
    login(client, 'alice')
    client.post('/collections/collections/status/add', data={'id': book, 'status': 'want to read'})
    assert scalar(db, 'SELECT quiet FROM collections WHERE book_id = ?', book) == 0


def test_changing_a_status_by_hand_ends_quiet(client, db, people):
    """Otherwise a book bulk-set to "want to read" would stay invisible after
    you start reading it."""
    alice = people['alice']
    book = add_book(db, alice, 'Dune')
    set_status(db, alice, book, 'want to read', 1)
    login(client, 'alice')
    client.post('/collections/collections/status/add', data={'id': book, 'status': 'currently reading'})
    assert scalar(db, 'SELECT status FROM collections WHERE book_id = ?', book) == 'currently reading'
    assert scalar(db, 'SELECT quiet FROM collections WHERE book_id = ?', book) == 0
    login(client, 'carol')
    assert 'started reading' in client.get('/feed/activity').get_data(as_text=True)
