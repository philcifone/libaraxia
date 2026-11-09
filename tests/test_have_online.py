"""Do I have this? "Not here" online (ROADMAP 13b): /have/online, the
ranking, and the add pages' pre-fill from a candidate's id.

The sources are replaced with fixed sample answers (the same shapes the
lookup modules return), so nothing here reaches the internet."""
import time

import pytest

from conftest import add_book, login
from test_videos import EAN
from utils import book_utils, discogs_lookup, have_online, media_lookup, music_lookup

MBID = '0f1e2d3c-4b5a-6978-8a9b-0c1d2e3f4a5b'


def volume(title, authors, isbn=None, year='2021'):
    """A search_google_books row."""
    return {'volumeInfo': {'title': title, 'authors': authors, 'publishedDate': year,
                           'industryIdentifiers': [{'type': 'ISBN_13', 'identifier': isbn}] if isbn else [],
                           'imageLinks': {'thumbnail': 'https://books.google.com/books/content?id=x&img=1&zoom=1'}}}


def release(rid, artist, title, year=2022):
    """A discogs_lookup.search row."""
    return {'id': rid, 'source': 'discogs', 'title': title, 'artist': artist, 'year': year,
            'country': 'US', 'label': '', 'catalog_number': '', 'format': 'LP',
            'format_label': 'LP', 'thumb': 'https://i.discogs.com/x.jpg'}


@pytest.fixture
def sources(monkeypatch):
    """Sample answers per source, set by each test; `calls` records who was asked."""
    answers = {'books': [], 'films': [], 'albums': [], 'upc': None, 'album_codes': [], 'film_codes': []}
    calls = []

    def books(q, n=15):
        calls.append('books')
        return answers['books']

    def films(q, year=None, limit=8):
        calls.append('tmdb')
        return answers['film_codes'] if answers['upc'] else answers['films']

    def albums(q, kind='', limit=12):
        calls.append('discogs')
        return answers['albums']

    def upc(code):
        calls.append('upcitemdb')
        return answers['upc']

    def album_codes(ean):
        calls.append('discogs-barcode')
        return answers['album_codes']

    def nothing(*a, **k):
        calls.append('other')
        return []

    monkeypatch.setattr(book_utils, 'search_google_books', books)
    monkeypatch.setattr(media_lookup, 'tmdb_key', lambda: 'k')
    monkeypatch.setattr(media_lookup, 'tmdb_search', films)
    monkeypatch.setattr(media_lookup, 'upcitemdb', upc)
    monkeypatch.setattr(discogs_lookup, 'enabled', lambda: True)
    monkeypatch.setattr(discogs_lookup, 'search', albums)
    monkeypatch.setattr(discogs_lookup, 'barcode_search', album_codes)
    monkeypatch.setattr(music_lookup, 'search', nothing)
    monkeypatch.setattr(music_lookup, 'barcode_search', nothing)
    media_lookup._cache.clear()
    return answers, calls


def online(client, q):
    r = client.get('/have/online', query_string={'q': q})
    assert r.status_code == 200
    return r.get_json()


# ------------------------------------------------------------ ranking

def test_score_is_word_coverage_plus_bonuses():
    s = have_online.score_text
    assert s('orville peck pony', 'Pony', 'Orville Peck') == pytest.approx(1.45)
    assert s('orville peck pony', 'Pony', 'R. J. Palacio') == pytest.approx(1 / 3, abs=0.001)
    assert s('dune', 'Dune', 'Frank Herbert') == 1.25                     # exact title
    assert s('dune', 'Dune Messiah', 'Frank Herbert') < s('dune', 'Dune', 'Frank Herbert')
    assert s('Les Misérables', 'Les Miserables', '') == 1.25             # folded
    assert s('pony', 'Horses', 'Nobody') == 0                            # not a match at all


def test_orville_peck_pony_is_the_album(client, people, sources):
    answers, _ = sources
    answers['books'] = [volume('Pony', ['R. J. Palacio'], '9780553508116'),
                        volume('Orville: A Dog Story', ['Haven Kimmel'])]
    answers['films'] = [{'id': 11, 'title': 'Pony', 'year': 2017, 'poster': None}]
    answers['albums'] = [release(14104321, 'Orville Peck', 'Pony', 2019)]
    login(client, 'alice')
    data = online(client, 'orville peck pony')
    best = data['best']
    assert best['type'] == 'record' and best['title'] == 'Pony' and best['creator'] == 'Orville Peck'
    assert best['type_label'] == 'Album'
    assert [g['type'] for g in data['groups']] == ['book', 'video']      # the rest, by type
    assert data['groups'][0]['items'][0]['title'] == 'Pony'              # Palacio's, best book first
    assert data['credits'] == ['discogs', 'tmdb']
    # Its add links carry the Discogs id
    assert best['wishlist_url'] == '/wishlist/add?type=record&discogs=14104321'
    assert best['shelf_url'] == '/records/add?discogs=14104321'


def test_a_title_that_is_a_book_and_an_album(client, people, sources):
    answers, _ = sources
    answers['books'] = [volume('Rumours', ['Anna Godbersen'], '9780061345692')]
    answers['albums'] = [release(1873013, 'Fleetwood Mac', 'Rumours', 1977)]
    login(client, 'alice')
    data = online(client, 'rumours')                         # a tie: both shown, one tap apart
    assert {data['best']['type'], data['groups'][0]['type']} == {'book', 'record'}
    data = online(client, 'fleetwood mac rumours')           # the artist settles it
    assert data['best']['type'] == 'record'
    assert data['groups'][0]['items'][0]['title'] == 'Rumours'


def test_each_types_links_carry_its_id(client, people, sources):
    answers, _ = sources
    answers['books'] = [volume('Heat', ['Bill Buford'], '9781400034475'), volume('Heat Wave', ['Nobody'])]
    answers['films'] = [{'id': 949, 'title': 'Heat', 'year': 1995, 'poster': 'https://image.tmdb.org/t/p/w185/x.jpg'}]
    login(client, 'alice')
    data = online(client, 'heat')
    every = [data['best']] + [c for g in data['groups'] for c in g['items']]
    by = {(c['type'], c['title']): c for c in every}
    assert by[('book', 'Heat')]['wishlist_url'] == '/wishlist/add?type=book&isbn=9781400034475'
    assert by[('book', 'Heat')]['shelf_url'] == '/books/add?isbn=9781400034475'
    assert by[('video', 'Heat')]['wishlist_url'] == '/wishlist/add?type=video&tmdb_id=949'
    assert by[('video', 'Heat')]['shelf_url'] == '/videos/add?tmdb_id=949'
    # No ISBN: the title and author instead
    assert by[('book', 'Heat Wave')]['wishlist_url'] == '/wishlist/add?type=book&title=Heat+Wave&author=Nobody'


def test_musicbrainz_ids_when_discogs_is_busy(client, people, sources, monkeypatch):
    def busy(*a, **k):
        raise discogs_lookup.Busy()
    monkeypatch.setattr(discogs_lookup, 'search', busy)
    monkeypatch.setattr(music_lookup, 'search', lambda q, kind='', limit=12: [
        {'id': MBID, 'title': 'Pony', 'artist': 'Orville Peck', 'year': 2019, 'format_label': 'LP', 'thumb': None}])
    login(client, 'alice')
    best = online(client, 'orville peck pony')['best']
    assert best['source'] == 'musicbrainz' and best['shelf_url'] == f'/records/add?mbid={MBID}'


# ------------------------------------------------------------ when it asks

def test_a_local_hit_never_calls_out(client, db, people, sources):
    _, calls = sources
    add_book(db, people['alice'], title='Dune')
    login(client, 'alice')
    data = online(client, 'dune')
    assert data['local'] is True and data['best'] is None and calls == []
    # and the page doesn't ask either
    html = client.get('/have/', query_string={'q': 'dune'}).get_data(as_text=True)
    assert 'have-online' not in html


def test_not_here_page_asks_and_keeps_title_links(client, people):
    login(client, 'alice')
    html = client.get('/have/', query_string={'q': 'orville peck pony'}).get_data(as_text=True)
    assert 'data-online-url="/have/online?q=orville+peck+pony"' in html
    # The by-hand fallback carries the title, for each type
    for url in ('/wishlist/add?type=book&amp;title=orville+peck+pony',
                '/wishlist/add?type=record&amp;title=orville+peck+pony',
                '/videos/add?title=orville+peck+pony'):
        assert url in html
    assert 'have-online' not in client.get('/have/?q=123456789019').get_data(as_text=True)   # bad code


def test_a_slow_source_is_left_out(client, people, sources, monkeypatch):
    answers, _ = sources
    answers['albums'] = [release(1, 'Orville Peck', 'Pony')]

    def slow(q, n=15):
        time.sleep(0.5)
        return [volume('Pony', ['R. J. Palacio'])]
    monkeypatch.setattr(book_utils, 'search_google_books', slow)
    monkeypatch.setattr(have_online, 'DEADLINE', 0.1)
    login(client, 'alice')
    started = time.monotonic()
    data = online(client, 'orville peck pony')
    assert time.monotonic() - started < 0.4
    assert data['status']['book'] == 'slow' and data['best']['type'] == 'record'
    assert data['groups'] == []


def test_a_failing_source_is_logged_not_shown(client, people, sources, monkeypatch):
    def broken(q, n=15):
        raise RuntimeError('secret detail')
    monkeypatch.setattr(book_utils, 'search_google_books', broken)
    login(client, 'alice')
    r = client.get('/have/online?q=anything')
    assert r.status_code == 200 and r.get_json()['status']['book'] == 'failed'
    assert 'secret detail' not in r.get_data(as_text=True)


# ------------------------------------------------------------ barcodes

JAWS_UPC = {'title': 'Jaws (1975) [VHS]', 'brand': 'MCA', 'description': '', 'category': 'Media > DVDs & Videos',
            'images': []}


def test_barcode_both_sources_recognise_it(client, people, sources):
    answers, calls = sources
    answers['upc'] = JAWS_UPC
    answers['film_codes'] = [{'id': 578, 'title': 'Jaws', 'year': 1975, 'poster': None}]
    answers['album_codes'] = [release(42, 'John Williams', 'Jaws (Soundtrack)', 1975)]
    login(client, 'alice')
    data = online(client, EAN)
    assert {'upcitemdb', 'discogs-barcode'} <= set(calls)              # asked together
    shown = [data['best']] + [c for g in data['groups'] for c in g['items']]
    assert {c['type'] for c in shown} == {'video', 'record'}
    album = next(c for c in shown if c['type'] == 'record')
    movie = next(c for c in shown if c['type'] == 'video')
    assert data['best'] is album                                      # recognised by the exact code
    assert album['wishlist_url'] == f'/wishlist/add?type=record&discogs=42&barcode={EAN}'
    assert movie['shelf_url'] == f'/videos/add?tmdb_id=578&barcode={EAN}'


def test_barcode_only_one_source_or_neither(client, people, sources):
    answers, _ = sources
    answers['album_codes'] = [release(42, 'Orville Peck', 'Pony')]
    login(client, 'alice')
    data = online(client, EAN)
    assert data['best']['type'] == 'record' and data['groups'] == []
    # A CD UPCitemdb knows, TMDb doesn't: not offered as a movie
    answers['album_codes'] = []
    answers['upc'] = {**JAWS_UPC, 'title': 'Pony CD', 'category': 'Media > Music & Sound Recordings'}
    media_lookup._cache.clear()
    assert online(client, EAN)['best'] is None                         # the page keeps its choice


# ------------------------------------------------------------ add pages

def test_add_pages_look_up_the_id_on_load(client, people, monkeypatch):
    monkeypatch.setattr(media_lookup, 'tmdb_key', lambda: 'k')
    monkeypatch.setattr(discogs_lookup, 'enabled', lambda: True)
    login(client, 'alice')
    get = lambda url: client.get(url).get_data(as_text=True)
    assert 'data-lookup-url="/videos/lookup?tmdb_id=949"' in get('/videos/add?tmdb_id=949')
    assert 'data-lookup-url="/videos/lookup?tmdb_id=949"' in get('/wishlist/add?type=video&tmdb_id=949')
    assert 'data-lookup-url="/records/lookup?discogs=42"' in get('/records/add?discogs=42')
    assert f'data-lookup-url="/records/lookup?mbid={MBID}"' in get(f'/wishlist/add?type=record&mbid={MBID}')
    html = get(f'/records/add?discogs=42&barcode={EAN}')                # and the code goes in its field
    assert 'data-lookup-url="/records/lookup?discogs=42"' in html and f'value="{EAN}"' in html
    html = get('/wishlist/add?type=book&isbn=9780553508116')            # books: the ISBN box, as before
    assert 'value="9780553508116"' in html and 'data-auto-lookup="1"' in html
    # Anything else in those parameters is ignored
    for url in ('/videos/add?tmdb_id=abc', '/records/add?discogs=1;drop', '/records/add?mbid=nope'):
        assert 'data-lookup-url' not in get(url)


def test_add_pages_take_a_title(client, people):
    login(client, 'alice')
    for url in ('/books/add?title=Pony&author=R.+J.+Palacio', '/wishlist/add?type=book&title=Pony&author=R.+J.+Palacio',
                '/records/add?title=Pony&author=R.+J.+Palacio', '/wishlist/add?type=video&title=Pony&author=R.+J.+Palacio'):
        html = client.get(url).get_data(as_text=True)
        assert 'value="Pony"' in html and 'value="R. J. Palacio"' in html, url
        assert 'data-lookup-url' not in html
