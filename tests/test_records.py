"""Phase 8.7: records (vinyl) as their own section, the Vinyls.

Same rule as for movies (tests/test_videos.py): a record shows in the
Vinyls section with its label, cat. no., format and tracklist, can be
listened to and reviewed, and is shared like a book; no record appears in
the Library, Movies, book stats, the Goodreads matcher or the cover fetcher.
Records have no barcode: Add Vinyl is MusicBrainz title search plus manual
entry (faked here; conftest blocks the network).

people: alice (admin) + bob share a household; carol is alice's friend.
"""
import io
import json

import pytest

from conftest import add_book, login, scalar
from utils import media, music_lookup

MBID = '243fb7b0-e7f3-42e8-bdfc-a66fd9e23d0e'
GROUP = '42d725fb-a8b7-388c-8866-3b02789af326'


def add_record(db, owner_id, title='Blue', artist='Joni Mitchell', label='Reprise',
               catno='MS 2038', fmt='LP', length=36):
    cur = db.execute('''
        INSERT INTO books (title, author, publisher, catalog_number, format, runtime_minutes,
                           description, added_by, media_type)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'record')
    ''', (title, artist, label, catno, fmt, length, 'A1 All I Want (3:32)\nA2 My Old Man (3:33)',
          owner_id))
    db.commit()
    return cur.lastrowid


def form(**overrides):
    data = {'title': 'Blue', 'author': 'Joni Mitchell', 'publisher': 'Reprise', 'year': '1971',
            'runtime_minutes': '36', 'format': 'LP', 'catalog_number': 'MS 2038',
            'genre': 'Folk', 'description': 'A1 All I Want'}
    data.update(overrides)
    return data


# --- the type ----------------------------------------------------------------

def test_record_labels_and_formats():
    m = media.media_labels(media.RECORD)
    assert (m['Noun'], m['creator'], m['publisher'], m['length'], m['section']) == \
        ('Album', 'Artist', 'Label', 'Length', 'Music')
    assert m['statuses'] == ('listened', 'want to listen') and m['has_barcode']   # since 8B.12
    assert [media.format_label(f) for f in media.FORMATS[media.RECORD]] == \
        ['LP', 'EP', '7" single', '10"', '12" single', 'CD', 'Cassette']
    assert media.item_endpoint(media.RECORD, 'edit') == 'records.edit_record'
    assert media.item_endpoint(media.BOOK) == 'books.show_book'


def test_views_keep_the_three_sections_apart(db, people):
    alice = people['alice']
    book = add_book(db, alice, 'Dune')
    record = add_record(db, alice)
    db.execute("INSERT INTO books (title, author, added_by, media_type) VALUES ('Jaws', 'S', ?, 'video')", (alice,))
    db.commit()
    assert [r[0] for r in db.execute('SELECT id FROM library_records')] == [record]
    assert [r[0] for r in db.execute('SELECT id FROM library_books')] == [book]
    assert record not in [r[0] for r in db.execute('SELECT id FROM library_videos')]


# --- add, edit, detail ----------------------------------------------------------

def test_add_vinyl_by_hand(client, db, people):
    login(client, 'alice')
    r = client.post('/records/add', data=form(format='7in', title='Big Yellow Taxi'))
    row = db.execute("SELECT * FROM books WHERE title = 'Big Yellow Taxi'").fetchone()
    assert r.status_code == 302 and r.headers['Location'].endswith(f"/records/{row['id']}")
    assert (row['media_type'], row['format'], row['publisher'], row['catalog_number'],
            row['runtime_minutes'], row['barcode']) == ('record', '7in', 'Reprise', 'MS 2038', 36, None)
    assert row['added_by'] == people['alice']


def test_unknown_format_falls_back_to_lp_and_barcode_is_kept(client, db, people):
    login(client, 'alice')
    client.post('/records/add', data=form(format='VHS', barcode='012345678905'))
    row = db.execute("SELECT format, barcode FROM books WHERE title = 'Blue'").fetchone()
    assert tuple(row) == ('LP', '0012345678905')        # stored as EAN-13, like movies


def test_add_album_page_has_search_barcode_and_scan(client, people):
    login(client, 'alice')
    page = client.get('/records/add').get_data(as_text=True)
    assert 'page-title min-w-0">Add an Album</span>' in page and 'data-type="record"' in page
    assert 'id="search-input"' in page and 'Artist and title...' in page
    # Barcodes since 8B.12: code and scan tabs, the scanner, a barcode field
    assert 'data-method="code"' in page and 'data-method="scan"' in page
    assert 'scanner.js' in page and 'name="barcode"' in page and 'name="isbn"' not in page
    assert 'back of the sleeve' in page
    # The no-JS barcode box is a GET to the add page, like Add Movie's
    assert '<input type="hidden" name="type" value="record">' in page
    assert 'id="catalog_number"' in page and 'Tracklist and notes' in page
    assert '<option value="7in"' in page and '7&#34; single' in page
    assert 'MusicBrainz' in page


def test_duplicates_by_title_and_artist_or_catalogue_number(client, db, people):
    add_record(db, people['bob'])                     # bob shares alice's household
    login(client, 'alice')
    r = client.post('/records/add', data=form(catalog_number=''))
    assert r.status_code == 400 and b'Add it anyway' in r.data
    # Same title by someone else: not a duplicate
    assert client.post('/records/add', data=form(author='Eiffel 65', catalog_number='')).status_code == 302
    # Same cat. no., however it's spaced
    r = client.post('/records/add', data=form(title='Blue (reissue)', catalog_number='ms-2038'))
    assert r.status_code == 400
    assert client.post('/records/add', data=form(confirm_duplicate='1')).status_code == 302
    data = client.post('/records/check_duplicates', json={'title': 'blue', 'author': 'Joni Mitchell'}).get_json()
    assert data['has_duplicates'] and data['duplicates'][0]['url'].startswith('/records/')


def test_strangers_records_are_not_duplicates(client, db, people):
    from conftest import add_user
    dave = add_user(db, 'dave')
    add_record(db, dave)
    login(client, 'alice')
    assert client.post('/records/check_duplicates', json={'title': 'Blue'}).get_json()['duplicates'] == []


def test_edit_vinyl(client, db, people):
    record = add_record(db, people['alice'])
    login(client, 'alice')
    page = client.get(f'/records/edit/{record}').get_data(as_text=True)
    assert 'Edit Album' in page and 'value="MS 2038"' in page
    r = client.post(f'/records/edit/{record}', data=form(format='12in', publisher='Asylum'))
    assert r.headers['Location'].endswith(f'/records/{record}')
    assert tuple(db.execute('SELECT format, publisher FROM books WHERE id = ?', (record,)).fetchone()) == \
        ('12in', 'Asylum')
    login(client, 'carol')
    assert client.get(f'/records/edit/{record}').status_code == 404


def test_detail_page_shows_record_fields(client, db, people):
    record = add_record(db, people['alice'])
    login(client, 'alice')
    page = client.get(f'/records/{record}').get_data(as_text=True)
    for text in ('Label', 'Reprise', 'Cat. No.', 'MS 2038', 'Length', 'class="crumb-link">Music<',
                 'About this Album', 'whitespace-pre-line', 'Listen Status'):
        assert text in page, text
    assert 'Purchase this book' not in page
    assert f'/records/edit/{record}' in page


def test_other_urls_redirect_to_the_record_page(client, db, people):
    record = add_record(db, people['alice'])
    login(client, 'alice')
    for url in (f'/books/book/{record}', f'/videos/{record}'):
        r = client.get(url)
        assert r.status_code == 302 and r.headers['Location'].endswith(f'/records/{record}'), url
    assert client.get(f'/books/edit/{record}').headers['Location'].endswith(f'/records/edit/{record}')


def test_grid_tabs_and_search(client, db, people):
    add_record(db, people['alice'])
    add_record(db, people['alice'], title='Hejira', catno='7E-1087', fmt='12in')
    login(client, 'alice')
    page = client.get('/records/').get_data(as_text=True)
    assert 'My Music' in page and 'Blue' in page and 'Hejira' in page
    assert '12&#34; single' in page            # the format badge
    page = client.get('/records/?search_term=7E-1087').get_data(as_text=True)
    assert 'Hejira' in page and '>Blue<' not in page
    page = client.get('/records/?format=LP').get_data(as_text=True)
    assert 'Blue' in page and 'Hejira' not in page
    # The + button: Album and Wishlist
    assert 'href="/records/add"' in page and 'href="/wishlist/add?type=record"' in page


def test_format_badges_use_icons_for_lp_cd_and_cassette(client, db, people):
    # LP, CD and Cassette get a Lucide icon (turntable, disc-2, cassette-tape)
    # beside the title on the album's page, named for screen readers. The
    # grid shows no format badge (Phil, 2026-11-11).
    ids = {name: add_record(db, people['alice'], title=title, catno=catno, fmt=name)
           for name, title, catno in (('LP', 'Blue', 'MS 2038'), ('CD', 'Court and Spark', '7E-1001'),
                                      ('Cassette', 'Hissing', '7E-1051'))}
    login(client, 'alice')
    assert 'M18 8v4a8 8 0 0 1-1.07 4' not in client.get('/records/').get_data(as_text=True)
    for name, path in (('LP', 'M18 8v4a8 8 0 0 1-1.07 4'),          # turntable
                       ('CD', '<circle cx="12" cy="12" r="4"/>'),   # disc-2
                       ('Cassette', 'M8 12h8')):                    # cassette-tape
        page = client.get(f'/records/{ids[name]}').get_data(as_text=True)
        assert path in page and f'aria-label="{name}"' in page


def test_household_and_friends_see_records(client, db, people):
    add_record(db, people['alice'])
    login(client, 'bob')
    assert 'Blue' in client.get('/records/shared').get_data(as_text=True)
    login(client, 'carol')
    friends = client.get('/friends/').get_data(as_text=True)   # the Friends page (11.3)
    assert 'alice' in friends and '1 album' in friends
    assert 'Blue' in client.get('/records/user/alice').get_data(as_text=True)


def test_strangers_see_no_records(client, db, people):
    from conftest import add_user
    record = add_record(db, people['alice'])
    add_user(db, 'dave')
    login(client, 'dave')
    assert client.get(f'/records/{record}').status_code == 404
    assert client.get('/records/user/alice').status_code == 404


# --- statuses, reviews, feed, stats ------------------------------------------------

def test_listen_statuses(client, db, people):
    record = add_record(db, people['alice'])
    login(client, 'alice')
    client.post('/collections/collections/status/add', data={'id': record, 'status': 'watched'},
                headers={'Referer': '/records/'})
    assert scalar(db, 'SELECT COUNT(*) FROM collections') == 0
    r = client.post('/collections/collections/status/add', data={'id': record, 'status': 'listened'})
    assert r.status_code == 302 and f'/read/rate_review/{record}' in r.headers['Location']
    assert scalar(db, 'SELECT status FROM collections WHERE book_id = ?', record) == 'listened'


def test_review_returns_to_the_record(client, db, people):
    record = add_record(db, people['alice'])
    login(client, 'alice')
    page = client.get(f'/read/rate_review/{record}').get_data(as_text=True)
    assert 'Listening History' in page and 'No listens yet' in page
    r = client.post(f'/read/rate_review/{record}', data={'rating': '5', 'comment': 'River'})
    assert r.headers['Location'].endswith(f'/records/{record}')


def test_feed_words_record_activity(client, db, people):
    record = add_record(db, people['alice'])
    db.execute("INSERT INTO collections (user_id, book_id, status) VALUES (?, ?, 'listened')",
               (people['alice'], record))
    db.execute("INSERT INTO read_data (user_id, book_id, rating, comment) VALUES (?, ?, 5, 'Great')",
               (people['alice'], record))
    db.commit()
    login(client, 'carol')
    page = client.get('/feed/activity').get_data(as_text=True)
    assert 'added a new album' in page and 'reviewed an album' in page and 'listened to' in page


def test_record_stats_on_the_profile(client, app, db, people):
    from utils.stats import type_stats
    alice = people['alice']
    login(client, 'alice')
    assert 'data-stats-kind="record"' not in client.get('/user/alice').get_data(as_text=True)
    record = add_record(db, alice)
    add_book(db, alice, 'Dune')
    db.execute("INSERT INTO collections (user_id, book_id, status) VALUES (?, ?, 'listened')", (alice, record))
    db.commit()
    page = client.get('/user/alice').get_data(as_text=True)
    assert 'data-stats-kind="record"' in page and 'data-stats-kind="video"' not in page
    assert 'Albums owned' in page and 'Hours listened to' in page
    with app.app_context():
        from utils.database import get_db
        conn = get_db()
        stats = type_stats(conn, alice, media.RECORD)
        assert (stats['owned'], stats['done'], stats['size_done']) == (1, 1, 0.6)
        assert stats['by_format'] == [{'format': 'LP', 'count': 1}]
        assert type_stats(conn, alice, media.VIDEO) is None
        assert type_stats(conn, alice, media.BOOK)['owned'] == 1


# --- records stay out of the other sections ------------------------------------------

def test_records_stay_out_of_the_library_and_movies(client, db, people):
    add_book(db, people['alice'], 'Dune')
    add_record(db, people['alice'], title='Hejira')
    login(client, 'alice')
    for url in ('/base/index', '/base/shared-library', '/books/search?search_term=e',
                '/base/library/alice', '/videos/', '/videos/shared'):
        assert 'Hejira' not in client.get(url).get_data(as_text=True), url
    login(client, 'carol')
    assert '1 book' in client.get('/friends/').get_data(as_text=True)
    assert 'Hejira' not in client.get('/videos/user/alice').get_data(as_text=True)


def test_book_features_skip_records(app, db, people):
    """Filter options, the cover fetcher's book lookup (by ISBN), Goodreads
    matching and the book duplicate check all ignore records. (The fetcher
    has its own lookup for them: tests/test_media_covers.py.)"""
    from flask_login import login_user
    from models import User
    from utils.book_utils import get_filter_options, find_duplicates, missing_cover_sql
    from utils.book_matching import BookIndex
    alice = people['alice']
    record = add_record(db, alice, title='Dune')
    db.execute("UPDATE books SET genre = 'Folk', isbn = '9780306406157' WHERE id = ?", (record,))
    db.commit()
    assert scalar(db, 'SELECT COUNT(*) ' + missing_cover_sql(types=('book',))) == 0
    with app.test_request_context():
        from utils.database import get_db
        conn = get_db()
        login_user(User(alice, 'alice', 'alice@example.test', is_admin=True))
        assert get_filter_options([alice])['genres'] == []
        assert get_filter_options([alice], media.VIDEO)['genres'] == []
        assert get_filter_options([alice], media.RECORD)['genres'] == ['Folk']
        assert get_filter_options([alice], media.RECORD)['formats'] == ['LP']
        assert find_duplicates(conn, alice, title='Dune', isbn='9780306406157') == []
        assert BookIndex(conn, alice).match(isbns=['9780306406157'], title='Dune', author='x') == (None, None)


def test_account_removal_counts_records(app, db, people):
    from conftest import add_user
    from utils.accounts import removal_context
    dave = add_user(db, 'dave')
    add_record(db, dave)
    with app.app_context():
        from utils.database import get_db
        assert removal_context(get_db(), dave, True)['owned_books'] == 1


def test_sidebar_has_vinyls(client, people):
    login(client, 'alice')
    page = client.get('/base/index').get_data(as_text=True)
    assert 'href="/records/"' in page and 'Music' in page


# --- wishlist ------------------------------------------------------------------

def test_vinyl_on_the_wishlist_then_onto_the_shelf(client, db, people):
    login(client, 'alice')
    page = client.get('/wishlist/add?type=record').get_data(as_text=True)
    assert 'page-title min-w-0">Add an Album to your Wishlist</span>' in page and 'id="notes"' in page
    r = client.post('/wishlist/add', data=form(media_type='record', notes='first pressing'))
    assert r.headers['Location'].endswith('/wishlist/view')
    record = scalar(db, "SELECT id FROM books WHERE title = 'Blue'")
    assert scalar(db, 'SELECT media_type FROM books WHERE id = ?', record) == 'record'
    assert scalar(db, 'SELECT COUNT(*) FROM library_records WHERE id = ?', record) == 0   # wished
    page = client.get('/wishlist/view').get_data(as_text=True)
    assert 'Music' in page and 'Add to Music' in page and 'first pressing' in page
    # The item's own link, not the word: "Blue" is also an accent in the sidebar
    assert f'/records/{record}' in client.get('/wishlist/view?show=music').get_data(as_text=True)
    assert f'/records/{record}' not in client.get('/wishlist/view?show=movies').get_data(as_text=True)
    r = client.post(f'/wishlist/move_to_library/{record}')
    assert r.headers['Location'].endswith(f'/records/{record}')
    assert scalar(db, 'SELECT status FROM collections WHERE book_id = ?', record) == 'want to listen'
    assert scalar(db, 'SELECT COUNT(*) FROM library_records WHERE id = ?', record) == 1


def test_removing_a_listened_wishlist_record_keeps_it(client, db, people):
    alice = people['alice']
    record = add_record(db, alice)
    db.execute('INSERT INTO wishlist (user_id, book_id) VALUES (?, ?)', (alice, record))
    db.execute("INSERT INTO collections (user_id, book_id, status) VALUES (?, ?, 'listened')", (alice, record))
    db.commit()
    login(client, 'alice')
    client.post(f'/wishlist/remove/{record}')
    assert scalar(db, 'SELECT owned = 0 AND removed_at IS NULL FROM books WHERE id = ?', record) == 1   # unshelved, not removed (8B.3)
    assert scalar(db, """SELECT COUNT(*) FROM collection_books cb JOIN user_collections uc USING (collection_id)
                         WHERE uc.name = 'Listened to, unshelved' AND cb.book_id = ?""", record) == 1


# --- MusicBrainz -----------------------------------------------------------------

def test_build_query_needs_every_word_and_a_physical_format():
    q = music_lookup.build_query('joni  mitchell blue')
    assert q.startswith('(release:joni OR artist:joni) AND (release:mitchell OR artist:mitchell) AND ')
    # No choice: vinyl, CD and cassette, never digital
    assert 'format:("Vinyl" OR "12\\" Vinyl" OR "10\\" Vinyl" OR "7\\" Vinyl" OR "CD" OR ' in q
    assert '"Cassette")' in q and 'Digital' not in q
    assert music_lookup.build_query('blue', 'vinyl').endswith(
        'format:("Vinyl" OR "12\\" Vinyl" OR "10\\" Vinyl" OR "7\\" Vinyl")')
    assert music_lookup.build_query('blue', 'cassette').endswith('format:("Cassette")')
    cd = music_lookup.build_query('blue', 'cd')
    assert '"CD"' in cd and '"Enhanced CD"' in cd and 'Vinyl' not in cd
    # Lucene syntax in what was typed is escaped, not obeyed
    assert '(release:AC\\/DC OR artist:AC\\/DC)' in music_lookup.build_query('AC/DC')
    assert 'release:a\\:b' in music_lookup.build_query('a:b')


@pytest.mark.parametrize('formats, kind, expected', [
    (['12" Vinyl'], 'Album', 'LP'),
    (['12" Vinyl', '12" Vinyl'], 'Album', 'LP'),
    (['Vinyl'], 'Album', 'LP'),
    (['7" Vinyl'], 'Single', '7in'),
    (['Vinyl'], 'Single', '7in'),
    (['12" Vinyl'], 'Single', '12in'),
    (['10" Vinyl'], 'Album', '10in'),
    (['12" Vinyl'], 'EP', 'EP'),
    (['7" Vinyl'], 'EP', 'EP'),
    (['CD'], 'Album', 'CD'),
    (['CD', 'CD'], 'Album', 'CD'),
    (['Enhanced CD'], 'Single', 'CD'),
    (['CD'], 'EP', 'CD'),                   # an EP on CD is a CD: the format is the object
    (['Cassette'], 'Album', 'Cassette'),
    (['Hybrid SACD (CD layer)', 'Hybrid SACD (SACD layer, 2 channels)'], 'Album', 'CD'),
    (['12" Vinyl', 'CD'], 'Album', 'LP'),   # a bonus CD doesn't make the set a CD
])
def test_album_format(formats, kind, expected):
    release = {'media': [{'format': f} for f in formats], 'release-group': {'primary-type': kind}}
    assert music_lookup.album_format(release) == expected


RELEASE = {
    'id': MBID, 'title': 'Blue', 'date': '1971-06-22', 'country': 'US', 'disambiguation': '',
    'artist-credit': [{'name': 'Joni Mitchell', 'joinphrase': ''}],
    'label-info': [{'label': {'name': 'Reprise Records'}, 'catalog-number': 'MS 2038'}],
    'release-group': {'id': GROUP, 'primary-type': 'Album', 'first-release-date': '1971-06-22',
                      'genres': [{'name': 'folk', 'count': 5}, {'name': 'pop', 'count': 1}]},
    'media': [{'format': '12" Vinyl', 'tracks': [
        {'number': 'A1', 'title': 'All I Want', 'length': 212000},
        {'number': 'A2', 'title': 'My Old Man', 'length': 213000},
        {'number': 'B1', 'title': 'River', 'length': 243000},
    ]}],
}
SEARCH = {'count': 1, 'releases': [{
    'id': MBID, 'score': 100, 'title': 'Blue', 'date': '1971-06-22', 'country': 'US',
    'artist-credit': [{'name': 'Joni Mitchell'}],
    'label-info': [{'label': {'name': 'Reprise Records'}, 'catalog-number': 'MS 2038'}],
    'release-group': {'id': GROUP, 'primary-type': 'Album'},
    'media': [{'format': '12" Vinyl'}],
}, {'title': 'no id: dropped'}]}


class FakeResponse:
    def __init__(self, status, body=b''):
        self.status_code = status
        self.raw = io.BytesIO(body)
        self.raw.read = (lambda f: lambda n, decode_content=True: f(n))(self.raw.read)

    def close(self):
        pass


@pytest.fixture
def fake_mb(monkeypatch):
    """MusicBrainz answers by URL; records each request and its headers."""
    calls, covers = [], []
    replies = {'status': 200}

    def fake_get_public(url, headers=None):
        calls.append((url, headers))
        if replies['status'] != 200:
            return FakeResponse(replies['status'])
        if '/release/?' in url:
            return FakeResponse(200, json.dumps(SEARCH).encode())
        if f'/release/{MBID}?' in url:
            return FakeResponse(200, json.dumps(RELEASE).encode())
        return FakeResponse(404)

    def fake_save(urls):
        covers.extend(urls)
        return 'uploads/cover_vinyl.jpg'
    monkeypatch.setattr(music_lookup.book_utils, '_get_public', fake_get_public)
    monkeypatch.setattr(music_lookup.book_utils, 'save_best_cover', fake_save)
    monkeypatch.setattr(music_lookup, 'MIN_INTERVAL', 0)
    music_lookup._cache.clear()
    return calls, covers, replies


def test_search_route_lists_pressings(client, people, fake_mb):
    calls, _, _ = fake_mb
    login(client, 'alice')
    data = client.get('/records/search?q=joni blue').get_json()
    assert data['results'] == [{
        'id': MBID, 'title': 'Blue', 'artist': 'Joni Mitchell', 'year': 1971, 'country': 'US',
        'label': 'Reprise Records', 'catalog_number': 'MS 2038', 'format': 'LP', 'format_label': 'LP',
        'thumb': f'https://coverartarchive.org/release-group/{GROUP}/front-250',
        'source': 'musicbrainz',
    }]
    assert data['source'] == 'musicbrainz'      # no DISCOGS_TOKEN in tests
    url, headers = calls[0]
    assert url.startswith('https://musicbrainz.org/ws/2/release/?') and 'fmt=json' in url
    assert headers['User-Agent'].startswith('Libaraxia/1.0 ( ') and headers['User-Agent'].endswith(' )')
    # Cached: the same search doesn't ask again
    client.get('/records/search?q=joni blue')
    assert len(calls) == 1
    assert client.get('/records/search?q=j').get_json()['results'] == []


def test_search_route_narrows_by_format(client, people, fake_mb):
    from urllib.parse import parse_qs, urlsplit
    calls, _, _ = fake_mb
    login(client, 'alice')
    client.get('/records/search?q=joni blue&format=cassette')
    client.get('/records/search?q=joni blue&format=CD')
    client.get('/records/search?q=joni blue&format=8track')    # unknown: all formats
    queries = [parse_qs(urlsplit(url).query)['query'][0] for url, _ in calls]
    assert queries[0].endswith('format:("Cassette")')
    assert '"CD"' in queries[1] and 'Vinyl' not in queries[1]
    assert 'Vinyl' in queries[2] and '"CD"' in queries[2] and 'Cassette' in queries[2]
    # Each format is its own cache entry
    assert len(calls) == 3


def test_lookup_route_fills_the_form(client, people, fake_mb):
    _, covers, _ = fake_mb
    login(client, 'alice')
    data = client.get(f'/records/lookup?mbid={MBID}').get_json()
    assert data['success'] and data['found'] and data['cover'] == 'uploads/cover_vinyl.jpg'
    assert data['sources'] == ['MusicBrainz', 'Cover Art Archive']
    d = data['details']
    assert (d['title'], d['author'], d['publisher'], d['catalog_number'], d['year'], d['format'],
            d['runtime_minutes'], d['genre']) == \
        ('Blue', 'Joni Mitchell', 'Reprise Records', 'MS 2038', 1971, 'LP', 11, 'Folk')
    assert d['description'] == ('A1 All I Want (3:32)\nA2 My Old Man (3:33)\nB1 River (4:03)'
                                '\n\nPressing: US 1971')
    assert covers == [f'https://coverartarchive.org/release/{MBID}/front-500',
                      f'https://coverartarchive.org/release-group/{GROUP}/front-500']


def test_lookup_route_refuses_anything_but_an_mbid(client, people, fake_mb):
    calls, _, _ = fake_mb
    login(client, 'alice')
    for bad in ('', 'abc', f'{MBID}/../x', '../../admin'):
        assert client.get('/records/lookup', query_string={'mbid': bad}).status_code == 400
    assert calls == []


def test_musicbrainz_busy_says_try_again(client, people, fake_mb):
    _, _, replies = fake_mb
    replies['status'] = 503
    login(client, 'alice')
    r = client.get('/records/search?q=joni blue')
    assert r.status_code == 503 and 'busy' in r.get_json()['error']
    assert client.get(f'/records/lookup?mbid={MBID}').status_code == 503


def test_unknown_release_is_not_found(client, people, fake_mb):
    login(client, 'alice')
    data = client.get('/records/lookup?mbid=00000000-0000-0000-0000-000000000000').get_json()
    assert data['success'] and not data['found']


def test_requests_wait_their_turn(app, monkeypatch):
    """One request a second per process (MusicBrainz's limit)."""
    slept = []
    monkeypatch.setattr(music_lookup.time, 'sleep', slept.append)
    monkeypatch.setattr(music_lookup, '_last_request', music_lookup.time.monotonic())
    music_lookup._throttle()
    assert slept and 0 < slept[0] <= music_lookup.MIN_INTERVAL


def test_search_thumbnails_allow_cover_art_archive():
    from utils.book_utils import THUMBNAIL_HOSTS
    assert 'coverartarchive.org' in THUMBNAIL_HOSTS and 'musicbrainz.org' not in THUMBNAIL_HOSTS


def test_session_form_titles_are_worded_per_type(client, db, people):
    """The session form's heading is set by JS on open; its wording comes
    from the template (data-add-title), so a vinyl says Listening Session."""
    record = add_record(db, people['alice'])
    login(client, 'alice')
    for url in (f'/records/{record}', f'/read/rate_review/{record}'):
        page = client.get(url).get_data(as_text=True)
        assert 'data-add-title="Add New Listening Session"' in page, url
        assert 'data-edit-title="Edit Listening Session"' in page, url
        assert 'New Reading Session' not in page, url


def test_data_export_has_type_and_format(app, db, people):
    """Every file of the ZIP says which section a row is from (8B.4)."""
    import csv
    import zipfile
    from utils.export import data_zip
    alice = people['alice']
    rid = add_record(db, alice)
    db.execute("INSERT INTO read_data (user_id, book_id, rating, comment) VALUES (?, ?, 5, 'great')",
               (alice, rid))
    db.execute("INSERT INTO reading_sessions (user_id, book_id, date_started) VALUES (?, ?, '2026-01-01')",
               (alice, rid))
    db.commit()
    with app.app_context():
        from utils.database import get_db
        z = zipfile.ZipFile(io.BytesIO(data_zip(get_db(), alice)))
    for name in ('reviews.csv', 'reading_sessions.csv'):
        rows = list(csv.reader(io.StringIO(z.read(name).decode())))
        assert rows[0][-2:] == ['Type', 'Format'], name
        assert rows[1][-2:] == ['record', 'LP'], name
    for name in ('collections.csv', 'wishlist.csv'):
        header = next(csv.reader(io.StringIO(z.read(name).decode())))
        assert header[-2:] == ['Type', 'Format'], name


def test_vinyl_sizes_have_no_icon_and_a_centred_title(client, db, people):
    """An EP or 7" has no format icon, so its page keeps the centred title."""
    rid = add_record(db, people['alice'], title='Small', fmt='7in')
    login(client, 'alice')
    page = client.get(f'/records/{rid}').get_data(as_text=True)
    assert '<header class="py-2 px-3 md:px-6 text-center">' in page and 'role="img"' not in page
