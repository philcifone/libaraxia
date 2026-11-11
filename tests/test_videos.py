"""Phase 8: videos (VHS) as their own section, in the same books table.

The rule the tests hold the code to (ROADMAP 8.1): a video shows in the
Videos section, with its barcode, runtime and studio, can be watched and
reviewed, and is shared like a book; no video ever appears in the Library,
book stats, book search or filters, the Goodreads matcher, the cover fetcher
or the book duplicate check.

people: alice (admin) + bob share a household; carol is alice's friend.
"""
import re

import pytest

from conftest import add_book, add_user, login, scalar
from utils import media

UPC = '012345678905'           # a valid UPC-A; stored as EAN-13 0012345678905
EAN = '0' + UPC
OTHER_EAN = '4006381333931'    # valid non-book EAN-13
ISBN13 = '9780306406157'
ISBN10 = '0306406152'


def add_video(db, owner_id, title='Jaws', director='Steven Spielberg', barcode=EAN,
              runtime=124, studio='MCA Home Video', fmt='VHS'):
    cur = db.execute('''
        INSERT INTO books (title, author, publisher, runtime_minutes, barcode, format,
                           added_by, media_type)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'video')
    ''', (title, director, studio, runtime, barcode, fmt, owner_id))
    db.commit()
    return cur.lastrowid


def form(**overrides):
    data = {'title': 'Jaws', 'author': 'Steven Spielberg', 'publisher': 'MCA Home Video',
            'year': '1985', 'runtime_minutes': '124', 'format': 'VHS', 'barcode': UPC,
            'catalog_number': '80123', 'genre': 'Thriller', 'description': ''}
    data.update(overrides)
    return data


# --- barcode helpers (server twin of scanner.js) -------------------------------

@pytest.mark.parametrize('code, kind', [
    (ISBN13, 'book'),
    ('979-10-90636-07-1', 'book'),   # 979 prefix, hyphens allowed when typed
    (ISBN10, 'book'),
    ('080442957X', 'book'),          # ISBN-10 with an X check digit
    (UPC, 'video'),                  # UPC-A
    (EAN, 'video'),                  # the same, as EAN-13
    (OTHER_EAN, 'video'),
    ('012345678906', None),          # bad check digit
    ('12345', None),
    ('', None),
])
def test_classify_code(code, kind):
    assert media.classify_code(code) == kind


def test_normalize_barcode_pads_upc_a():
    assert media.normalize_barcode(UPC) == EAN
    assert media.normalize_barcode(EAN) == EAN
    assert media.normalize_barcode('012345678906') is None


def test_labels_differ_by_type():
    assert media.media_labels('book')['creator'] == 'Author'
    assert media.media_labels('video')['creator'] == 'Director'
    assert media.media_labels('video')['statuses'] == ('watched', 'want to watch')
    assert media.format_runtime(95) == '1 h 35 min'
    with pytest.raises(ValueError):
        media.only('dvd')


# --- schema ------------------------------------------------------------------

def test_views_split_books_and_videos(db, people):
    book = add_book(db, people['alice'], 'Dune')
    video = add_video(db, people['alice'])
    assert [r[0] for r in db.execute('SELECT id FROM library_books')] == [book]
    assert [r[0] for r in db.execute('SELECT id FROM library_videos')] == [video]
    assert scalar(db, "SELECT media_type FROM books WHERE id = ?", book) == 'book'


def test_collections_accept_watch_statuses(db, people):
    video = add_video(db, people['alice'])
    for status in ('watched', 'want to watch'):
        db.execute('INSERT OR REPLACE INTO collections (user_id, book_id, status) VALUES (?, ?, ?)',
                   (people['alice'], video, status))
    db.commit()


# --- adding ------------------------------------------------------------------

def test_add_video_by_hand(client, db, people):
    login(client, 'alice')
    r = client.post('/videos/add', data=form())
    assert r.status_code == 302
    row = db.execute("SELECT * FROM books WHERE title = 'Jaws'").fetchone()
    assert row['media_type'] == 'video'
    assert row['barcode'] == EAN               # UPC-A stored as EAN-13
    assert row['runtime_minutes'] == 124 and row['catalog_number'] == '80123'
    assert row['added_by'] == people['alice']
    assert r.headers['Location'].endswith(f"/videos/{row['id']}")


def test_add_form_prefills_scanned_barcode(client, people):
    login(client, 'alice')
    page = client.get(f'/videos/add?barcode={UPC}').get_data(as_text=True)
    assert f'value="{EAN}"' in page


def test_barcode_must_be_valid_and_not_an_isbn(client, db, people):
    login(client, 'alice')
    assert client.post('/videos/add', data=form(barcode='012345678906')).status_code == 400
    r = client.post('/videos/add', data=form(barcode=ISBN13))
    assert r.status_code == 400 and 'ISBN' in r.get_data(as_text=True)
    assert scalar(db, "SELECT COUNT(*) FROM books WHERE media_type = 'video'") == 0


def test_no_barcode_is_fine(client, db, people):
    """Older tapes have no barcode at all: manual entry must not need one."""
    login(client, 'alice')
    assert client.post('/videos/add', data=form(barcode='', title='Old Tape')).status_code == 302
    assert scalar(db, "SELECT barcode FROM books WHERE title = 'Old Tape'") is None


def test_duplicate_barcode_in_household_needs_confirmation(client, db, people):
    add_video(db, people['bob'], title='Jaws (other copy)')
    login(client, 'alice')
    r = client.post('/videos/add', data=form(title='Jaws again'))
    assert r.status_code == 400 and 'Already on your household' in r.get_data(as_text=True)
    assert client.post('/videos/add', data=form(title='Jaws again', confirm_duplicate='1')).status_code == 302
    assert scalar(db, "SELECT COUNT(*) FROM books WHERE barcode = ?", EAN) == 2


def test_duplicate_check_api_ignores_strangers(client, db, people):
    dave = add_user(db, 'dave')
    add_video(db, dave)
    login(client, 'alice')
    data = client.post('/videos/check_duplicates', json={'barcode': UPC}).get_json()
    assert data['has_duplicates'] is False
    add_video(db, people['bob'])
    data = client.post('/videos/check_duplicates', json={'barcode': UPC}).get_json()
    assert data['has_duplicates'] is True and data['duplicates'][0]['match_reason'] == ['barcode']


def test_edit_video(client, db, people):
    video = add_video(db, people['alice'])
    login(client, 'alice')
    r = client.post(f'/videos/edit/{video}', data=form(runtime_minutes='130', format='DVD'))
    assert r.status_code == 302
    row = db.execute('SELECT * FROM books WHERE id = ?', (video,)).fetchone()
    assert row['runtime_minutes'] == 130 and row['format'] == 'DVD'
    login(client, 'carol')                   # a friend can see it but not edit it
    assert client.get(f'/videos/edit/{video}').status_code == 404


# --- scanner dispatch --------------------------------------------------------

def test_barcode_endpoint_sends_videos_to_the_videos_section(client, people):
    login(client, 'alice')
    data = client.get(f'/books/fetch_barcode_details?code={UPC}').get_json()
    assert data['media_type'] == 'video' and data['barcode'] == EAN
    assert data['add_url'].startswith('/videos/add')
    # the old endpoint name still answers, the same way
    assert client.get(f'/books/fetch_isbn_details?isbn={UPC}').get_json()['media_type'] == 'video'


def test_typed_upc_on_add_book_redirects_to_videos(client, people):
    login(client, 'alice')
    r = client.post('/books/add', data={'isbn_lookup': '1', 'isbn': UPC})
    assert r.status_code == 302 and '/videos/add' in r.headers['Location']


# --- the Videos pages --------------------------------------------------------

def test_detail_page_shows_video_fields(client, db, people):
    video = add_video(db, people['alice'])
    login(client, 'alice')
    page = client.get(f'/videos/{video}').get_data(as_text=True)
    for text in ('directed by', 'MCA Home Video', 'Studio', EAN, '2 h 4 min',
                 'Watch Status', 'Want to Watch'):
        assert text in page, text
    assert 'Page Count' not in page and 'Want to Read' not in page


def test_book_url_redirects_to_video_page(client, db, people):
    video = add_video(db, people['alice'])
    login(client, 'alice')
    r = client.get(f'/books/book/{video}')
    assert r.status_code == 302 and r.headers['Location'].endswith(f'/videos/{video}')
    book = add_book(db, people['alice'], 'Dune')
    assert client.get(f'/videos/{book}').headers['Location'].endswith(f'/books/book/{book}')


def test_grid_search_and_filters(client, db, people):
    add_video(db, people['alice'], title='Jaws')
    add_video(db, people['alice'], title='Alien', director='Ridley Scott', barcode=None, fmt='DVD')
    login(client, 'alice')
    page = client.get('/videos/').get_data(as_text=True)
    assert 'Jaws' in page and 'Alien' in page
    page = client.get('/videos/?search_term=ridley').get_data(as_text=True)
    assert 'Alien' in page and 'Jaws' not in page
    page = client.get('/videos/?format=VHS').get_data(as_text=True)
    assert 'Jaws' in page and 'Alien' not in page


def test_section_is_called_movies(client, db, people):
    # The UI says "Movies" (Phil, 2026-11-07); code, URLs and the DB keep "video"
    login(client, 'alice')
    assert 'My Movies' in client.get('/videos/').get_data(as_text=True)
    assert 'Household Movies' in client.get('/videos/shared').get_data(as_text=True)
    # Friends are their own page (11.3); the old tab redirects there
    assert client.get('/videos/friends').headers['Location'].endswith('/friends/')
    assert 'Video' not in client.get('/videos/add').get_data(as_text=True).replace('lookupVideo', '')


def test_format_labels():
    assert media.format_label('VHS') == 'Cartridge'
    assert media.format_label('DVD') == 'DVD'
    assert media.format_label(None) == ''


def test_vhs_shows_as_cartridge_dvd_as_dvd(client, db, people):
    tape = add_video(db, people['alice'], title='Jaws')
    disc = add_video(db, people['alice'], title='Alien', barcode=None, fmt='DVD')
    login(client, 'alice')
    page = client.get('/videos/').get_data(as_text=True)
    # No format badge on the grid (Phil, 2026-11-11); the filter names VHS Cartridge
    assert 'title="Cartridge"' not in page and 'title="DVD"' not in page
    assert '<option value="VHS"' in page and '>Cartridge</option>' in page
    # The item page: the icon beside the title, named for screen readers
    page = client.get(f'/videos/{tape}').get_data(as_text=True)
    assert 'aria-label="Cartridge"' in page and 'aria-label="VHS"' not in page
    page = client.get(f'/videos/{disc}').get_data(as_text=True)
    assert 'aria-label="DVD"' in page


def test_add_dvd_filter_and_count(client, db, people):
    login(client, 'alice')
    client.post('/videos/add', data=form(title='Alien', barcode='', format='DVD'))
    assert scalar(db, "SELECT format FROM books WHERE title = 'Alien'") == 'DVD'
    add_video(db, people['alice'], title='Jaws')
    page = client.get('/videos/?format=DVD').get_data(as_text=True)
    assert 'Alien' in page and 'Jaws' not in page
    profile = client.get('/user/alice').get_data(as_text=True)
    assert 'DVD: 1' in profile and 'Cartridge: 1' in profile


def test_movies_filters_use_library_names(client, db, people):
    # The shared header search/filter panel sends the Library's parameter names
    jaws = add_video(db, people['alice'], title='Jaws')
    add_video(db, people['alice'], title='Alien', barcode=None, fmt='DVD')
    db.execute("UPDATE books SET genre = 'Horror' WHERE title = 'Alien'")
    db.execute("INSERT INTO collections (user_id, book_id, status) VALUES (?, ?, 'watched')",
               (people['alice'], jaws))
    db.execute("INSERT INTO book_tags (user_id, book_id, tag_name) VALUES (?, ?, 'shark')",
               (people['alice'], jaws))
    db.commit()
    login(client, 'alice')
    for query, shown, hidden in [('genre=horror', 'Alien', 'Jaws'),
                                 ('read_status=watched', 'Jaws', 'Alien'),
                                 ('tags[]=shark', 'Jaws', 'Alien'),
                                 ('format=DVD', 'Alien', 'Jaws')]:
        page = client.get(f'/videos/?{query}').get_data(as_text=True)
        assert f'>{shown}<' in page and f'>{hidden}<' not in page, query


def test_movies_header_search_stays_on_the_page(client, db, people):
    add_video(db, people['alice'], fmt='DVD')
    login(client, 'alice')
    page = client.get('/videos/shared').get_data(as_text=True)
    assert 'search-form-container' in page
    assert 'action="/videos/shared"' in page          # not books.search
    assert 'All Formats' in page and 'Watch Status' in page
    assert 'Add a Movie' not in page                  # the floating button replaced it


def test_filter_options_per_section(db, people):
    """The Library's filters never offer movie statuses, genres, tags or formats."""
    from flask_login import login_user
    from models import User
    from utils.book_utils import get_filter_options
    alice = people['alice']
    jaws = add_video(db, alice)
    book = add_book(db, alice, title='Dune')
    db.execute("UPDATE books SET genre = 'Horror' WHERE id = ?", (jaws,))
    db.execute("INSERT INTO collections (user_id, book_id, status) VALUES (?, ?, 'watched')", (alice, jaws))
    db.execute("INSERT INTO collections (user_id, book_id, status) VALUES (?, ?, 'read')", (alice, book))
    db.execute("INSERT INTO book_tags (user_id, book_id, tag_name) VALUES (?, ?, 'shark')", (alice, jaws))
    db.commit()
    from app import create_app
    app = create_app()
    with app.test_request_context():
        row = db.execute('SELECT * FROM users WHERE id = ?', (alice,)).fetchone()
        login_user(User(row['id'], row['username'], row['email'], row['password'], row['is_admin']))
        books = get_filter_options([alice])
        assert books['read_statuses'] == ['read'] and books['tags'] == [] and not books.get('formats')   # no audiobooks yet
        movies = get_filter_options([alice], media.VIDEO)
        assert movies['read_statuses'] == ['watched'] and movies['tags'] == ['shark']
        assert movies['genres'] == ['Horror'] and movies['formats'] == ['VHS']


def test_add_button_menus(client, db, people):
    login(client, 'alice')
    library = client.get('/base/index').get_data(as_text=True)
    assert '>Library</a>' in library and '>Wishlist</a>' in library
    movies = client.get('/videos/').get_data(as_text=True)
    assert 'href="/videos/add?format=VHS"' in movies and '>Cartridge</a>' in movies
    assert 'href="/videos/add?format=DVD"' in movies
    # The form opens with that format picked; nonsense falls back to VHS
    assert '<option value="DVD" selected' in client.get('/videos/add?format=DVD').get_data(as_text=True)
    assert '<option value="VHS" selected' in client.get('/videos/add?format=Betamax').get_data(as_text=True)


def test_household_and_friends_see_videos(client, db, people):
    video = add_video(db, people['alice'])
    login(client, 'bob')                     # household
    assert 'Jaws' in client.get('/videos/shared').get_data(as_text=True)
    assert client.get(f'/videos/{video}').status_code == 200
    login(client, 'carol')                   # friend
    assert 'Jaws' in client.get('/videos/user/alice').get_data(as_text=True)
    assert 'alice' in client.get('/friends/').get_data(as_text=True)
    assert client.get(f'/videos/{video}').status_code == 200


def test_strangers_see_nothing(client, db, people):
    video = add_video(db, people['alice'])
    add_user(db, 'dave')
    login(client, 'dave')
    assert client.get(f'/videos/{video}').status_code == 404
    assert client.get('/videos/user/alice').status_code == 404
    assert 'Jaws' not in client.get('/videos/shared').get_data(as_text=True)


# --- watch status, reviews, feed --------------------------------------------

def test_watched_status_goes_to_review(client, db, people):
    video = add_video(db, people['alice'])
    login(client, 'alice')
    r = client.post('/collections/collections/status/add', data={'id': video, 'status': 'watched'})
    assert r.status_code == 302 and f'/read/rate_review/{video}' in r.headers['Location']
    assert scalar(db, 'SELECT status FROM collections WHERE book_id = ?', video) == 'watched'


def test_statuses_are_checked_against_the_type(client, db, people):
    video = add_video(db, people['alice'])
    book = add_book(db, people['alice'], 'Dune')
    login(client, 'alice')
    client.post('/collections/collections/status/add', data={'id': video, 'status': 'read'},
                headers={'Referer': '/videos/'})
    client.post('/collections/collections/status/add', data={'id': book, 'status': 'watched'},
                headers={'Referer': '/base/index'})
    assert scalar(db, 'SELECT COUNT(*) FROM collections') == 0


def test_untracked_clears_the_status(client, db, people):
    book = add_book(db, people['alice'], 'Dune')
    db.execute("INSERT INTO collections (user_id, book_id, status) VALUES (?, ?, 'read')",
               (people['alice'], book))
    db.commit()
    login(client, 'alice')
    client.post('/collections/collections/status/add', data={'id': book, 'status': 'untracked'},
                headers={'Referer': '/base/index'})
    assert scalar(db, 'SELECT COUNT(*) FROM collections') == 0


def test_review_returns_to_the_video(client, db, people):
    video = add_video(db, people['alice'])
    login(client, 'alice')
    page = client.get(f'/read/rate_review/{video}').get_data(as_text=True)
    assert 'Viewing History' in page and 'directed by' in page
    r = client.post(f'/read/rate_review/{video}', data={'rating': '4', 'comment': 'Shark!'})
    assert r.headers['Location'].endswith(f'/videos/{video}')


def test_feed_words_video_activity(client, db, people):
    video = add_video(db, people['alice'])
    db.execute("INSERT INTO collections (user_id, book_id, status) VALUES (?, ?, 'watched')",
               (people['alice'], video))
    db.execute("INSERT INTO read_data (user_id, book_id, rating, comment) VALUES (?, ?, 5, 'Great')",
               (people['alice'], video))
    db.commit()
    login(client, 'carol')
    page = client.get('/feed/activity').get_data(as_text=True)
    assert 'added a new movie' in page
    assert 'reviewed a movie' in page
    assert 'watched' in page and 'directed by' in page


# --- videos stay out of book features ----------------------------------------

def test_videos_stay_out_of_the_library(client, db, people):
    add_book(db, people['alice'], 'Dune')
    add_video(db, people['alice'], title='Jaws')
    login(client, 'alice')
    for url in ('/base/index', '/base/shared-library', '/books/search?search_term=a',
                '/base/library/alice'):
        page = client.get(url).get_data(as_text=True)
        assert 'Dune' in page and 'Jaws' not in page, url
    login(client, 'carol')
    page = client.get('/friends/').get_data(as_text=True)
    assert '1 book' in page and '2 books' not in page


def test_book_stats_ignore_videos(app, db, people):
    from utils.stats import type_stats
    alice = people['alice']
    book = add_book(db, alice, 'Dune')
    video = add_video(db, alice)
    for item, status in ((book, 'read'), (video, 'watched')):
        db.execute('INSERT INTO collections (user_id, book_id, status) VALUES (?, ?, ?)', (alice, item, status))
        db.execute('INSERT INTO reading_sessions (user_id, book_id, date_completed) VALUES (?, ?, date())',
                   (alice, item))
    db.execute('INSERT INTO read_data (user_id, book_id, rating) VALUES (?, ?, 2)', (alice, book))
    db.execute('INSERT INTO read_data (user_id, book_id, rating) VALUES (?, ?, 5)', (alice, video))
    db.commit()
    with app.app_context():
        from utils.database import get_db
        conn = get_db()
        stats = type_stats(conn, alice, 'book')
        assert stats['done'] == 1 and stats['done_this_year'] == 1
        assert stats['avg_rating'] == 2
        assert {r['status'] for r in stats['statuses']} == {'read'}
        assert stats['by_month']['total'] == 1
        assert stats['owned'] == 1
        videos = type_stats(conn, alice, 'video')
        assert videos['owned'] == 1 and videos['done'] == 1 and videos['done_this_year'] == 1
        assert videos['avg_rating'] == 5 and videos['size_done'] == 2.1
        assert videos['by_month']['total'] == 1
        assert type_stats(conn, alice, 'record') is None


def test_profile_shows_video_tab_only_with_videos(client, db, people):
    login(client, 'alice')
    assert 'data-stats-kind="video"' not in client.get('/user/alice').get_data(as_text=True)
    add_video(db, people['alice'])
    page = client.get('/user/alice').get_data(as_text=True)
    assert 'data-stats-kind="video"' in page and 'Movies watched per month' not in page   # nothing watched
    assert 'See the movies' in page and 'See the books' in page


def test_book_features_skip_videos(app, db, people):
    """Filter options, the cover fetcher's book lookup (by ISBN), Goodreads
    matching and the book duplicate check all ignore videos. (The fetcher
    has its own lookup for them: tests/test_media_covers.py.)"""
    from flask_login import login_user
    from models import User
    from utils.book_utils import get_filter_options, find_duplicates, missing_cover_sql
    from utils.book_matching import BookIndex
    alice = people['alice']
    db.execute("UPDATE books SET genre = 'x'")
    video = add_video(db, alice, title='Dune')
    db.execute("UPDATE books SET genre = 'Thriller', isbn = ? WHERE id = ?", (ISBN13, video))
    db.commit()
    assert scalar(db, 'SELECT COUNT(*) ' + missing_cover_sql(types=('book',))) == 0
    with app.test_request_context():
        from utils.database import get_db
        conn = get_db()
        login_user(User(alice, 'alice', 'alice@example.test', is_admin=True))
        assert get_filter_options([alice])['genres'] == []
        assert find_duplicates(conn, alice, title='Dune', isbn=ISBN13) == []
        assert BookIndex(conn, alice).match(isbns=[ISBN13], title='Dune', author='x') == (None, None)


def test_export_marks_videos(app, db, people):
    from utils.export import library_csv
    add_book(db, people['alice'], 'Dune')
    add_video(db, people['alice'])
    with app.app_context():
        from utils.database import get_db
        text = library_csv(get_db(), people['alice'])
    lines = text.splitlines()
    assert lines[0].endswith('Type,Format,Barcode,Catalogue Number,Runtime (min)')
    assert any(line.startswith('2,Jaws') and f'video,VHS,{EAN}' in line for line in lines)
    assert any('Dune' in line and line.rstrip().endswith('book,,,,') for line in lines)


def test_account_removal_counts_videos(app, db, people):
    from utils.accounts import removal_context
    dave = add_user(db, 'dave')
    add_video(db, dave)
    with app.app_context():
        from utils.database import get_db
        assert removal_context(get_db(), dave, True)['owned_books'] == 1


# --- lookups (utils/media_lookup.py) -----------------------------------------
# No network in tests: the sources' JSON is faked at media_lookup._get_json,
# and one test checks that _get_json itself goes through the SSRF guard.

from utils import media_lookup


@pytest.mark.parametrize('raw, expected', [
    ('Jaws [VHS]', ('Jaws', None)),
    ('Jaws (1975) VHS Widescreen Edition', ('Jaws', 1975)),
    ('Alien - VHS Tape', ('Alien', None)),
    ("The Abyss (Special Edition) [VHS]", ('The Abyss', None)),
    ('Star Wars: A New Hope (Letterboxed) NTSC', ('Star Wars: A New Hope', None)),
    ('Back to the Future Part II (1989)', ('Back to the Future Part II', 1989)),
    ('My Pal Trigger (Used, PAL) [VHS]', ('My Pal Trigger', None)),
    ('Stereo', ('Stereo', None)),
    # real UPCitemdb title (2026-11-07): keywords after the format bracket
    ('Goodfellas [DVD]  Feature Thriller Drama  Action  Suspense  Drama', ('Goodfellas', None)),
    ('Jaws [VHS] (1975)', ('Jaws', 1975)),
])
def test_clean_title(raw, expected):
    assert media_lookup.clean_title(raw) == expected


UPC_REPLY = {'code': 'OK', 'items': [{'title': 'Jaws (1975) [VHS]', 'brand': 'MCA Home Video',
                                      'description': 'Shark film on tape',
                                      'images': ['https://example.com/sleeve.jpg']}]}
TMDB_SEARCH = {'results': [{'id': 578, 'title': 'Jaws', 'release_date': '1975-06-20',
                            'poster_path': '/jaws.jpg'},
                           {'id': 'junk'}]}
TMDB_MOVIE = {'title': 'Jaws', 'release_date': '1975-06-20', 'runtime': 124,
              'overview': 'A great white shark...', 'genres': [{'name': 'Thriller'}],
              'poster_path': '/jaws.jpg',
              'credits': {'crew': [{'job': 'Producer', 'name': 'Zanuck'},
                                   {'job': 'Director', 'name': 'Steven Spielberg'}]}}


@pytest.fixture
def fake_sources(monkeypatch):
    """Canned replies by URL; records what was asked and which covers were tried."""
    calls, covers = [], []

    def fake_json(url, params=None, headers=None):
        calls.append((url, params or {}, headers))
        if url == media_lookup.UPCITEMDB_URL:
            return UPC_REPLY if params['upc'] == UPC else {'items': []}
        if url.endswith('/search/movie'):
            return TMDB_SEARCH if params['query'] == 'Jaws' else {'results': []}
        if url.endswith('/movie/578'):
            return TMDB_MOVIE
        return None

    def fake_save(urls):
        covers.extend(urls)
        return 'uploads/cover_test.jpg'
    monkeypatch.setattr(media_lookup, '_get_json', fake_json)
    monkeypatch.setattr(media_lookup.book_utils, 'save_best_cover', fake_save)
    media_lookup._cache.clear()
    return calls, covers


def test_lookup_barcode_merges_upc_and_tmdb(app, monkeypatch, fake_sources):
    calls, covers = fake_sources
    monkeypatch.setenv('TMDB_API_KEY', 'k' * 32)
    with app.app_context():
        result = media_lookup.lookup(barcode=EAN)
    assert result['sources'] == ['UPCitemdb', 'TMDb']
    d = result['details']
    assert (d['title'], d['author'], d['publisher'], d['year'], d['runtime_minutes'], d['genre']) == \
        ('Jaws', 'Steven Spielberg', 'MCA Home Video', 1975, 124, 'Thriller')
    assert d['barcode'] == EAN and d['description'] == 'A great white shark...'
    # the tape's own sleeve before the film poster
    assert covers == ['https://example.com/sleeve.jpg', 'https://image.tmdb.org/t/p/w500/jaws.jpg']
    assert result['cover'] == 'uploads/cover_test.jpg'
    assert calls[0][1] == {'upc': UPC}                 # UPC-A sent as 12 digits
    assert calls[1][1]['query'] == 'Jaws' and calls[1][1]['year'] == 1975


def test_lookup_without_tmdb_key_uses_upc_only(app, monkeypatch, fake_sources):
    calls, _ = fake_sources
    monkeypatch.delenv('TMDB_API_KEY', raising=False)
    with app.app_context():
        result = media_lookup.lookup(barcode=EAN)
    assert result['sources'] == ['UPCitemdb']
    assert result['details']['title'] == 'Jaws' and result['details']['publisher'] == 'MCA Home Video'
    assert all('themoviedb' not in url for url, _, _ in calls)


def test_tmdb_token_goes_in_a_header_not_the_url(app, monkeypatch, fake_sources):
    calls, _ = fake_sources
    monkeypatch.setenv('TMDB_API_KEY', 'eyJ' + 'x' * 100)       # a v4 read access token
    with app.app_context():
        media_lookup.lookup(title='Jaws')
    tmdb_calls = [c for c in calls if 'themoviedb' in c[0]]
    assert tmdb_calls and all('api_key' not in params for _, params, _ in tmdb_calls)
    assert all(headers['Authorization'].startswith('Bearer ') for _, _, headers in tmdb_calls)


def test_lookup_miss_is_not_cached(app, monkeypatch, fake_sources):
    calls, _ = fake_sources
    monkeypatch.delenv('TMDB_API_KEY', raising=False)
    with app.app_context():
        assert media_lookup.lookup(barcode=OTHER_EAN)['found'] is False
        media_lookup.lookup(barcode=OTHER_EAN)
        media_lookup.lookup(barcode=EAN)
        media_lookup.lookup(barcode=EAN)
    asked = [p['upc'] for url, p, _ in calls if url == media_lookup.UPCITEMDB_URL]
    assert asked == [OTHER_EAN, OTHER_EAN, UPC]        # the hit was cached, the miss wasn't


def test_lookup_requests_go_through_the_ssrf_guard(app, monkeypatch):
    seen = []

    def fake_get_public(url, headers=None):
        seen.append(url)
        return None
    monkeypatch.setattr(media_lookup.book_utils, '_get_public', fake_get_public)
    with app.app_context():
        assert media_lookup.upcitemdb(UPC) is None
    assert seen and seen[0].startswith(media_lookup.UPCITEMDB_URL)


def test_lookup_route(client, people, monkeypatch, fake_sources):
    monkeypatch.delenv('TMDB_API_KEY', raising=False)
    login(client, 'alice')
    data = client.get(f'/videos/lookup?barcode={UPC}').get_json()
    assert data['success'] and data['found'] and data['details']['title'] == 'Jaws'
    assert client.get('/videos/lookup?barcode=012345678906').status_code == 400
    assert client.get('/videos/lookup').status_code == 400
    assert client.get(f'/videos/lookup?barcode={OTHER_EAN}').get_json()['found'] is False


def test_add_uses_the_looked_up_cover_but_not_arbitrary_paths(client, db, people):
    login(client, 'alice')
    client.post('/videos/add', data=form(existing_cover_url='uploads/cover_x.jpg'))
    assert scalar(db, "SELECT cover_image_url FROM books WHERE title = 'Jaws'") == 'uploads/cover_x.jpg'
    client.post('/videos/add', data=form(title='Evil', barcode='', existing_cover_url='../app.py'))
    assert scalar(db, "SELECT cover_image_url FROM books WHERE title = 'Evil'") is None


# --- the shared add page (Phase 8.5) -----------------------------------------

def test_movie_search_route_lists_films(client, people, monkeypatch, fake_sources):
    login(client, 'alice')
    monkeypatch.delenv('TMDB_API_KEY', raising=False)
    r = client.get('/videos/search?q=Jaws')
    assert r.status_code == 400 and 'TMDb' in r.get_json()['error']
    monkeypatch.setenv('TMDB_API_KEY', 'k' * 32)
    data = client.get('/videos/search?q=Jaws').get_json()
    assert data['results'] == [{'id': 578, 'title': 'Jaws', 'year': 1975,
                                'poster': 'https://image.tmdb.org/t/p/w185/jaws.jpg'}]   # junk row dropped
    assert client.get('/videos/search?q=J').get_json()['results'] == []


def test_lookup_by_picked_tmdb_id(client, people, monkeypatch, fake_sources):
    calls, covers = fake_sources
    monkeypatch.setenv('TMDB_API_KEY', 'k' * 32)
    login(client, 'alice')
    data = client.get('/videos/lookup?tmdb_id=578').get_json()
    assert data['found'] and data['sources'] == ['TMDb']
    assert data['details']['author'] == 'Steven Spielberg' and data['details']['runtime_minutes'] == 124
    assert covers == ['https://image.tmdb.org/t/p/w500/jaws.jpg']
    assert all(url != media_lookup.UPCITEMDB_URL for url, _, _ in calls)   # no barcode, no UPCitemdb


def test_search_thumbnails_allow_tmdb_posters_only():
    from utils.book_utils import THUMBNAIL_HOSTS
    assert 'image.tmdb.org' in THUMBNAIL_HOSTS and 'api.themoviedb.org' not in THUMBNAIL_HOSTS


@pytest.mark.parametrize('url, noun, code_tab', [('/books/add', 'Book', 'ISBN'), ('/videos/add', 'Movie', 'Barcode')])
def test_add_pages_share_one_layout(client, people, url, noun, code_tab):
    login(client, 'alice')
    page = client.get(url).get_data(as_text=True)
    assert f'Add a {noun}</h1>' in page and 'add_item.js' in page
    for method in ('search', 'code', 'scan'):
        assert f'data-method="{method}"' in page
    assert f'>{code_tab}</span>' in page                     # the tab's short label
    # the code box and its Look up button sit in one row
    assert re.search(r'id="code-input".*?</form>', page, re.S).group(0).count('Look up') == 1
    assert 'id="duplicate-notice"' in page and 'id="item-form"' in page


def test_add_movie_without_tmdb_key_opens_the_barcode_tab(client, people, monkeypatch):
    monkeypatch.delenv('TMDB_API_KEY', raising=False)
    login(client, 'alice')
    page = client.get('/videos/add').get_data(as_text=True)
    assert 'data-method="code" data-active="true"' in page and 'needs a free TMDb API key' in page
    monkeypatch.setenv('TMDB_API_KEY', 'k' * 32)
    page = client.get('/videos/add').get_data(as_text=True)
    assert 'data-method="search" data-active="true"' in page and 'id="search-input"' in page


def test_add_book_still_saves(client, db, people):
    login(client, 'alice')
    r = client.post('/books/add', data={'submit_book': '1', 'title': 'Piranesi', 'author': 'Susanna Clarke',
                                        'year': '2020', 'page_count': '272', 'isbn': '9781526622426'})
    assert r.status_code == 302
    assert scalar(db, "SELECT page_count FROM books WHERE title = 'Piranesi'") == 272


def test_movie_duplicate_json_has_format_names(client, db, people):
    add_video(db, people['bob'])
    login(client, 'alice')
    data = client.post('/videos/check_duplicates', json={'barcode': EAN}).get_json()
    assert data['duplicates'][0]['format_label'] == 'Cartridge'


def test_edit_movie_uses_the_shared_fields(client, db, people):
    video = add_video(db, people['alice'], fmt='DVD')
    login(client, 'alice')
    page = client.get(f'/videos/edit/{video}').get_data(as_text=True)
    assert 'Edit Movie</h1>' in page and 'id="runtime_minutes"' in page
    assert '<option value="DVD" selected' in page and 'value="124"' in page


# --- wishlist (Phase 8.6) and Edit Book -----------------------------------------

def test_wishlist_add_page_for_each_type(client, people):
    login(client, 'alice')
    page = client.get('/wishlist/add?type=video&format=DVD').get_data(as_text=True)
    assert 'Add a Movie to your Wishlist</h1>' in page and 'id="notes"' in page
    assert 'action="/wishlist/add"' in page and '<option value="DVD" selected' in page
    assert 'Add to Wishlist' in page and 'class="crumb-link">Wishlist<' in page
    book = client.get('/wishlist/add?type=book').get_data(as_text=True)
    assert 'Add a Book to your Wishlist</h1>' in book and 'id="notes"' in book
    # a movie barcode found on the wishlist's Add Book goes to its Add Movie
    assert 'data-other-add-url="/wishlist/add?type=video"' in book


def test_movie_on_the_wishlist_then_onto_the_shelf(client, db, people):
    alice = people['alice']
    login(client, 'alice')
    r = client.post('/wishlist/add', data=form(media_type='video', title='Alien', barcode=UPC,
                                               format='DVD', notes='the director\'s cut'))
    assert r.status_code == 302 and r.headers['Location'].endswith('/wishlist/view')
    movie = scalar(db, "SELECT id FROM books WHERE title = 'Alien'")
    assert scalar(db, 'SELECT media_type FROM books WHERE id = ?', movie) == 'video'
    assert scalar(db, 'SELECT notes FROM wishlist WHERE book_id = ?', movie) == "the director's cut"
    assert scalar(db, 'SELECT COUNT(*) FROM library_videos WHERE id = ?', movie) == 0   # wished, not owned
    page = client.get('/wishlist/view').get_data(as_text=True)
    assert 'Movies <span' in page and 'Alien' in page and 'Add to Movies' in page
    assert client.get('/videos/').get_data(as_text=True).count('>Alien<') == 0

    r = client.post(f'/wishlist/move_to_library/{movie}')
    assert r.headers['Location'].endswith(f'/videos/{movie}')
    assert scalar(db, 'SELECT COUNT(*) FROM library_videos WHERE id = ?', movie) == 1
    assert scalar(db, 'SELECT status FROM collections WHERE user_id = ? AND book_id = ?', alice, movie) == 'want to watch'


def test_wishlist_refuses_a_movie_you_own(client, db, people):
    mine = add_video(db, people['alice'])
    login(client, 'alice')
    r = client.post('/wishlist/add', data=form(media_type='video'))     # same barcode as `mine`
    assert r.headers['Location'].endswith(f'/videos/{mine}')
    assert scalar(db, 'SELECT COUNT(*) FROM wishlist') == 0


def test_quick_add_and_remove_a_movie(client, db, people):
    video = add_video(db, people['bob'])                # bob's tape, alice wants one
    login(client, 'alice')
    client.post(f'/wishlist/quick_add/{video}')
    assert scalar(db, 'SELECT COUNT(*) FROM wishlist WHERE user_id = ?', people['alice']) == 1
    client.post(f'/wishlist/remove/{video}')
    assert scalar(db, 'SELECT COUNT(*) FROM wishlist') == 0
    assert scalar(db, 'SELECT COUNT(*) FROM books WHERE id = ?', video) == 1   # bob's copy stays


def test_removing_a_watched_wishlist_movie_keeps_it_as_watched_not_owned(client, db, people):
    alice = people['alice']
    login(client, 'alice')
    client.post('/wishlist/add', data=form(media_type='video', title='Heat', barcode=''))
    movie = scalar(db, "SELECT id FROM books WHERE title = 'Heat'")
    db.execute("INSERT INTO collections (user_id, book_id, status) VALUES (?, ?, 'watched')", (alice, movie))
    db.commit()
    client.post(f'/wishlist/remove/{movie}')
    assert scalar(db, 'SELECT owned = 0 AND removed_at IS NULL FROM books WHERE id = ?', movie) == 1   # not owned, not removed (8B.3)
    assert scalar(db, """SELECT COUNT(*) FROM collection_books cb JOIN user_collections uc USING (collection_id)
                         WHERE uc.name = 'Watched but not owned' AND cb.book_id = ?""", movie) == 1


def test_wishlist_isbn_box_sends_a_movie_barcode_to_the_wishlist_movie_form(client, people):
    login(client, 'alice')
    r = client.post('/wishlist/add', data={'isbn_lookup': '1', 'isbn': UPC})
    assert r.status_code == 302 and '/wishlist/add?type=video&barcode=' in r.headers['Location']


def test_edit_book_saves_isbn_and_genre_is_optional(client, db, people):
    book = add_book(db, people['alice'], 'Dune', 'Frank Herbert')
    login(client, 'alice')
    page = client.get(f'/books/edit/{book}').get_data(as_text=True)
    assert 'Edit Book</h1>' in page and 'id="fetch-cover-btn"' in page and 'id="page_count"' in page
    assert not re.search(r'id="genre"[^>]*required', page)
    r = client.post(f'/books/edit/{book}', data={'title': 'Dune', 'author': 'Frank Herbert',
                                                 'isbn': '9780441013593', 'genre': ''})
    assert r.headers['Location'].endswith(f'/books/book/{book}')
    assert scalar(db, 'SELECT isbn FROM books WHERE id = ?', book) == '9780441013593'


def test_edit_book_takes_a_picked_cover_but_not_other_paths(client, db, people):
    book = add_book(db, people['alice'], 'Dune', 'Frank Herbert')
    login(client, 'alice')
    base = {'title': 'Dune', 'author': 'Frank Herbert'}
    client.post(f'/books/edit/{book}', data={**base, 'existing_cover_url': '../library.db'})
    assert scalar(db, 'SELECT cover_image_url FROM books WHERE id = ?', book) is None
    client.post(f'/books/edit/{book}', data={**base, 'existing_cover_url': 'uploads/cover_new.jpg'})
    assert scalar(db, 'SELECT cover_image_url FROM books WHERE id = ?', book) == 'uploads/cover_new.jpg'


def test_wishlist_tabs_show_books_movies_or_both(client, db, people):
    """Books | Movies | Both on top of the wishlist; Both is the default."""
    alice = people['alice']
    book = add_book(db, alice, title='Wished Book')
    movie = add_book(db, alice, title='Wished Movie')
    db.execute("UPDATE books SET media_type = 'video', format = 'VHS' WHERE id = ?", (movie,))
    for book_id in (book, movie):
        db.execute("INSERT INTO wishlist (user_id, book_id) VALUES (?, ?)", (alice, book_id))
    db.commit()
    login(client, 'alice')

    def page(query=''):
        return client.get('/wishlist/view' + query).get_data(as_text=True)

    both = page()
    assert 'Wished Book' in both and 'Wished Movie' in both
    assert re.search(r'href="/wishlist/view\?show=all"\s+class="tab tab-active"', both)
    assert 'Wished Book' in page('?show=both')          # the tab's name before Vinyls
    books = page('?show=books')
    assert 'Wished Book' in books and 'Wished Movie' not in books
    movies = page('?show=movies')
    assert 'Wished Movie' in movies and 'Wished Book' not in movies
    assert 'Wished Movie' in page('?show=nonsense')     # unknown: both


def test_rack_prints_a_label_on_every_case(client, db, people, static_root):
    """The Shelf style's video-store rack shows a printed title on every
    case, so a movie with a poster carries the hidden .rack-print label too
    (a coverless one already has its placeholder); books never get one."""
    (static_root / 'uploads').mkdir()
    for name in ('jaws.jpg', 'dune.jpg'):
        (static_root / 'uploads' / name).write_bytes(b'x')
    vid = add_video(db, people['alice'], title='Jaws')
    db.execute("UPDATE books SET cover_image_url = 'uploads/jaws.jpg' WHERE id = ?", (vid,))
    add_video(db, people['alice'], title='Alien', barcode=None)
    add_book(db, people['alice'], title='Dune', cover='uploads/dune.jpg')
    db.commit()
    login(client, 'alice')
    page = client.get('/videos/').get_data(as_text=True)
    assert page.count('rack-print') == 1
    assert re.search(r'rack-print[^>]*>\s*<span class="no-cover-title">Jaws<', page)
    assert 'rack-print' not in client.get('/base/index').get_data(as_text=True)
