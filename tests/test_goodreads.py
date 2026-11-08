"""Goodreads import (utils/goodreads.py, user.import_goodreads) and the
own-books-only matching it shares with the wishlist (utils/book_matching.py)."""
import csv
import io

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
    return client.post('/user/import_goodreads', data=data, content_type='multipart/form-data')


def run(client, username, *rows):
    login(client, username)
    r = upload(client, csv_text(*rows))
    assert r.status_code == 200, r.get_json()
    report = r.get_json()
    # The result screen must account for every row
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

    assert outcome(report, 'Dune') == 'added'
    mine = scalar(db, "SELECT id FROM books WHERE added_by = ? AND title = 'Dune'", people['alice'])
    assert mine != theirs
    assert status_of(db, people['alice'], mine) == 'read'
    assert status_of(db, people['alice'], theirs) is None


def test_household_copy_is_matched_and_own_copy_wins(client, db, people):
    bobs = add_book(db, people['bob'], 'Dune', 'Frank Herbert')
    carols = add_book(db, people['carol'], 'Emma', 'Jane Austen')  # friend, not household
    report = run(client, 'alice', row('Dune', author='Frank Herbert'),
                 row('Emma', author='Jane Austen'))
    assert outcome(report, 'Dune') == 'matched'
    assert status_of(db, people['alice'], bobs) == 'read'
    assert scalar(db, "SELECT COUNT(*) FROM books WHERE title = 'Dune'") == 1
    # a friend's copy is not your household's: a new book
    assert outcome(report, 'Emma') == 'added'
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
    assert report['outcomes']['matched'] == 2
    assert report['totals']['books_created'] == 0
    assert status_of(db, people['alice'], by_isbn) == 'read'
    assert status_of(db, people['alice'], by_title) == 'read'


def test_to_read_on_a_book_you_own_is_want_to_read_not_wishlist(client, db, people):
    owned = add_book(db, people['alice'], 'Owned', 'Some Author')
    report = run(client, 'alice', row('Owned', 'to-read'), row('Wanted', 'to-read'))
    assert outcome(report, 'Owned') == 'matched'
    assert status_of(db, people['alice'], owned) == 'want to read'
    # still in the library (a wishlist row on your own book would hide it)
    assert scalar(db, 'SELECT COUNT(*) FROM wishlist WHERE book_id = ?', owned) == 0
    assert scalar(db, 'SELECT COUNT(*) FROM library_books WHERE id = ?', owned) == 1
    assert outcome(report, 'Wanted') == 'wishlist'


def test_reimport_and_wishlist_duplicates_are_reported(client, db, people):
    rows = [row('Read One'), row('Wanted', 'to-read'), row('Wanted Twice', 'to-read'),
            row('Wanted Twice', 'to-read')]
    first = run(client, 'alice', *rows)
    assert first['outcomes'] == {'added': 1, 'matched': 0, 'wishlist': 2, 'already': 1,
                                 'skipped': 0, 'error': 0}
    second = run(client, 'alice', *rows)
    assert second['outcomes']['already'] == 4
    assert scalar(db, 'SELECT COUNT(*) FROM books') == 3


def test_read_row_moves_your_wishlist_entry_into_the_library(client, db, people):
    run(client, 'alice', row('Was Wanted', 'to-read'))
    report = run(client, 'alice', row('Was Wanted', 'read', date_read='2025/01/05'))
    book = scalar(db, "SELECT id FROM books WHERE title = 'Was Wanted'")
    assert outcome(report, 'Was Wanted') == 'matched'
    assert scalar(db, 'SELECT COUNT(*) FROM wishlist WHERE book_id = ?', book) == 0
    assert scalar(db, 'SELECT COUNT(*) FROM library_books WHERE id = ?', book) == 1
    assert status_of(db, people['alice'], book) == 'read'


# --- shelves, DNF, reviews, read count ---------------------------------------

def test_custom_shelves_become_collections(client, db, people):
    report = run(client, 'alice',
                 row('Heard It', bookshelves='audiobook, re-read'),
                 row('Heard Too', bookshelves='audiobook'),
                 row('Want Audio', 'to-read', bookshelves='to-read, audiobook'))
    assert set(report['collections_created']) == {'audiobook', 're-read'}
    counts = dict(db.execute('''SELECT uc.name, COUNT(*) FROM collection_books cb
                                JOIN user_collections uc USING (collection_id)
                                WHERE uc.user_id = ? GROUP BY uc.name''', (people['alice'],)).fetchall())
    assert counts == {'audiobook': 3, 're-read': 1}
    assert report['outcomes']['error'] == 0


def test_dnf_shelf_sets_did_not_finish(client, db, people):
    run(client, 'alice', row('Quit Early', 'did-not-finish'),
        row('Also Quit', 'abandoned', read_count='0'),
        row('Shelved Dnf', 'my-custom', bookshelves='dnf', read_count='0'))
    for title in ('Quit Early', 'Also Quit', 'Shelved Dnf'):
        book = scalar(db, 'SELECT id FROM books WHERE title = ?', title)
        assert status_of(db, people['alice'], book) == 'did not finish', title
    # the DNF shelf itself is not also made a collection; a real custom one is
    names = {r['name'] for r in db.execute('SELECT name FROM user_collections')}
    assert names == {'my-custom'}
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
    original = goodreads._Importer.add_sessions

    def explode(self, book_id, r):
        if r['title'] == 'Bad Row':
            raise RuntimeError('boom')
        return original(self, book_id, r)
    monkeypatch.setattr(goodreads._Importer, 'add_sessions', explode)

    report = run(client, 'alice', row('Good Row'), row('Bad Row', my_rating='5', bookshelves='odd-one'),
                 row('After', bookshelves='odd-one'))
    assert outcome(report, 'Bad Row') == 'error'
    assert outcome(report, 'Good Row') == outcome(report, 'After') == 'added'
    assert scalar(db, "SELECT COUNT(*) FROM books WHERE title = 'Bad Row'") == 0
    assert scalar(db, 'SELECT COUNT(*) FROM read_data') == 0
    # the collection the failed row created was rolled back and made again for "After"
    assert scalar(db, "SELECT COUNT(*) FROM user_collections WHERE name = 'odd-one'") == 1
    assert scalar(db, 'SELECT COUNT(*) FROM collection_books') == 1
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


def test_rows_without_title_are_counted_as_skipped(client, db, people):
    report = run(client, 'alice', row('Real'), row(''))
    assert report['outcomes']['skipped'] == 1


def test_encoding_and_file_checks(client, db, people):
    login(client, 'alice')
    # Windows-1252 (curly quotes), uppercase extension
    r = upload(client, csv_text(row('Don’t Panic')), filename='EXPORT.CSV', encoding='cp1252')
    assert r.status_code == 200 and r.get_json()['encoding'] == 'cp1252'
    assert scalar(db, 'SELECT title FROM books') == 'Don’t Panic'
    # UTF-8 with a BOM: the first column name must still be found
    r = upload(client, '﻿' + csv_text(row('Bom')))
    assert r.status_code == 200 and r.get_json()['encoding'] == 'utf-8-sig'

    assert upload(client, 'a,b\n1,2\n').status_code == 400          # not a Goodreads export
    assert upload(client, csv_text(row('X')), filename='x.txt').status_code == 400


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
    assert got == {'Heard It': ('Audiobook', 0), 'By Binding': ('Audiobook', 0),
                   'Paper Copy': (None, 1), 'Want The Audio': ('Audiobook', 1)}
    heard = scalar(db, "SELECT id FROM books WHERE title = 'Heard It'")
    assert status_of(db, people['carol'], heard) == 'read'
    assert scalar(db, 'SELECT rating FROM read_data WHERE book_id = ?', heard) == 4


def test_audiobook_row_matching_a_book_you_own_leaves_it_alone(client, db, people):
    book = add_book(db, people['carol'], title='Already Mine', author='Some Author')
    run(client, 'carol', row('Already Mine', bookshelves='audiobook'))
    assert db.execute('SELECT format, owned FROM books WHERE id = ?', (book,)).fetchone()[:] == (None, 1)
