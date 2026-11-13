"""16.0 (Phil, 2026-11-13): the Add pages' Search tab. "The silver cord by
King Gizzard" came back as pressings of other albums, and "king gizzard" as
twelve pressings of one. Now: music lists albums, then an album's pressings;
"X by Y" asks for title X by Y; every type has "Show more" (each answer's
`next` is the parameters for the following page).

No network: the sources' JSON is faked at book_utils._get_public (music),
or at the module's own request helper (books, TMDb)."""
import json
from urllib.parse import parse_qs, urlsplit

import pytest

from conftest import login
from test_records import FakeResponse
from utils import book_utils, discogs_lookup, media_lookup, music_lookup
from utils.search import by_or_plain, next_page, split_by

GROUP = '70cbf290-4584-4a31-a459-409fa9c8610a'


# --- the pieces ---------------------------------------------------------------

@pytest.mark.parametrize('text, expected', [
    ('the silver cord by King Gizzard', ('the silver cord', 'King Gizzard')),
    ('Stand by Me by Ben E. King', ('Stand by Me', 'Ben E. King')),     # the last " by "
    ('Stand by Me', ('Stand', 'Me')),                                   # wrong, so by_or_plain falls back
    ('by the way', None), ('dune', None), ('', None),
])
def test_split_by(text, expected):
    assert split_by(text) == expected


def test_by_or_plain_falls_back_and_remembers():
    asked = []

    def run(split, page):
        asked.append(split)
        return (['hit'] if split is None or split[0] == 'Dune' else []), True

    assert by_or_plain('Dune by Herbert', run) == (['hit'], True, True)
    asked.clear()
    assert by_or_plain('Stand by Me', run) == (['hit'], True, False)
    assert asked == [('Stand', 'Me'), None]                  # tried the split, then as typed
    asked.clear()
    by_or_plain('Stand by Me', run, page=2, by=False)       # page 2 stays on the plain reading
    assert asked == [None]


def test_fits_folds_and_skips_joining_words():
    from utils.search import fits
    split = ('the silver cord', 'King Gizzard and the Lizard Wizard')
    assert fits(split, 'The Silver Cord', 'King Gizzard & The Lizard Wizard')
    assert not fits(split, 'Silver Linings', 'King Gizzard & The Lizard Wizard')
    assert fits(('les miserables', 'hugo'), 'Les Misérables', 'Victor Hugo')


def test_next_page():
    assert next_page(1, True, by=True, src=None) == {'page': 2, 'by': 1}
    assert next_page(1, False) is None
    assert next_page(20, True) is None                       # MAX_PAGE


# --- Discogs: albums, pressings, "Use this" -----------------------------------------

MASTERS = {'results': [
    {'id': 992310, 'type': 'master', 'title': 'King Gizzard And The Lizard Wizard - Nonagon Infinity',
     'year': '2016', 'thumb': 'https://i.discogs.com/n.jpg'},
    {'id': 3306460, 'type': 'master', 'title': 'King Gizzard And The Lizard Wizard - The Silver Cord',
     'year': '2023', 'thumb': ''},
], 'pagination': {'page': 1, 'pages': 17}}

VERSIONS = {'versions': [
    {'id': 8479035, 'title': 'Nonagon Infinity', 'major_formats': ['Vinyl'], 'format': 'LP, Album, Ltd',
     'label': 'Flightless', 'catno': 'FLT-025 ', 'country': 'Australia', 'released': '2016', 'thumb': 't.jpg'},
    {'id': 8489238, 'title': 'Nonagon Infinity', 'major_formats': ['CD'], 'format': 'Album',
     'label': 'Heavenly', 'catno': 'HVNLP127CD', 'country': 'UK', 'released': '2016-04-29'},
    {'id': 1, 'title': 'Nonagon Infinity', 'major_formats': ['File'], 'format': 'MP3'},      # digital
], 'pagination': {'page': 1, 'pages': 1}}

RELEASES = {'results': [
    {'id': 555, 'title': 'Someone - Rare Single', 'year': '1999', 'format': ['Vinyl', '7"', 'Single'],
     'label': ['Tiny'], 'catno': 'T1'},
], 'pagination': {'page': 1, 'pages': 3}}


@pytest.fixture
def discogs(monkeypatch):
    """Discogs answers by URL; `masters` is what a master search finds."""
    monkeypatch.setenv('DISCOGS_TOKEN', 'test-token')
    calls = []
    state = {'masters': MASTERS, 'status': 200}

    def fake(url, headers=None):
        calls.append(url)
        if state['status'] != 200:
            return FakeResponse(state['status'])
        q = parse_qs(urlsplit(url).query)
        path = urlsplit(url).path
        if path == '/database/search':
            body = state['masters'] if q['type'] == ['master'] else RELEASES
        elif path == '/masters/992310/versions':
            body = VERSIONS
        elif path == '/masters/992310':
            body = {'id': 992310, 'main_release': 8479035}
        else:
            return FakeResponse(404)
        return FakeResponse(200, json.dumps(body).encode())
    monkeypatch.setattr(book_utils, '_get_public', fake)
    monkeypatch.setattr(discogs_lookup, 'MIN_INTERVAL', 0)
    discogs_lookup._cache.clear()
    return calls, state


def test_albums_one_row_each(client, people, discogs):
    calls, _ = discogs
    login(client, 'alice')
    data = client.get('/records/albums?q=king gizzard&format=vinyl').get_json()
    assert data['source'] == 'discogs'
    assert [(r['title'], r['artist'], r['year'], r['level']) for r in data['results']] == [
        ('Nonagon Infinity', 'King Gizzard And The Lizard Wizard', 2016, 'album'),
        ('The Silver Cord', 'King Gizzard And The Lizard Wizard', 2023, 'album')]
    q = parse_qs(urlsplit(calls[0]).query)
    assert q['type'] == ['master'] and q['q'] == ['king gizzard'] and q['format'] == ['Vinyl']
    assert data['next'] == {'page': 2, 'by': 0}

    # Show more: the next page of the same search
    client.get('/records/albums?q=king gizzard&format=vinyl&page=2&by=0')
    assert parse_qs(urlsplit(calls[-1]).query)['page'] == ['2']


def test_album_by_artist_asks_for_exactly_that(client, people, discogs):
    calls, state = discogs
    login(client, 'alice')
    data = client.get('/records/albums?q=the silver cord by King Gizzard').get_json()
    q = parse_qs(urlsplit(calls[0]).query)
    assert q['release_title'] == ['the silver cord'] and q['artist'] == ['King Gizzard'] and 'q' not in q
    assert data['next']['by'] == 1

    # "Stand by Me" as title "Stand" by "Me": Discogs matches loosely and
    # finds something, but nothing whose title has "stand" and artist "me",
    # so it's asked again as typed
    calls.clear()
    discogs_lookup._cache.clear()
    data = client.get('/records/albums?q=Stand by Me').get_json()
    assert 'release_title' in calls[0] and parse_qs(urlsplit(calls[1]).query)['q'] == ['Stand by Me']
    assert data['next']['by'] == 0


def test_no_album_lists_pressings(client, people, discogs):
    """A release with no Discogs master: the first page lists pressings, and
    Show more stays on them."""
    calls, state = discogs
    state['masters'] = {'results': [], 'pagination': {'page': 1, 'pages': 1}}
    login(client, 'alice')
    data = client.get('/records/albums?q=rare single').get_json()
    assert [r['id'] for r in data['results']] == [555] and 'level' not in data['results'][0]
    assert data['next'] == {'page': 2, 'level': 'pressing'}
    calls.clear()
    client.get('/records/albums?q=rare single&page=2&level=pressing')
    assert parse_qs(urlsplit(calls[0]).query)['type'] == ['release']


def test_pressings_of_an_album(client, people, discogs):
    calls, _ = discogs
    login(client, 'alice')
    data = client.get('/records/pressings?source=discogs&id=992310&format=cd').get_json()
    rows = data['results']
    assert [(r['id'], r['format'], r['label'], r['catalog_number'], r['year']) for r in rows] == [
        (8479035, 'LP', 'Flightless', 'FLT-025', 2016), (8489238, 'CD', 'Heavenly', 'HVNLP127CD', 2016)]
    assert parse_qs(urlsplit(calls[0]).query)['format'] == ['CD']
    assert data['next'] is None
    for bad in ('source=discogs&id=abc', 'source=discogs&id=1;2', 'source=musicbrainz&id=../x', 'id=1'):
        assert client.get(f'/records/pressings?{bad}').status_code == 400


def test_use_this_on_an_album_fills_from_its_main_pressing(client, people, discogs, monkeypatch):
    looked_up = []
    monkeypatch.setattr(discogs_lookup, 'lookup', lambda rid: looked_up.append(rid) or
                        {'found': True, 'details': {'title': 'Nonagon Infinity'}, 'sources': ['Discogs'], 'cover': None})
    login(client, 'alice')
    data = client.get('/records/lookup?discogs_master=992310').get_json()
    assert data['found'] and looked_up == [8479035]
    assert client.get('/records/lookup?discogs_master=12x').status_code == 400


def test_busy_discogs_on_a_later_page_says_so(client, people, discogs):
    """Page 2 never switches to MusicBrainz's list halfway down."""
    _, state = discogs
    state['status'] = 429
    login(client, 'alice')
    r = client.get('/records/albums?q=king gizzard&page=2&by=0')
    assert r.status_code == 503 and 'busy' in r.get_json()['error']


# --- MusicBrainz: the same, when Discogs is off or busy ------------------------------

def test_musicbrainz_album_query_drops_joining_words():
    assert music_lookup.album_query('x', ('the silver cord', 'King Gizzard & the Lizard Wizard')) == (
        'releasegroup:the AND releasegroup:silver AND releasegroup:cord'
        ' AND artist:King AND artist:Gizzard AND artist:the AND artist:Lizard AND artist:Wizard')
    assert music_lookup.album_query('gizzard and lizard') == \
        '(releasegroup:gizzard OR artist:gizzard) AND (releasegroup:lizard OR artist:lizard)'


@pytest.fixture
def mb(monkeypatch):
    monkeypatch.setenv('DISCOGS_TOKEN', '')
    calls = []

    def fake(url, headers=None):
        calls.append(url)
        path = urlsplit(url).path
        if path == '/ws/2/release-group/':
            body = {'count': 30, 'release-groups': [
                {'id': GROUP, 'title': 'The Silver Cord', 'first-release-date': '2023-10-27',
                 'artist-credit': [{'name': 'King Gizzard & the Lizard Wizard'}]}]}
        elif path == '/ws/2/release':
            body = {'release-count': 3, 'releases': [
                {'id': 'b' * 8 + '-0000-0000-0000-' + 'b' * 12, 'title': 'The Silver Cord', 'date': '2024',
                 'media': [{'format': '12" Vinyl'}], 'label-info': [{'label': {'name': 'KGLW'}, 'catalog-number': 'K2'}]},
                {'id': 'a' * 8 + '-0000-0000-0000-' + 'a' * 12, 'title': 'The Silver Cord', 'date': '2023-10-27',
                 'media': [{'format': '12" Vinyl'}], 'label-info': [{'label': {'name': 'KGLW'}, 'catalog-number': 'K1'}]},
                {'id': 'c' * 8 + '-0000-0000-0000-' + 'c' * 12, 'title': 'The Silver Cord', 'date': '2023',
                 'media': [{'format': 'Digital Media'}]},
            ]}
        else:
            return FakeResponse(404)
        return FakeResponse(200, json.dumps(body).encode())
    monkeypatch.setattr(book_utils, '_get_public', fake)
    monkeypatch.setattr(music_lookup, 'MIN_INTERVAL', 0)
    music_lookup._cache.clear()
    return calls


def test_musicbrainz_albums_pressings_and_main_release(client, people, mb, monkeypatch):
    login(client, 'alice')
    data = client.get('/records/albums?q=silver cord by king gizzard').get_json()
    assert data['source'] == 'musicbrainz' and data['next'] == {'page': 2, 'by': 1}
    album = data['results'][0]
    assert (album['id'], album['year'], album['level']) == (GROUP, 2023, 'album')
    assert album['thumb'] == f'https://coverartarchive.org/release-group/{GROUP}/front-250'

    data = client.get(f'/records/pressings?source=musicbrainz&id={GROUP}&format=vinyl').get_json()
    assert [r['catalog_number'] for r in data['results']] == ['K2', 'K1']        # the digital one dropped
    assert all(r['source'] == 'musicbrainz' for r in data['results']) and data['next'] is None
    assert parse_qs(urlsplit(mb[-1]).query)['release-group'] == [GROUP]

    # "Use this" on the album: its earliest pressing
    looked_up = []
    monkeypatch.setattr(music_lookup, 'lookup', lambda mbid: looked_up.append(mbid) or
                        {'found': True, 'details': {}, 'sources': [], 'cover': None})
    client.get(f'/records/lookup?mb_group={GROUP}')
    assert looked_up == ['a' * 8 + '-0000-0000-0000-' + 'a' * 12]


# --- Books and movies: Show more, and "by" for books ----------------------------------

def test_books_by_author_and_show_more(client, people, monkeypatch):
    asked = []

    def volumes(q, n, start=0):
        asked.append((q, n, start))
        return [{'volumeInfo': {'title': 'Dune', 'subtitle': f'Edition {start + i}',
                                'authors': ['Frank Herbert']}} for i in range(n)]
    monkeypatch.setattr(book_utils, '_google_volumes', volumes)
    login(client, 'alice')
    data = client.get('/books/search_books?q=dune by frank herbert').get_json()
    assert asked[0] == ('intitle:dune inauthor:frank inauthor:herbert', 10, 0)
    assert len(data['items']) == 10 and data['next'] == {'page': 2, 'by': 1}
    client.get('/books/search_books?q=dune by frank herbert&page=2&by=1')
    assert asked[-1] == ('intitle:dune inauthor:frank inauthor:herbert', 10, 10)


def test_books_open_library_keeps_show_more_there(client, people, monkeypatch):
    monkeypatch.setattr(book_utils, '_google_volumes', lambda q, n, start=0: None)     # Google down
    pages = []

    def ol(query=None, max_results=15, title=None, author=None, page=1):
        pages.append(page)
        return [{'volumeInfo': {'title': 'x'}}] * max_results
    monkeypatch.setattr(book_utils, 'search_open_library', ol)
    login(client, 'alice')
    data = client.get('/books/search_books?q=dune').get_json()
    assert data['next'] == {'page': 2, 'by': 0, 'src': 'ol'}
    client.get('/books/search_books?q=dune&page=2&by=0&src=ol')
    assert pages == [1, 2]


def test_movies_show_more_in_tens(client, people, monkeypatch):
    monkeypatch.setattr(media_lookup, 'tmdb_key', lambda: 'k')
    asked = []

    def tmdb(path, **params):
        asked.append(params['page'])
        return {'total_pages': 2, 'results': [
            {'id': params['page'] * 100 + i, 'media_type': 'movie', 'title': f'Jaws {i}'} for i in range(20)]}
    monkeypatch.setattr(media_lookup, '_tmdb', tmdb)
    login(client, 'alice')
    first = client.get('/videos/search?q=Jaws').get_json()
    second = client.get('/videos/search?q=Jaws&page=2').get_json()
    third = client.get('/videos/search?q=Jaws&page=4').get_json()
    assert [r['id'] for r in first['results']] == list(range(100, 110)) and first['next'] == {'page': 2}
    assert [r['id'] for r in second['results']] == list(range(110, 120)) and second['next'] == {'page': 3}
    assert third['next'] is None and asked == [1, 1, 2]


def test_add_page_offers_show_more_and_album_pressings():
    """The page side: one Show more for every type, built from `next`."""
    from pathlib import Path
    js = (Path(__file__).resolve().parent.parent / 'static' / 'add_item.js').read_text()
    assert "searchUrl: q => `/records/albums?q=" in js
    assert 'new URLSearchParams(next)' in js and 'data-more' in js and 'data-pressings' in js
