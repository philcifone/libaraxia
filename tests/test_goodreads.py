"""Goodreads import through its routes (blueprints/user.py: upload, review,
choose, apply; ROADMAP 14b), the parser (utils/goodreads.py), and the
own-books-only matching it shares with the wishlist (utils/book_matching.py).
The planner's own rules are tested headless in test_goodreads_plan.py.

Expectations changed in 14b on purpose (spec section 13): read rows come in
not owned by default; no collections from shelves; no Want to Read for an
owned to-read row; a matched book with a status gets what's missing."""
import csv
import io
import re

import pytest

from conftest import add_book, add_user, fk_violations, login, scalar

HEADER = ['Book Id', 'Title', 'Author', 'Author l-f', 'Additional Authors', 'ISBN', 'ISBN13',
          'My Rating', 'Average Rating', 'Publisher', 'Binding', 'Number of Pages',
          'Year Published', 'Original Publication Year', 'Date Read', 'Date Added',
          'Bookshelves', 'Bookshelves with positions', 'Exclusive Shelf', 'My Review',
          'Spoiler', 'Private Notes', 'Read Count', 'Owned Copies']


def row(title, shelf='read', **kw):
    """A Goodreads row with sensible defaults; keyword names use underscores
    for spaces (my_rating='5', isbn13='978...')."""
    r = {h: '' for h in HEADER}
    r.update({'Title': title, 'Author': 'Some Author', 'Exclusive Shelf': shelf,
              'My Rating': '0', 'Date Added': '2024/01/02',
              'Read Count': '1' if shelf == 'read' else '0'})
    by_lower = {h.lower(): h for h in HEADER}
    for key, value in kw.items():
        r[by_lower[key.replace('_', ' ')]] = value
    return r


def csv_text(*rows):
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=HEADER)
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


def upload(client, text, filename='goodreads_library_export.csv', encoding='utf-8'):
    data = {'goodreads_csv': (io.BytesIO(text.encode(encoding)), filename)}
    return client.post('/user/import_goodreads/plan', data=data, content_type='multipart/form-data')


def fingerprint(client):
    """The review page's fingerprint, as the browser sends it back."""
    page = client.get('/user/import_goodreads/review')
    assert page.status_code == 200
    return re.search(r'data-fingerprint="([0-9a-f]+)"', page.get_data(as_text=True)).group(1)


def run(client, username, *rows, choices=()):
    """Upload, choose, import, as the review page does. Returns the result."""
    login(client, username)
    r = upload(client, csv_text(*rows))
    assert r.status_code == 302 and r.headers['Location'].endswith('/user/import_goodreads/review')
    for lines, choice in choices:
        r = client.post('/user/import_goodreads/choose', json={'lines': lines, 'choice': choice})
        assert r.status_code == 200 and r.get_json()['saved'] == lines, r.get_json()
    r = client.post('/user/import_goodreads/apply', json={'fingerprint': fingerprint(client)})
    assert r.status_code == 200, r.get_json()
    report = r.get_json()
    # The result must account for every row
    assert sum(report['outcomes'].values()) == report['total_rows'] == len(rows)
    return report


def outcome(report, title):
    return next(r for r in report['rows'] if r['title'] == title)['outcome']


def status_of(db, user_id, book_id):
    row = db.execute('SELECT status FROM collections WHERE user_id = ? AND book_id = ?',
                     (user_id, book_id)).fetchone()
    return row and row['status']


# --- matching only within your own books -------------------------------------

def test_strangers_book_is_never_matched(client, db, people):
    dave = add_user(db, 'dave')  # not in alice's circle at all
    theirs = add_book(db, dave, 'Dune', 'Frank Herbert')
    db.execute("UPDATE books SET isbn = '9780441172719' WHERE id = ?", (theirs,))
    db.commit()

    report = run(client, 'alice', row('Dune', author='Frank Herbert', isbn13='="9780441172719"'))

    assert outcome(report, 'Dune') == 'not_owned'          # was 'added' (owned)
    mine = scalar(db, "SELECT id FROM books WHERE added_by = ? AND title = 'Dune'", people['alice'])
    assert mine != theirs
    assert status_of(db, people['alice'], mine) == 'read'
    assert status_of(db, people['alice'], theirs) is None


def test_household_copy_is_matched_and_own_copy_wins(client, db, people):
    bobs = add_book(db, people['bob'], 'Dune', 'Frank Herbert')
    carols = add_book(db, people['carol'], 'Emma', 'Jane Austen')  # friend, not household
    report = run(client, 'alice', row('Dune', author='Frank Herbert'),
                 row('Emma', author='Jane Austen'))
    assert outcome(report, 'Dune') == 'filled'             # was 'matched'
    assert status_of(db, people['alice'], bobs) == 'read'
    assert scalar(db, "SELECT COUNT(*) FROM books WHERE title = 'Dune'") == 1
    # a friend's copy is not your household's: a new book
    assert outcome(report, 'Emma') == 'not_owned'
    assert status_of(db, people['alice'], carols) is None

    # bob imports: his own copy is preferred over anything else
    alices = add_book(db, people['alice'], 'Middlemarch', 'George Eliot')
    bobs_mm = add_book(db, people['bob'], 'Middlemarch', 'George Eliot')
    client.post('/auth/logout')
    run(client, 'bob', row('Middlemarch', author='George Eliot'))
    assert status_of(db, people['bob'], bobs_mm) == 'read'
    assert status_of(db, people['bob'], alices) is None


def test_isbn10_13_and_series_suffix_match(client, db, people):
    by_isbn = add_book(db, people['alice'], 'White Noise', 'Don DeLillo')
    db.execute("UPDATE books SET isbn = '0143129554' WHERE id = ?", (by_isbn,))
    by_title = add_book(db, people['alice'], 'Leviathan Wakes', 'James S. A. Corey')
    db.commit()
    report = run(client, 'alice',
                 row('White Noise (Penguin Classics)', isbn13='="9780143129554"', isbn='=""'),
                 row('Leviathan Wakes (The Expanse, #1)', author='James S.A.  Corey'))
    assert report['outcomes']['filled'] == 2
    assert scalar(db, 'SELECT COUNT(*) FROM books') == 2
    assert status_of(db, people['alice'], by_isbn) == 'read'
    assert status_of(db, people['alice'], by_title) == 'read'


def test_to_read_on_a_book_you_own_changes_nothing(client, db, people):
    # Was: the owned book got the Want to Read status (decision 3: no more)
    owned = add_book(db, people['alice'], 'Owned', 'Some Author')
    report = run(client, 'alice', row('Owned', 'to-read'), row('Wanted', 'to-read'))
    assert outcome(report, 'Owned') == 'nothing'
    assert status_of(db, people['alice'], owned) is None
    assert scalar(db, 'SELECT COUNT(*) FROM wishlist WHERE book_id = ?', owned) == 0
    assert scalar(db, 'SELECT COUNT(*) FROM library_books WHERE id = ?', owned) == 1
    assert outcome(report, 'Wanted') == 'wishlist'


def test_reimport_and_wishlist_duplicates_are_reported(client, db, people):
    rows = [row('Read One'), row('Wanted', 'to-read'), row('Wanted Twice', 'to-read'),
            row('Wanted Twice', 'to-read')]
    first = run(client, 'alice', *rows)
    assert {k: v for k, v in first['outcomes'].items() if v} == {'not_owned': 1, 'wishlist': 2, 'nothing': 1}
    assert first['rows'][3]['detail'] == 'same book as line 4'
    second = run(client, 'alice', *rows)
    assert second['outcomes']['nothing'] == 4
    assert scalar(db, 'SELECT COUNT(*) FROM books') == 3


def test_read_row_on_your_wishlist_is_asked_then_moved_as_chosen(client, db, people):
    # Was: moved into the library (owned) without asking
    run(client, 'alice', row('Was Wanted', 'to-read'), row('Also Wanted', 'to-read'))
    book = scalar(db, "SELECT id FROM books WHERE title = 'Was Wanted'")
    report = run(client, 'alice', row('Was Wanted', 'read', date_read='2025/01/05'))
    assert outcome(report, 'Was Wanted') == 'later'
    assert scalar(db, 'SELECT COUNT(*) FROM wishlist WHERE book_id = ?', book) == 1

    report = run(client, 'alice', row('Was Wanted', 'read', date_read='2025/01/05'),
                 row('Also Wanted'), choices=[([2], 'bought'), ([3], 'drop_wish')])
    assert outcome(report, 'Was Wanted') == 'decided'
    assert scalar(db, 'SELECT COUNT(*) FROM wishlist WHERE book_id = ?', book) == 0
    assert scalar(db, 'SELECT COUNT(*) FROM library_books WHERE id = ? AND owned = 1', book) == 1
    assert status_of(db, people['alice'], book) == 'read'
    dropped = scalar(db, "SELECT id FROM books WHERE title = 'Also Wanted'")
    assert scalar(db, 'SELECT owned FROM books WHERE id = ?', dropped) == 0


# --- shelves, DNF, reviews, read count ---------------------------------------

def test_custom_shelves_do_not_become_collections(client, db, people):
    # Was: each custom shelf became a collection (decision 2)
    run(client, 'alice', row('Heard It', bookshelves='audiobook, re-read'),
        row('Want Audio', 'to-read', bookshelves='to-read, audiobook'))
    assert scalar(db, 'SELECT COUNT(*) FROM user_collections') == 0
    shelves = {r[0] for r in db.execute('SELECT shelves FROM goodreads_rows')}
    assert shelves == {'audiobook,re-read,read', 'to-read,audiobook'}


def test_dnf_shelf_sets_did_not_finish(client, db, people):
    run(client, 'alice', row('Quit Early', 'did-not-finish'),
        row('Also Quit', 'abandoned', read_count='0'),
        row('Shelved Dnf', 'my-custom', bookshelves='dnf', read_count='0'))
    for title in ('Quit Early', 'Also Quit', 'Shelved Dnf'):
        book = scalar(db, 'SELECT id FROM books WHERE title = ?', title)
        assert status_of(db, people['alice'], book) == 'did not finish', title
    assert scalar(db, 'SELECT COUNT(*) FROM user_collections') == 0
    assert scalar(db, 'SELECT COUNT(*) FROM reading_sessions') == 0


def test_reviews_without_rating_and_ratings_on_to_read(client, db, people):
    run(client, 'alice', row('Words Only', my_review='Good<br/><br/>Really &amp; truly'),
        row('Rated Wish', 'to-read', my_rating='4'))
    words = db.execute("SELECT r.* FROM read_data r JOIN books b ON b.id = r.book_id "
                       "WHERE b.title = 'Words Only'").fetchone()
    assert words['rating'] is None and words['comment'] == 'Good\n\nReally & truly'
    wish = db.execute("SELECT r.* FROM read_data r JOIN books b ON b.id = r.book_id "
                      "WHERE b.title = 'Rated Wish'").fetchone()
    assert wish['rating'] == 4


def test_read_count_becomes_sessions(client, db, people):
    run(client, 'alice', row('Twice', read_count='2', date_read='2024/03/08'),
        row('Undated', read_count='1'))
    twice = scalar(db, "SELECT id FROM books WHERE title = 'Twice'")
    dates = [r[0] for r in db.execute('SELECT date_completed FROM reading_sessions WHERE book_id = ? '
                                      'ORDER BY session_id', (twice,))]
    assert dates == [None, '2024-03-08']
    undated = scalar(db, "SELECT id FROM books WHERE title = 'Undated'")
    assert scalar(db, 'SELECT COUNT(*) FROM reading_sessions WHERE book_id = ?', undated) == 1

    # an undated read shows as "Date unknown", not "Currently Reading"
    page = client.get(f'/books/book/{twice}').get_data(as_text=True)
    assert 'Date unknown' in page and 'Currently Reading</span>' not in page


# --- robustness ----------------------------------------------------------------

def test_failing_row_leaves_nothing_behind(client, db, people, monkeypatch):
    from utils import goodreads
    original = goodreads.add_sessions

    def explode(conn, user_id, book_id, dates):
        if conn.execute('SELECT title FROM books WHERE id = ?', (book_id,)).fetchone()[0] == 'Bad Row':
            raise RuntimeError('boom')
        return original(conn, user_id, book_id, dates)
    monkeypatch.setattr(goodreads, 'add_sessions', explode)

    report = run(client, 'alice', row('Good Row'), row('Bad Row', my_rating='5'), row('After'))
    assert outcome(report, 'Bad Row') == 'error'
    assert outcome(report, 'Good Row') == outcome(report, 'After') == 'not_owned'
    assert scalar(db, "SELECT COUNT(*) FROM books WHERE title = 'Bad Row'") == 0
    assert scalar(db, 'SELECT COUNT(*) FROM read_data') == 0
    assert fk_violations(db) == []


def test_empty_values_are_null_and_created_at_never_null(client, db, people):
    run(client, 'alice', row('Sparse', number_of_pages='', year_published='', date_added=''),
        row('Dated', number_of_pages='320', year_published='2016', date_added='2016/5/9'))
    sparse = db.execute("SELECT * FROM books WHERE title = 'Sparse'").fetchone()
    assert sparse['page_count'] is None and sparse['publish_year'] is None
    assert sparse['created_at'] is not None
    assert scalar(db, "SELECT created_at FROM collections WHERE book_id = ?", sparse['id']) is not None
    dated = db.execute("SELECT * FROM books WHERE title = 'Dated'").fetchone()
    assert (dated['page_count'], dated['publish_year'], dated['created_at']) == (320, 2016, '2016-05-09')


def test_rows_without_title_are_nothing_to_do(client, db, people):
    # Was: counted as 'skipped'; 'skipped' now means you chose Skip
    report = run(client, 'alice', row('Real'), row(''))
    assert report['outcomes']['nothing'] == 1 and report['rows'][1]['detail'] == 'no title'


def test_encoding_and_file_checks(client, db, people):
    login(client, 'alice')
    # Windows-1252 (curly quotes), uppercase extension: staged, with a warning
    r = upload(client, csv_text(row('Don’t Panic')), filename='EXPORT.CSV', encoding='cp1252')
    assert r.status_code == 302
    page = client.get('/user/import_goodreads/review').get_data(as_text=True)
    assert 'read as cp1252' in page and 'Don’t Panic' in page
    # UTF-8 with a BOM: the first column name must still be found
    r = upload(client, '﻿' + csv_text(row('Bom')), filename='x.csv')
    assert r.status_code == 302
    assert 'Bom' in client.get('/user/import_goodreads/review').get_data(as_text=True)

    # Not an export, or not a .csv: back to the upload page with why
    r = upload(client, 'a,b\n1,2\n')
    assert r.status_code == 302 and r.headers['Location'].endswith('/user/import_goodreads_page')
    assert 'missing column' in client.get('/user/import_goodreads_page').get_data(as_text=True)
    r = client.post('/user/import_goodreads/plan', data={'goodreads_csv': (io.BytesIO(b'x'), 'x.txt')},
                    content_type='multipart/form-data', headers={'X-Requested-With': 'XMLHttpRequest'})
    assert r.status_code == 400 and r.get_json()['success'] is False
    assert scalar(db, 'SELECT COUNT(*) FROM books') == 0


# --- wishlist add-by-ISBN uses the same rule ---------------------------------------

def test_wishlist_add_never_reuses_someone_elses_book(client, db, people):
    dave = add_user(db, 'dave')
    for owner in (dave, people['bob']):  # a stranger's and a household member's copy
        b = add_book(db, owner, 'Shared Isbn', 'X')
        db.execute("UPDATE books SET isbn = '9780000000002' WHERE id = ?", (b,))
    db.commit()
    login(client, 'alice')
    r = client.post('/wishlist/view', data={'submit_book': '1', 'title': 'Shared Isbn', 'author': 'X',
                                            'isbn': '9780000000002'})
    assert r.status_code == 302
    wished = scalar(db, 'SELECT book_id FROM wishlist WHERE user_id = ?', people['alice'])
    assert scalar(db, 'SELECT added_by FROM books WHERE id = ?', wished) == people['alice']


def test_wishlist_add_refuses_a_book_in_your_library(client, db, people):
    mine = add_book(db, people['alice'], 'Mine', 'X')
    db.execute("UPDATE books SET isbn = '0143129554' WHERE id = ?", (mine,))
    db.commit()
    login(client, 'alice')
    r = client.post('/wishlist/add', data={'title': 'Mine', 'author': 'X', 'isbn': '9780143129554'})
    assert r.status_code == 302 and f'/books/book/{mine}' in r.headers['Location']
    assert scalar(db, 'SELECT COUNT(*) FROM wishlist') == 0
    assert scalar(db, 'SELECT COUNT(*) FROM library_books WHERE id = ?', mine) == 1


def test_review_without_rating_can_be_saved_and_shown(client, db, people):
    book = add_book(db, people['alice'], 'Words', 'X')
    login(client, 'alice')
    r = client.post(f'/read/rate_review/{book}', data={'comment': 'No stars, just thoughts'})
    assert r.status_code == 302
    assert scalar(db, 'SELECT rating FROM read_data WHERE book_id = ?', book) is None
    page = client.get(f'/books/book/{book}').get_data(as_text=True)
    assert 'No stars, just thoughts' in page and 'None / 5' not in page
    # neither a rating nor a review: refused
    other = add_book(db, people['alice'], 'Empty', 'X')
    client.post(f'/read/rate_review/{other}', data={'comment': ''})
    assert scalar(db, 'SELECT COUNT(*) FROM read_data WHERE book_id = ?', other) == 0


def test_saving_a_review_without_dates_adds_no_session(client, db, people):
    book = add_book(db, people['alice'], 'Words', 'X')
    login(client, 'alice')
    for rating in ('4', '5'):
        client.post(f'/read/rate_review/{book}',
                    data={'rating': rating, 'comment': 'a', 'date_started': '', 'date_completed': ''})
    assert scalar(db, 'SELECT COUNT(*) FROM reading_sessions WHERE book_id = ?', book) == 0
    client.post(f'/read/rate_review/{book}', data={'rating': '5', 'date_completed': '2024-02-02'})
    assert scalar(db, 'SELECT COUNT(*) FROM reading_sessions WHERE book_id = ?', book) == 1


# --- audiobooks (ROADMAP 8B.2) ------------------------------------------------

def test_audiobook_shelf_imports_as_not_owned_audiobook(client, db, people):
    run(client, 'carol',
        row('Heard It', bookshelves='audiobook', number_of_pages='400', my_rating='4'),
        row('By Binding', binding='Audible Audio'),
        row('Paper Copy', number_of_pages='200'),
        row('Want The Audio', shelf='to-read', bookshelves='to-read, audiobook'))
    got = {r['title']: (r['format'], r['owned']) for r in
           db.execute('SELECT title, format, owned FROM books')}
    # Paper Copy was (None, 1): read books now come in not owned by default
    assert got == {'Heard It': ('Audiobook', 0), 'By Binding': ('Audiobook', 0),
                   'Paper Copy': (None, 0), 'Want The Audio': ('Audiobook', 1)}
    heard = scalar(db, "SELECT id FROM books WHERE title = 'Heard It'")
    assert status_of(db, people['carol'], heard) == 'read'
    assert scalar(db, 'SELECT rating FROM read_data WHERE book_id = ?', heard) == 4


def test_audiobook_row_matching_a_book_you_own_leaves_it_alone(client, db, people):
    book = add_book(db, people['carol'], title='Already Mine', author='Some Author')
    run(client, 'carol', row('Already Mine', bookshelves='audiobook'))
    assert db.execute('SELECT format, owned FROM books WHERE id = ?', (book,)).fetchone()[:] == (None, 1)


# --- parser fields for the granular import (ROADMAP 14b step 1) ---------------

def test_parse_row_keeps_the_goodreads_book_id():
    # Book Id is Goodreads' stable id for the book: the next import matches
    # on it even after the book is retitled or re-ISBN'd here.
    from utils.goodreads import parse_row
    assert parse_row(row('Dune', book_id='234225'))['goodreads_id'] == '234225'
    assert parse_row(row('Dune', book_id='  234225 '))['goodreads_id'] == '234225'
    assert parse_row(row('Dune'))['goodreads_id'] is None
    # An export without the column at all still parses
    bare = {'Title': 'Dune', 'Author': 'Frank Herbert', 'Exclusive Shelf': 'read'}
    assert parse_row(bare)['goodreads_id'] is None


def test_parse_row_keeps_every_shelf_raw():
    # Unlike `collections`, `shelves` keeps the status shelves too, so the
    # review page can filter by any shelf in the file and the provenance
    # records what Goodreads said. Order kept, duplicates and blanks dropped,
    # the exclusive shelf last if the Bookshelves column didn't list it.
    from utils.goodreads import parse_row
    r = parse_row(row('Dune', bookshelves='Sci-Fi,  2019-challenge, read,,sci-fi'))
    assert r['shelves'] == ['sci-fi', '2019-challenge', 'read']
    assert r['collections'] == ['sci-fi', '2019-challenge']

    assert parse_row(row('Wanted', shelf='to-read'))['shelves'] == ['to-read']
    assert parse_row(row('Gave Up', shelf='dnf', bookshelves='dnf, kindle'))['shelves'] == ['dnf', 'kindle']
    # An unknown exclusive shelf with no reading recorded: the "Not sure" box
    unsure = parse_row(row('Maybe', shelf='Kindle-Deals', read_count='0'))
    assert unsure['status'] is None and unsure['shelves'] == ['kindle-deals']
    assert parse_row({'Title': 'Bare'})['shelves'] == []


def test_parse_row_new_fields_change_nothing_else():
    # Step 1 adds two keys and must not move any existing value
    from utils.goodreads import parse_row
    r = parse_row(row('Dune', book_id='1', bookshelves='audiobook, re-read', my_rating='4',
                      date_read='2021/06/30', isbn13='="9780441172719"'))
    assert set(r) == {'title', 'author', 'isbns', 'publisher', 'year', 'pages', 'rating',
                      'review', 'private_notes', 'date_read', 'date_added', 'read_count',
                      'status', 'collections', 'audiobook', 'goodreads_id', 'shelves'}
    assert (r['status'], r['rating'], r['date_read'], r['audiobook'], r['isbns'],
            r['collections']) == ('read', 4, '2021-06-30', True, ['9780441172719'],
                                  ['audiobook', 're-read'])


# --- the review routes (ROADMAP 14b step 5) ---------------------------------------

def test_review_without_an_upload_goes_back_to_the_import_page(client, db, people):
    login(client, 'alice')
    r = client.get('/user/import_goodreads/review')
    assert r.status_code == 302 and r.headers['Location'].endswith('/user/import_goodreads_page')
    assert 'Upload your export first' in client.get('/user/import_goodreads_page').get_data(as_text=True)


def test_review_page_shows_every_box_and_the_import_page_says_one_is_waiting(client, db, people):
    from test_layout import unbalanced_tags
    alice = people['alice']
    add_book(db, alice, 'On Shelf', 'Some Author')
    add_book(db, alice, 'Owned Want', 'Some Author')
    wished = add_book(db, alice, 'Wished', 'Some Author')
    db.execute('INSERT INTO wishlist (user_id, book_id) VALUES (?, ?)', (alice, wished))
    db.commit()
    login(client, 'alice')
    upload(client, csv_text(row('New <b>Book</b>'), row('On Shelf', my_rating='4'), row('Wanted', 'to-read'),
                            row('Owned Want', 'to-read'), row('Reading', 'currently-reading'), row('Wished'),
                            row('Kindle', 'kindle-deals', read_count='0'), row('')))
    page = client.get('/user/import_goodreads/review').get_data(as_text=True)
    from utils.goodreads_plan import BOXES
    for box in BOXES.values():
        assert box['title'] in page, box['title']
    assert 'Import 3, leave 2 undecided' in page
    assert 'New &lt;b&gt;Book&lt;/b&gt;' in page and '<b>Book' not in page
    assert unbalanced_tags(page) == []
    assert 'waiting for review' in client.get('/user/import_goodreads_page').get_data(as_text=True)


def test_choose_route_refuses_bad_choices_and_other_users_rows(client, db, people):
    login(client, 'alice')
    upload(client, csv_text(row('Mine'), row('Wanted', 'to-read')))
    r = client.post('/user/import_goodreads/choose', json={'lines': [2, 3], 'choice': 'library'})
    data = r.get_json()
    assert r.status_code == 200 and data['saved'] == [2] and data['refused'][0]['line'] == 3
    assert data['rows']['2']['choice'] == 'library' and data['will_write'] == 2
    for body in ({'lines': [2], 'choice': 'ask'}, {'lines': [2], 'choice': 'delete'}, {'lines': [], 'choice': 'skip'}):
        r = client.post('/user/import_goodreads/choose', json=body)
        assert r.status_code == 400 and r.get_json()['success'] is False
    client.post('/auth/logout')
    login(client, 'bob')
    r = client.post('/user/import_goodreads/choose', json={'lines': [2], 'choice': 'skip'})
    assert r.status_code == 400
    r = client.post('/user/import_goodreads/apply', json={'fingerprint': 'x'})
    assert r.status_code == 400
    assert scalar(db, "SELECT choice FROM goodreads_staging WHERE line = 2") == 'library'


def test_apply_route_refuses_a_stale_review(client, db, people):
    login(client, 'alice')
    upload(client, csv_text(row('Mine')))
    old = fingerprint(client)
    client.post('/user/import_goodreads/choose', json={'lines': [2], 'choice': 'library'})
    r = client.post('/user/import_goodreads/apply', json={'fingerprint': old})
    assert r.status_code == 409 and r.get_json()['stale'] is True
    assert scalar(db, 'SELECT COUNT(*) FROM books') == 0
    assert 'changed since you looked' in client.get('/user/import_goodreads/review').get_data(as_text=True)


def test_start_over_discards_the_upload(client, db, people):
    login(client, 'alice')
    upload(client, csv_text(row('Mine')))
    r = client.post('/user/import_goodreads/discard')
    assert r.status_code == 302 and scalar(db, 'SELECT COUNT(*) FROM goodreads_staging') == 0
    assert client.get('/user/import_goodreads/review').status_code == 302


def test_import_is_undone_through_the_bulk_route_and_listed_on_the_profile(client, db, people, monkeypatch):
    from utils import goodreads_plan
    monkeypatch.setattr(goodreads_plan, 'delete_image_file', lambda path: None)
    report = run(client, 'alice', row('Undo Me'), row('Wanted', 'to-read'))
    assert report['summary'] == 'Goodreads import: 1 added as not owned, 1 to your wishlist'
    profile = client.get('/user/alice').get_data(as_text=True)
    assert report['summary'] in profile
    r = client.post(f"/bulk/{report['edit_id']}/undo", json={'banner': False})
    assert r.status_code == 200 and r.get_json()['restored'] == 2
    assert scalar(db, 'SELECT COUNT(*) FROM books') == 0
    # bob can't undo alice's import
    report = run(client, 'alice', row('Again'))
    client.post('/auth/logout')
    login(client, 'bob')
    assert client.post(f"/bulk/{report['edit_id']}/undo", json={}).status_code == 400
    assert scalar(db, 'SELECT COUNT(*) FROM books') == 1


def test_the_old_one_pass_import_route_is_gone(client, db, people):
    login(client, 'alice')
    r = client.post('/user/import_goodreads', data={'goodreads_csv': (io.BytesIO(csv_text(row('X')).encode()), 'x.csv')},
                    content_type='multipart/form-data')
    assert r.status_code in (404, 405)
    assert scalar(db, 'SELECT COUNT(*) FROM books') == 0
