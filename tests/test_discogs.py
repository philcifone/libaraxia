"""Add Album from Discogs (ROADMAP 8B.10), and the shop links (8B.11).

No network: Discogs' JSON is faked at book_utils._get_public, which also
records what was asked (the token must travel in a header, never the URL).
"""
import json

import pytest

from conftest import login
from test_records import FakeResponse, fake_mb, SEARCH as MB_SEARCH  # noqa: F401 (fixture)
from utils import discogs_lookup, media, music_lookup

TOKEN = 'test-token-not-real'

SEARCH = {'results': [
    {'id': 1873013, 'title': 'Fleetwood Mac - Rumours', 'year': '1977', 'country': 'US',
     'label': ['Warner Bros. Records'], 'catno': 'BSK 3010', 'format': ['Vinyl', 'LP', 'Album'],
     'thumb': 'https://i.discogs.com/thumb.jpg'},
    {'id': 2, 'title': 'Fleetwood Mac - Rumours', 'year': '1977', 'country': 'US',
     'label': ['Warner Bros. Records'], 'catno': 'M5 3010', 'format': ['Cassette', 'Album']},
    {'id': 3, 'title': 'Fleetwood Mac - Rumours', 'format': ['File', 'FLAC', 'Album']},   # digital
]}

RELEASE = {
    'id': 1873013, 'title': 'Rumours', 'year': 1977, 'country': 'US',
    'artists': [{'name': 'Fleetwood Mac', 'anv': '', 'join': ''}],
    'labels': [{'name': 'Warner Bros. Records', 'catno': 'BSK 3010'}],
    'formats': [{'name': 'Vinyl', 'qty': '1', 'descriptions': ['LP', 'Album']}],
    'genres': ['Rock'], 'styles': ['Soft Rock'],
    'tracklist': [
        {'type_': 'heading', 'position': '', 'title': 'Side One', 'duration': ''},
        {'type_': 'track', 'position': 'A1', 'title': 'Second Hand News', 'duration': '2:43'},
        {'type_': 'track', 'position': 'A2', 'title': 'Dreams', 'duration': '4:14'},
    ],
    'images': [{'type': 'secondary', 'uri': 'https://i.discogs.com/back.jpg'},
               {'type': 'primary', 'uri': 'https://i.discogs.com/front.jpg'}],
}


@pytest.fixture
def fake_discogs(monkeypatch):
    calls, covers = [], []
    replies = {'status': 200}

    def fake_get_public(url, headers=None):
        calls.append((url, headers))
        if replies['status'] != 200:
            return FakeResponse(replies['status'])
        if url.startswith('https://api.discogs.com/database/search?'):
            return FakeResponse(200, json.dumps(SEARCH).encode())
        if url == 'https://api.discogs.com/releases/1873013':
            return FakeResponse(200, json.dumps(RELEASE).encode())
        return FakeResponse(404)

    def fake_save(urls):
        covers.extend(urls)
        return 'uploads/cover_discogs.jpg'
    monkeypatch.setenv('DISCOGS_TOKEN', TOKEN)
    monkeypatch.setattr(discogs_lookup.book_utils, '_get_public', fake_get_public)
    monkeypatch.setattr(discogs_lookup.book_utils, 'save_best_cover', fake_save)
    monkeypatch.setattr(discogs_lookup, 'MIN_INTERVAL', 0)
    discogs_lookup._cache.clear()
    return calls, covers, replies


def test_off_without_a_token(monkeypatch):
    monkeypatch.setenv('DISCOGS_TOKEN', '')
    assert not discogs_lookup.enabled()


def test_search_uses_discogs_with_token_in_header(client, people, fake_discogs):
    calls, _, _ = fake_discogs
    login(client, 'alice')
    data = client.get('/records/search?q=fleetwood rumours&format=vinyl').get_json()
    assert data['source'] == 'discogs'
    assert [r['id'] for r in data['results']] == [1873013, 2]          # the FLAC is dropped
    first = data['results'][0]
    assert (first['title'], first['artist'], first['format'], first['catalog_number'],
            first['label'], first['year'], first['source']) == \
        ('Rumours', 'Fleetwood Mac', 'LP', 'BSK 3010', 'Warner Bros. Records', 1977, 'discogs')
    assert data['results'][1]['format'] == 'Cassette'
    url, headers = calls[0]
    assert 'format=Vinyl' in url and TOKEN not in url
    assert headers['Authorization'] == f'Discogs token={TOKEN}'
    assert headers['User-Agent'].startswith('Libaraxia/')
    # Cached: asking again sends nothing
    client.get('/records/search?q=fleetwood rumours&format=vinyl')
    assert len(calls) == 1


def test_lookup_fills_the_form(client, people, fake_discogs):
    _, covers, _ = fake_discogs
    login(client, 'alice')
    data = client.get('/records/lookup?discogs=1873013').get_json()
    assert data['found'] and data['sources'] == ['Discogs'] and data['cover'] == 'uploads/cover_discogs.jpg'
    d = data['details']
    assert (d['title'], d['author'], d['publisher'], d['catalog_number'], d['year'], d['format'],
            d['genre'], d['runtime_minutes']) == \
        ('Rumours', 'Fleetwood Mac', 'Warner Bros. Records', 'BSK 3010', 1977, 'LP', 'Rock', 7)
    assert d['description'].startswith('Side One\nA1 Second Hand News (2:43)\nA2 Dreams (4:14)')
    assert 'Pressing: US 1977' in d['description']
    assert covers[0] == 'https://i.discogs.com/front.jpg'               # the primary image first


@pytest.mark.parametrize('param', ['abc', '1; DROP', '9' * 13, '-1'])
def test_lookup_takes_only_a_number(client, people, fake_discogs, param):
    calls, _, _ = fake_discogs
    login(client, 'alice')
    assert client.get(f'/records/lookup?discogs={param}').status_code == 400
    assert calls == []


def test_busy_discogs_falls_back_to_musicbrainz(client, people, fake_discogs, fake_mb, monkeypatch):
    # Both fixtures patch the same _get_public; route by host instead
    d_calls, _, _ = fake_discogs
    mb_calls, _, _ = fake_mb
    from utils import book_utils

    def by_host(url, headers=None):
        if 'discogs.com' in url:
            d_calls.append((url, headers))
            return FakeResponse(429)
        mb_calls.append((url, headers))
        return FakeResponse(200, json.dumps(MB_SEARCH).encode())
    monkeypatch.setattr(book_utils, '_get_public', by_host)
    login(client, 'alice')
    data = client.get('/records/search?q=joni blue').get_json()
    assert data['source'] == 'musicbrainz' and data['results'][0]['source'] == 'musicbrainz'
    assert len(d_calls) == 1 and len(mb_calls) == 1                     # one try each, no retries


@pytest.mark.parametrize('tokens, expected', [
    (['Vinyl', 'LP', 'Album'], 'LP'),
    (['Vinyl', '7"', '45 RPM', 'Single'], '7in'),
    (['Vinyl', '12"', '33 ⅓ RPM', 'Single'], '12in'),
    (['Vinyl', '10"'], '10in'),
    (['Vinyl', '12"', 'EP'], 'EP'),
    (['CD', 'Album'], 'CD'),
    (['CDr'], 'CD'),
    (['Cassette', 'Album'], 'Cassette'),
    (['File', 'MP3'], None),
])
def test_album_format(tokens, expected):
    assert discogs_lookup.album_format(tokens) == expected


def test_artist_credits():
    assert discogs_lookup._artists([{'name': 'Simon (2)', 'join': '&'},
                                    {'name': 'Garfunkel', 'join': ','}]) == 'Simon & Garfunkel'
    assert discogs_lookup._artists([{'name': 'Prince', 'anv': 'The Artist'}]) == 'The Artist'


# --- shop links (8B.11) -------------------------------------------------------------

def row(**kw):
    base = {'title': 'Heat', 'author': 'Michael Mann', 'format': None, 'media_type': 'book'}
    return {**base, **kw}


def test_buy_links_per_type():
    assert [n for n, _ in media.buy_links(row())] == ['ThriftBooks', 'Bookshop.org']
    (name, url), = media.buy_links(row(media_type='video', format='VHS'))
    assert name == 'eBay' and url == 'https://www.ebay.com/sch/i.html?_nkw=Heat+VHS'
    (name, url), = media.buy_links(row(media_type='record', title='Rumours',
                                         author='Fleetwood Mac', format='Cassette'))
    assert name == 'Discogs'
    assert url == 'https://www.discogs.com/sell/list?q=Fleetwood+Mac+Rumours&format=Cassette'
    (_, url), = media.buy_links(row(media_type='record', title='Blue', author='Joni', format='12in'))
    assert url.endswith('&format=Vinyl')


# --- barcodes (8B.12) ----------------------------------------------------------------

def test_barcode_lookup_on_discogs(client, people, fake_discogs):
    calls, _, _ = fake_discogs
    login(client, 'alice')
    data = client.get('/records/lookup?barcode=075992731324').get_json()   # UPC-A
    assert data['found'] and data['sources'] == ['Discogs'] and data['barcode'] == '0075992731324'
    assert data['details']['title'] == 'Rumours'
    # Asked as printed (12 digits), then the first release
    assert 'barcode=075992731324' in calls[0][0]
    assert calls[1][0] == 'https://api.discogs.com/releases/1873013'


def test_barcode_lookup_falls_back_to_musicbrainz(client, people, fake_mb, monkeypatch):
    """No Discogs token: MusicBrainz, asked for both the 12- and 13-digit forms."""
    from urllib.parse import parse_qs, urlsplit
    from test_records import MBID
    calls, _, _ = fake_mb
    login(client, 'alice')
    data = client.get('/records/lookup?barcode=075992731324').get_json()
    query = parse_qs(urlsplit(calls[0][0]).query)['query'][0]
    assert query == 'barcode:0075992731324 OR barcode:075992731324'
    assert data['found'] and data['details']['title'] == 'Blue'
    assert MBID in calls[1][0]


@pytest.mark.parametrize('code, why', [('12345', 'valid'), ('9780141439518', 'ISBN')])
def test_barcode_lookup_refuses_bad_codes(client, people, fake_discogs, code, why):
    calls, _, _ = fake_discogs
    login(client, 'alice')
    r = client.get(f'/records/lookup?barcode={code}')
    assert r.status_code == 400 and why in r.get_json()['error'] and calls == []


def test_barcode_duplicates_for_records(client, db, people):
    from test_records import add_record
    record = add_record(db, people['alice'], title='Rumours', artist='Fleetwood Mac')
    db.execute("UPDATE books SET barcode = '0075992731324' WHERE id = ?", (record,))
    db.commit()
    login(client, 'bob')                                            # alice's household
    r = client.post('/records/check_duplicates', json={'barcode': '075992731324', 'title': 'Something else'})
    (d,) = r.get_json()['duplicates']
    assert d['id'] == record and 'barcode' in d['match_reason']


def test_add_book_offers_movie_or_album_for_other_barcodes(client, people):
    login(client, 'alice')
    page = client.get('/books/add').get_data(as_text=True)
    assert 'data-music-add-url="/records/add"' in page
    page = client.get('/wishlist/add?type=book').get_data(as_text=True)
    assert 'data-music-add-url="/wishlist/add?type=record"' in page
