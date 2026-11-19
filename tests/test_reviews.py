"""The Reviews section (ROADMAP 13): rows per type, access, See all, the
[+ Review] search scope and the not-owned path."""
import re

from conftest import add_book, add_review, add_user, login, make_friends, scalar


def add_item(db, owner_id, title, media_type='book', owned=1, author='Someone'):
    cur = db.execute('INSERT INTO books (title, author, added_by, media_type, owned) VALUES (?, ?, ?, ?, ?)',
                     (title, author, owner_id, media_type, owned))
    db.commit()
    return cur.lastrowid


def finish(db, user_id, book_id, status='read'):
    db.execute('INSERT INTO collections (user_id, book_id, status) VALUES (?, ?, ?)',
               (user_id, book_id, status))
    db.commit()


def page(client, url):
    r = client.get(url)
    assert r.status_code == 200, url
    return r.get_data(as_text=True)


# --- access ------------------------------------------------------------------

def test_friends_reviews_only_friends(client, db, people):
    """carol (a friend) shows; bob (household, not a friend) and a stranger never do."""
    alice, bob, carol = people['alice'], people['bob'], people['carol']
    dave = add_user(db, 'dave')
    add_review(db, carol, add_book(db, carol, 'Carols Pick'), comment='friend words')
    add_review(db, bob, add_book(db, bob, 'Bobs Pick'), comment='household words')
    add_review(db, dave, add_book(db, dave, 'Daves Pick'), comment='stranger words')
    login(client, 'alice')
    for url in ('/reviews/', '/reviews/all/friends'):
        html = page(client, url)
        assert 'Carols Pick' in html
        assert 'Bobs Pick' not in html and 'household words' not in html
        assert 'Daves Pick' not in html and 'stranger words' not in html


def test_household_member_sees_no_household_reviews(client, db, people):
    """bob shares alice's household but isn't her friend: none of hers show."""
    add_review(db, people['alice'], add_book(db, people['alice'], 'Alices Pick'))
    login(client, 'bob')
    assert 'Alices Pick' not in page(client, '/reviews/all/friends')
    assert 'Alices Pick' not in page(client, '/reviews/')


def test_see_all_by_friend_only(client, db, people):
    add_review(db, people['carol'], add_book(db, people['carol'], 'Carols Pick'))
    login(client, 'alice')
    assert 'Carols Pick' in page(client, '/reviews/all/friends?by=carol')
    # bob is household, not a friend; dave is nobody to alice
    add_user(db, 'dave')
    assert client.get('/reviews/all/friends?by=bob').status_code == 404
    assert client.get('/reviews/all/friends?by=dave').status_code == 404
    assert client.get('/reviews/all/nonsense').status_code == 404


# --- rows per type -------------------------------------------------------------

def test_rows_per_type(client, db, people):
    alice = people['alice']
    book = add_book(db, alice, 'Paper Thing')
    movie = add_item(db, alice, 'Film Thing', 'video')
    album = add_item(db, alice, 'Album Thing', 'record')
    add_review(db, alice, book, rating=4)
    db.execute('INSERT INTO read_data (user_id, book_id, rating) VALUES (?, ?, 3)', (alice, movie))
    finish(db, alice, album, 'listened')         # finished, no review yet
    login(client, 'alice')

    books = page(client, '/reviews/?type=book')
    assert 'Paper Thing' in books and 'Film Thing' not in books and 'Album Thing' not in books
    assert 'Rated 4 of 5' in books

    movies = page(client, '/reviews/?type=video')
    assert 'Film Thing' in movies and 'Paper Thing' not in movies
    assert 'Rated 3 of 5' in movies

    music = page(client, '/reviews/?type=record')
    assert 'Album Thing' in music                # in "Finished, not reviewed yet"
    unreviewed = page(client, '/reviews/all/unreviewed?type=record')
    assert 'Album Thing' in unreviewed and 'Write a review' in unreviewed
    # once reviewed it leaves that list and joins yours
    db.execute('INSERT INTO read_data (user_id, book_id, rating) VALUES (?, ?, 5)', (alice, album))
    db.commit()
    assert 'Album Thing' not in page(client, '/reviews/all/unreviewed?type=record')
    assert 'Album Thing' in page(client, '/reviews/all/mine?type=record')


def test_your_reviews_newest_first(client, db, people):
    alice = people['alice']
    old, new = add_book(db, alice, 'Old Read'), add_book(db, alice, 'New Read')
    for book, day in ((new, '2025-06-01'), (old, '2020-01-01')):
        db.execute('INSERT INTO read_data (user_id, book_id, rating) VALUES (?, ?, 4)', (alice, book))
        db.execute('INSERT INTO reading_sessions (user_id, book_id, date_completed) VALUES (?, ?, ?)',
                   (alice, book, day))
    db.commit()
    login(client, 'alice')
    html = page(client, '/reviews/all/mine')
    assert html.index('New Read') < html.index('Old Read')


def test_profile_reviews_once_per_book_and_link_here(client, db, people):
    """A re-read book used to be listed once per session."""
    alice = people['alice']
    book = add_book(db, alice, 'Twice Read')
    add_review(db, alice, book)
    db.execute("INSERT INTO reading_sessions (user_id, book_id, date_completed) VALUES (?, ?, '2025-01-01')",
               (alice, book))
    db.commit()
    login(client, 'alice')
    html = page(client, '/user/alice')
    section = html[html.index('id="reviews-list"'):]
    section = section[:section.index('</section>')]
    assert section.count('aria-label="Twice Read"') == 1     # one cover link per review
    assert '/reviews/all/mine' in html


# --- [+ Review] search -----------------------------------------------------------

def test_find_scope(client, db, people):
    """Your shelf, your not-owned and your household's; never a friend's or a stranger's."""
    alice, bob, carol = people['alice'], people['bob'], people['carol']
    dave = add_user(db, 'dave')
    add_item(db, alice, 'Zebra Mine')
    add_item(db, alice, 'Zebra Borrowed', owned=0)
    add_item(db, bob, 'Zebra Household')
    add_item(db, carol, 'Zebra Friend')
    add_item(db, dave, 'Zebra Stranger')
    add_item(db, alice, 'Zebra Film', 'video')
    wished = add_item(db, alice, 'Zebra Wished')
    db.execute('INSERT INTO wishlist (user_id, book_id) VALUES (?, ?)', (alice, wished))
    db.commit()
    login(client, 'alice')
    html = page(client, '/reviews/find?type=book&q=zebra')
    for title in ('Zebra Mine', 'Zebra Borrowed', 'Zebra Household'):
        assert title in html
    for title in ('Zebra Friend', 'Zebra Stranger', 'Zebra Film', 'Zebra Wished'):
        assert title not in html
    assert html.index('Zebra Mine') < html.index('Zebra Household')     # yours first
    assert 'Zebra Film' in page(client, '/reviews/find?type=video&q=zebra')


def test_find_results_open_the_review_page(client, db, people):
    book = add_item(db, people['alice'], 'Quokka Tales')
    login(client, 'alice')
    html = page(client, '/reviews/find?type=book&q=quokka')
    assert f'/read/rate_review/{book}?from=reviews' in html
    assert 'Quokka Tales' in page(client, f'/read/rate_review/{book}?from=reviews')


def test_find_nothing_offers_not_owned_add(client, db, people):
    login(client, 'alice')
    html = page(client, '/reviews/find?type=video&q=Nowhere+Film')
    assert 'Add it as unshelved' in html
    assert '/videos/add?not_owned=1&amp;then=review&amp;title=Nowhere+Film' in html
    # empty search: no results, no offer yet
    assert 'Add it as unshelved' not in page(client, '/reviews/find?type=video')


# --- unshelved -> review --------------------------------------------------------

def test_add_page_prefilled_for_review(client, db, people):
    login(client, 'alice')
    for url in ('/books/add', '/videos/add', '/records/add'):
        html = page(client, url + '?not_owned=1&then=review&title=Seen+It')
        assert 'name="then" value="review"' in html
        assert 'value="Seen It"' in html
        checkbox = html[html.index('id="not_owned"'):][:200]
        assert 'checked' in checkbox
    # without then=review nothing changes
    plain = page(client, '/books/add?not_owned=1')
    assert 'name="then"' not in plain


def test_not_owned_book_lands_on_review(client, db, people):
    login(client, 'alice')
    r = client.post('/books/add', data={'submit_book': '1', 'title': 'Library Loan', 'author': 'A. Writer',
                                         'not_owned': '1', 'then': 'review'})
    book = scalar(db, "SELECT id FROM books WHERE title = 'Library Loan'")
    assert r.status_code == 302 and r.location.endswith(f'/read/rate_review/{book}?from=reviews')
    assert scalar(db, 'SELECT owned FROM books WHERE id = ?', book) == 0
    # saving the review goes back to Reviews, where it shows
    r = client.post(f'/read/rate_review/{book}?from=reviews', data={'rating': '4', 'from': 'reviews'})
    assert r.status_code == 302 and '/reviews/' in r.location
    assert 'Library Loan' in page(client, '/reviews/')


def test_not_owned_movie_and_album_land_on_review(client, db, people):
    login(client, 'alice')
    for url, title, kind in (('/videos/add', 'TV Film', 'video'), ('/records/add', 'Radio Album', 'record')):
        r = client.post(url, data={'title': title, 'author': 'Someone', 'not_owned': '1', 'then': 'review'})
        item = scalar(db, 'SELECT id FROM books WHERE title = ?', title)
        assert r.status_code == 302 and r.location.endswith(f'/read/rate_review/{item}?from=reviews')
        assert scalar(db, 'SELECT owned FROM books WHERE id = ?', item) == 0
        assert scalar(db, 'SELECT media_type FROM books WHERE id = ?', item) == kind


# --- layout (layout walk 16.0, step 3) -----------------------------------------

def test_list_and_find_pages_have_the_framed_heading(client, db, people):
    """Your reviews, Friends' reviews, Finished, not reviewed yet and the
    [+ Review] search: crumbs, then page_heading (the framed heading in
    Shelf), then the drawers."""
    login(client, 'alice')
    for url in ('/reviews/all/mine', '/reviews/all/friends', '/reviews/all/unreviewed',
                '/reviews/find?type=book'):
        html = page(client, url)
        crumbs, heading, drawers = (html.find(m) for m in
                                    ('aria-label="Breadcrumb"', 'class="page-heading', 'class="tab-row'))
        assert -1 < crumbs < heading < drawers, url


def test_captioned_cover_keeps_its_screen_reader_text_in_the_row(client, db, people):
    """The stars' "Rated 4 of 5" is sr-only, absolutely placed. The caption's
    figure is its containing block, so it stays inside the row's scroller;
    without that it was placed past the scroller and widened the page (the
    Reviews page was 957 px wide on a phone)."""
    add_review(db, people['carol'], add_book(db, people['carol'], 'Carols Pick'), rating=4)
    login(client, 'alice')
    html = page(client, '/reviews/')
    figure = re.search(r'<figure class="shelf-figure ([^"]*)"', html)
    assert figure and 'relative' in figure.group(1).split()
    assert 'Rated 4 of 5' in html


def test_empty_row_line_lines_up_in_the_bookcase(client, db, people):
    """'Nothing reviewed yet...' takes the case's note padding in Shelf, not
    the case's edge."""
    login(client, 'alice')
    html = page(client, '/reviews/')
    assert re.search(r'<p class="shelf-case-note[^"]*">Nothing reviewed yet', html)


def test_rate_review_page_layout(client, db, people):
    """Rate & review (layout walk 16.0, step 4): one grid, the head, the cover
    and the form in that order (styles.css .review-layout puts a small cover
    beside the title on a phone), each star a 44 px tap target, and the
    session row free to wrap."""
    alice = people['alice']
    book = add_book(db, alice, 'Layout Pick')
    add_review(db, alice, book)
    login(client, 'alice')
    html = page(client, f'/read/rate_review/{book}')
    spots = [html.find(f'class="{c}') for c in ('review-layout', 'review-head', 'review-cover', 'review-main')]
    assert -1 < spots[0] < spots[1] < spots[2] < spots[3]
    stars = re.findall(r'<label for="star\d"\s+class="rating-star ([^"]*)"', html)
    assert len(stars) == 5 and all({'w-11', 'h-11'} <= set(c.split()) for c in stars)
    row = re.search(r'<div class="([^"]*)" id="session-\d+">', html)
    assert row and 'flex-wrap' in row.group(1).split()
