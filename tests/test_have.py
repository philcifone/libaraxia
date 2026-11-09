"""Do I have this? (ROADMAP 8E): /have/?q=."""
from conftest import add_book, add_user, login
from test_videos import add_video, EAN, UPC


def isbn(db, book_id, value):
    db.execute('UPDATE books SET isbn = ? WHERE id = ?', (value, book_id))
    db.commit()


def page(client, q):
    return client.get('/have/', query_string={'q': q}).get_data(as_text=True)


def test_your_book_by_either_isbn_form(client, db, people):
    dune = add_book(db, people['alice'], title='Dune')
    isbn(db, dune, '978-0-441-17271-9')                    # stored with hyphens
    login(client, 'alice')
    for q in ('9780441172719', '0441172717', '0-441-17271-7'):
        html = page(client, q)
        assert 'You own this' in html and 'On your shelf' in html and f'/books/book/{dune}' in html, q


def test_household_copy_and_movie_barcode(client, db, people):
    heat = add_video(db, people['bob'], title='Heat')      # bob shares alice's household
    login(client, 'alice')
    html = page(client, UPC)                               # 12-digit UPC finds the stored EAN-13
    assert 'Your household owns this' in html and "On the shelf: bob's" in html
    assert f'/videos/{heat}' in html


def test_not_owned_shows_your_status_and_rating(client, db, people):
    alice = people['alice']
    circe = add_book(db, alice, title='Circe')
    db.execute('UPDATE books SET owned = 0 WHERE id = ?', (circe,))
    db.execute("INSERT INTO collections (user_id, book_id, status) VALUES (?, ?, 'read')", (alice, circe))
    db.execute('INSERT INTO read_data (user_id, book_id, rating) VALUES (?, ?, 4)', (alice, circe))
    db.commit()
    login(client, 'alice')
    html = page(client, 'circe')                           # by title
    assert "You don&#39;t own this" in html and 'Not owned' in html
    assert 'You: Read, rated 4/5' in html


def test_wishlists(client, db, people):
    alice, bob = people['alice'], people['bob']
    mine = add_book(db, alice, title='Piranesi')
    theirs = add_book(db, bob, title='Piranesi Deluxe')
    db.executemany('INSERT INTO wishlist (user_id, book_id) VALUES (?, ?)', [(alice, mine), (bob, theirs)])
    db.commit()
    login(client, 'alice')
    html = page(client, 'piranesi')
    assert 'On your wishlist' in html                      # the headline
    assert "On bob's wishlist" in html                 # a member's wish isn't a copy
    assert 'household owns' not in html


def test_strangers_and_friends_copies_are_not_yours(client, db, people):
    dave = add_user(db, 'dave')                            # nobody's friend
    carol = people['carol']                                # alice's friend, not household
    add_book(db, dave, title='Stranger Book')
    reviewed = add_book(db, carol, title='Friend Book')
    add_book(db, carol, title='Friend Book Two')
    db.execute('INSERT INTO read_data (user_id, book_id, rating) VALUES (?, ?, 5)', (people['alice'], reviewed))
    db.commit()
    login(client, 'alice')
    assert 'Not here' in page(client, 'stranger book')
    html = page(client, 'friend book')
    assert "carol&#39;s copy, not on a shelf here" in html and 'rated 5/5' in html
    assert 'Friend Book Two' not in html                   # no data on it: not yours to see here


def test_misses_offer_adding_with_the_code(client, db, people):
    login(client, 'alice')
    html = page(client, '9780141439518')
    assert 'Not here' in html
    assert '/wishlist/add?type=book&amp;isbn=9780141439518' in html
    assert '/books/add?isbn=9780141439518' in html
    html = page(client, EAN)
    assert 'Wishlist it as' in html and f'/wishlist/add?type=video&amp;barcode={EAN}' in html
    assert f'/wishlist/add?type=record&amp;barcode={EAN}' in html
    assert f'/records/add?barcode={EAN}' in html and f'/videos/add?barcode={EAN}' in html
    assert '/books/add?barcode' not in html                   # a barcode isn't a book
    assert "isn't a valid barcode" in page(client, '123456789019')    # bad check digit


def test_add_book_takes_an_isbn_from_the_url(client, people):
    login(client, 'alice')
    html = client.get('/books/add?isbn=9780141439518').get_data(as_text=True)
    assert 'value="9780141439518"' in html and 'data-auto-lookup="1"' in html
    assert 'data-auto-lookup' not in client.get('/books/add').get_data(as_text=True)


def test_sidebar_links_to_it(client, people):
    login(client, 'alice')
    html = client.get('/have/').get_data(as_text=True)
    assert 'href="/have/"' in html and 'Do I Have This?' in html and 'id="toggle-scanner"' in html
