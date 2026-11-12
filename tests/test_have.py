"""Do I have this? (ROADMAP 8E): /have/?q=."""
from html import unescape

from conftest import add_book, add_user, login
from test_videos import add_video, EAN, UPC


def isbn(db, book_id, value):
    db.execute('UPDATE books SET isbn = ? WHERE id = ?', (value, book_id))
    db.commit()


def page(client, q):
    # Unescaped: the verdict labels come from utils/have.py, so "bob's" is &#39;
    return unescape(client.get('/have/', query_string={'q': q}).get_data(as_text=True))


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
    assert 'It is in your records, not on your shelf.' in html and 'Unshelved' in html
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
    assert "carol's copy, not on a shelf here" in html and 'rated 5/5' in html
    assert 'Friend Book Two' not in html                   # no data on it: not yours to see here


def test_misses_offer_adding_with_the_code(client, db, people):
    login(client, 'alice')
    html = page(client, '9780141439518')
    assert 'Not here' in html
    assert '/wishlist/add?type=book&isbn=9780141439518' in html
    assert '/books/add?isbn=9780141439518' in html
    html = page(client, EAN)
    assert 'Wishlist it as' in html and f'/wishlist/add?type=video&barcode={EAN}' in html
    assert f'/wishlist/add?type=record&barcode={EAN}' in html
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


# --- The Add pages' local check (ROADMAP 14c) ------------------------------

def test_local_check_by_isbn_and_barcode(client, db, people):
    book = add_book(db, people['alice'], title='Emma')
    isbn(db, book, '9780141439587')
    add_video(db, people['bob'], title='Heat')             # the household's
    login(client, 'alice')
    data = client.get('/have/local', query_string={'q': '0141439580'}).get_json()   # ISBN-10 form
    assert data['best'] == 'yours'
    assert data['matches'][0]['url'] == f'/books/book/{book}'
    assert data['matches'][0]['label'] == 'On your shelf'
    data = client.get('/have/local', query_string={'q': UPC}).get_json()
    assert data['best'] == 'household' and data['matches'][0]['label'] == "On the shelf: bob's"


def test_local_check_is_codes_only_and_scoped(client, db, people):
    stranger = add_user(db, 'dave')
    theirs = add_book(db, stranger, title='Emma')
    isbn(db, theirs, '9780141439587')
    login(client, 'alice')
    # A stranger's copy is never a match; a title is the page's job
    assert client.get('/have/local', query_string={'q': '9780141439587'}).get_json()['matches'] == []
    add_book(db, people['alice'], title='Emma')
    assert client.get('/have/local', query_string={'q': 'Emma'}).get_json()['matches'] == []


def test_add_page_duplicate_check_uses_the_14b_rules(client, db, people):
    # Subtitle split off vs in the title, Jr., name order: as book_matching
    db.execute("INSERT INTO books (title, subtitle, author, added_by) VALUES "
               "('This Is Water', 'Some Thoughts', 'David Foster Wallace', ?)", (people['alice'],))
    db.execute("INSERT INTO books (title, author, added_by) VALUES "
               "('Slaughterhouse-Five', 'Kurt Vonnegut Jr.', ?)", (people['bob'],))
    db.execute("INSERT INTO books (title, author, added_by) VALUES "
               "('The Three-Body Problem', 'Liu Cixin', ?)", (people['alice'],))
    db.commit()
    login(client, 'alice')

    def dups(**body):
        return [d['title'] for d in client.post('/books/check_duplicates', json=body).get_json()['duplicates']]
    assert dups(title='This Is Water: Some Thoughts', author='David Foster Wallace') == ['This Is Water']
    assert dups(title='This Is Water', subtitle='Some Thoughts', author='David Foster Wallace') == ['This Is Water']
    assert dups(title='Slaughterhouse-Five', author='Kurt Vonnegut') == ['Slaughterhouse-Five']
    assert dups(title='Three-Body Problem', author='Cixin Liu') == ['The Three-Body Problem']
    assert dups(title="Three-Body Problem (Remembrance of Earth's Past, #1)", author='Cixin Liu') == ['The Three-Body Problem']
    assert dups(title='This Is Water', author='Someone Else') == []
    assert dups(title='Slaughterhouse-Five') == ['Slaughterhouse-Five']    # no author typed yet


def test_add_page_says_codes_are_checked_locally(client, people):
    login(client, 'alice')
    html = client.get('/books/add').get_data(as_text=True)
    assert 'checked against your library first' in html
