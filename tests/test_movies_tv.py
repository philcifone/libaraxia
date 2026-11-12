"""Movies & TV (ROADMAP 15.1): a video is a movie or TV.

A TV box set is a video row like a film (same formats, statuses and shelf)
with books.video_kind = 'tv' and an optional free-text season; NULL is a
movie (migration 034, media.video_kind). The migration itself is tested in
test_migrations.py.

people: alice (admin) + bob share a household; carol is alice's friend.
"""
import csv
import io

import pytest

from conftest import login
from utils import media
from utils.book_utils import card_json


def add_video(db, owner_id, title, kind=None, season=None, fmt='DVD'):
    cur = db.execute('''
        INSERT INTO books (title, author, format, added_by, media_type, video_kind, season)
        VALUES (?, 'Someone', ?, ?, 'video', ?, ?)
    ''', (title, fmt, owner_id, kind, season))
    db.commit()
    return cur.lastrowid


# --- media helpers ---------------------------------------------------------------

def test_video_kind_stores_tv_or_none():
    """One spelling for a movie: None, like a plain book's format."""
    assert media.video_kind('tv') == 'tv'
    assert media.video_kind(' TV ') == 'tv'
    assert media.video_kind('movie') is None
    assert media.video_kind('') is None
    assert media.video_kind('anime') is None


def test_kind_of_reads_null_as_movie(db, people):
    tv = add_video(db, people['bob'], 'The Wire', 'tv', 'Season 1')
    film = add_video(db, people['bob'], 'Heat')
    rows = {r['id']: r for r in db.execute('SELECT * FROM books WHERE id IN (?, ?)', (tv, film))}
    assert media.kind_of(rows[tv]) == 'tv'
    assert media.kind_of(rows[film]) == 'movie'
    assert media.kind_of({'media_type': 'book'}) is None


# --- carried through: grid JSON and the export -------------------------------------

def test_card_json_carries_kind_and_season(db, people):
    vid = add_video(db, people['bob'], 'The Wire', 'tv', 'Season 1')
    rows = db.execute('SELECT * FROM library_videos WHERE id = ?', (vid,)).fetchall()
    card = card_json(db, people['bob'], rows)[0]
    assert (card['video_kind'], card['season']) == ('tv', 'Season 1')


def test_library_export_has_kind_and_season(client, db, people):
    add_video(db, people['bob'], 'The Wire', 'tv', 'Season 1')
    add_video(db, people['bob'], 'Heat')
    login(client, 'bob')
    rows = list(csv.DictReader(io.StringIO(client.get('/user/export_library').get_data(as_text=True))))
    by_title = {r['Title']: r for r in rows}
    assert (by_title['The Wire']['Kind'], by_title['The Wire']['Season']) == ('tv', 'Season 1')
    assert (by_title['Heat']['Kind'], by_title['Heat']['Season']) == ('movie', '')


# --- wording: "Movies & TV" for the section, per kind for an item -------------------

def test_section_and_kind_words():
    section = media.media_labels(media.VIDEO)
    assert section['section'] == 'Movies & TV' and section['kind'] is None
    assert media.SECTION_NAMES[media.VIDEO] == 'Movies & TV'
    tv = media.media_labels(media.VIDEO, 'tv')
    assert (tv['Noun'], tv['creator'], tv['by'], tv['section']) == ('TV Show', 'Creator', 'created by', 'Movies & TV')
    movie = media.media_labels(media.VIDEO, 'movie')
    assert (movie['Noun'], movie['creator']) == ('Movie', 'Director')
    # A kind means nothing to the other types
    assert media.media_labels(media.RECORD, 'tv')['Noun'] == 'Album'


def test_grid_and_switch_say_movies_and_tv(client, db, people):
    add_video(db, people['alice'], 'Heat')
    login(client, 'alice')
    page = client.get('/videos/').get_data(as_text=True)
    assert 'My Movies &amp; TV' in page
    assert '>Movies &amp; TV<' in page                       # the Books | Movies & TV | Music switch
    assert 'Search your 1 movie or show' in page


def test_tv_item_pages_say_tv_show(client, db, people):
    vid = add_video(db, people['alice'], 'The Wire', 'tv', 'Season 1')
    login(client, 'alice')
    page = client.get(f'/videos/{vid}').get_data(as_text=True)
    assert 'created by' in page and 'About this Show' in page and 'Edit TV Show' in page
    assert 'Remove from Movies &amp; TV' in page
    edit = client.get(f'/videos/edit/{vid}').get_data(as_text=True)
    assert 'Edit TV Show</h1>' in edit and '<span class="when-tv">Creator</span>' in edit
    assert 'name="video_kind" value="tv" checked' in edit and 'value="Season 1"' in edit


def test_movie_item_pages_keep_movie_words(client, db, people):
    vid = add_video(db, people['alice'], 'Heat')
    login(client, 'alice')
    page = client.get(f'/videos/{vid}').get_data(as_text=True)
    assert 'directed by' in page and 'Edit Movie' in page and 'TV Show' not in page


def test_feed_words_a_tv_show(client, db, people):
    """The feed's rows carry the kind, so a friend's new box set reads right."""
    add_video(db, people['carol'], 'The Wire', 'tv')
    login(client, 'alice')
    page = client.get('/feed/activity').get_data(as_text=True)
    assert 'added a new TV show' in page


# --- the form: Kind and Season on add and edit --------------------------------------

def tv_form(**overrides):
    data = {'title': 'The Wire', 'author': 'David Simon', 'publisher': 'HBO', 'year': '2002',
            'runtime_minutes': '', 'format': 'DVD', 'barcode': '', 'catalog_number': '',
            'genre': 'Crime', 'description': '', 'video_kind': 'tv', 'season': 'Season 1'}
    data.update(overrides)
    return data


def test_add_page_offers_kind_and_season(client, people):
    login(client, 'alice')
    page = client.get('/videos/add').get_data(as_text=True)
    assert 'name="video_kind" value="movie" checked' in page        # Movie is the default
    assert 'id="season"' in page and 'class="when-tv"' in page      # shown by CSS for TV only
    assert '<span class="when-movie">Director</span><span class="when-tv">Creator</span>' in page
    tv = client.get('/videos/add?kind=tv').get_data(as_text=True)
    assert 'Add a TV Show</h1>' in tv and 'name="video_kind" value="tv" checked' in tv
    # Music has neither
    music = client.get('/records/add').get_data(as_text=True)
    assert 'video_kind' not in music and 'id="season"' not in music


def test_add_tv_round_trip(client, db, people):
    login(client, 'alice')
    r = client.post('/videos/add', data=tv_form())
    assert r.status_code == 302
    row = db.execute("SELECT * FROM books WHERE title = 'The Wire'").fetchone()
    assert (row['media_type'], row['video_kind'], row['season']) == ('video', 'tv', 'Season 1')
    page = client.get(r.headers['Location']).get_data(as_text=True)
    assert 'added to your TV shows' in page

    # Edit: back to a movie drops the season; NULL is how a movie is stored
    r = client.post(f"/videos/edit/{row['id']}", data=tv_form(video_kind='movie', season='Season 1'))
    assert r.status_code == 302
    again = db.execute('SELECT video_kind, season FROM books WHERE id = ?', (row['id'],)).fetchone()
    assert tuple(again) == (None, None)
    r = client.post(f"/videos/edit/{row['id']}", data=tv_form(season='Complete series'))
    again = db.execute('SELECT video_kind, season FROM books WHERE id = ?', (row['id'],)).fetchone()
    assert tuple(again) == ('tv', 'Complete series')


def test_unknown_kind_is_a_movie(client, db, people):
    login(client, 'alice')
    client.post('/videos/add', data=tv_form(video_kind='anime'))
    assert tuple(db.execute("SELECT video_kind, season FROM books WHERE title = 'The Wire'").fetchone()) == (None, None)


def test_reshown_form_keeps_the_kind(client, people):
    """A refused submit (no title) shows the form again on TV with the season."""
    login(client, 'alice')
    r = client.post('/videos/add', data=tv_form(title=''))
    page = r.get_data(as_text=True)
    assert r.status_code == 400
    assert 'name="video_kind" value="tv" checked' in page and 'value="Season 1"' in page
    assert 'Add a TV Show</h1>' in page


def test_wishlist_add_keeps_the_kind(client, db, people):
    login(client, 'alice')
    r = client.post('/wishlist/add', data=tv_form(media_type='video'))
    assert r.status_code == 302
    row = db.execute("SELECT video_kind, season FROM books WHERE title = 'The Wire'").fetchone()
    assert tuple(row) == ('tv', 'Season 1')
    assert 'TV Show added to your wishlist' in client.get('/wishlist/view').get_data(as_text=True)


def test_records_never_get_a_kind(client, db, people):
    login(client, 'alice')
    client.post('/records/add', data={'title': 'Pony', 'author': 'Orville Peck', 'format': 'LP',
                                      'video_kind': 'tv', 'season': 'x'})
    assert tuple(db.execute("SELECT video_kind, season FROM books WHERE title = 'Pony'").fetchone()) == (None, None)


def test_add_button_has_a_tv_entry(client, db, people):
    login(client, 'alice')
    assert '/videos/add?kind=tv' in client.get('/videos/').get_data(as_text=True)


# --- the grid: TV badge, Kind filter, season in list view ---------------------------

def grid_titles(page):
    import re
    return re.findall(r'<h3 class="book-title[^"]*">\s*(.*?)\s*</h3>', page)


def test_season_short():
    assert media.season_short('Season 2') == 'S2'
    assert media.season_short('season 12') == 'S12'
    assert media.season_short('Seasons 1-3') == 'S1-3'
    assert media.season_short('Seasons 1 – 3') == 'S1–3'
    assert media.season_short('Complete series') == 'Complete series'
    assert media.season_short(None) == ''


def test_grid_badges_tv_and_shows_its_season_in_list_view(client, db, people):
    add_video(db, people['alice'], 'The Wire', 'tv', 'Season 2')
    add_video(db, people['alice'], 'Heat')
    login(client, 'alice')
    page = client.get('/videos/').get_data(as_text=True)
    assert page.count('class="tv-badge') == 1
    assert '<span class="book-season"> · TV, S2</span>' in page      # hidden in grid view by CSS
    assert 'created by Someone' in page and 'directed by Someone' in page


def test_kind_filter(client, db, people):
    add_video(db, people['alice'], 'The Wire', 'tv', 'Season 2')
    add_video(db, people['alice'], 'Heat')
    add_video(db, people['alice'], 'Alien', 'movie')       # stored by hand as 'movie': still a movie
    login(client, 'alice')
    page = client.get('/videos/').get_data(as_text=True)
    assert 'id="kind"' in page and '<option value="tv"' in page        # both kinds on the shelf
    assert grid_titles(client.get('/videos/?kind=tv').get_data(as_text=True)) == ['The Wire']
    assert grid_titles(client.get('/videos/?kind=movie').get_data(as_text=True)) == ['Alien', 'Heat']
    # Narrowed: the count moves out of the placeholder
    assert 'Search your 3' not in client.get('/videos/?kind=tv').get_data(as_text=True)


def test_kind_filter_only_with_both_kinds(client, db, people):
    add_video(db, people['alice'], 'Heat')
    login(client, 'alice')
    assert 'id="kind"' not in client.get('/videos/').get_data(as_text=True)
    assert 'id="kind"' not in client.get('/records/').get_data(as_text=True)


# --- lookup: TMDb movies and TV together, the kind fills Kind ------------------------

from utils import have_online, media_lookup               # noqa: E402  (grouped with their tests)

WIRE = {'id': 1438, 'media_type': 'tv', 'name': 'The Wire', 'first_air_date': '2002-06-02',
        'poster_path': '/wire.jpg'}
WIRE_FILM = {'id': 5, 'media_type': 'movie', 'title': 'The Wire', 'release_date': '1991-01-01'}
WIRE_SHOW = {'name': 'The Wire', 'first_air_date': '2002-06-02', 'overview': 'Baltimore.',
             'created_by': [{'name': 'David Simon'}], 'genres': [{'name': 'Crime'}],
             'episode_run_time': [60], 'number_of_seasons': 5, 'poster_path': '/wire.jpg'}
WIRE_UPC = {'items': [{'title': 'The Wire: The Complete First Season [DVD]', 'brand': 'HBO',
                       'images': [], 'category': 'Media > DVDs & Videos'}]}
WIRE_EAN = '0026359238222'      # a valid EAN-13 (check digit), standing in for the box's code


@pytest.fixture
def tmdb(monkeypatch):
    """Canned TMDb (and UPCitemdb) replies by URL; `calls` records what was asked."""
    calls = []

    def fake_json(url, params=None, headers=None):
        calls.append((url, params or {}))
        if url == media_lookup.UPCITEMDB_URL:
            return WIRE_UPC
        if url.endswith('/search/multi'):
            # The film comes first in TMDb's order, so a season must pick the show
            return {'results': [WIRE_FILM, WIRE, {'id': 9, 'media_type': 'person', 'name': 'x'}]} \
                if params['query'] == 'The Wire' else {'results': []}
        if url.endswith('/tv/1438'):
            return WIRE_SHOW
        return None
    monkeypatch.setenv('TMDB_API_KEY', 'k' * 32)
    monkeypatch.setattr(media_lookup, '_get_json', fake_json)
    monkeypatch.setattr(media_lookup.book_utils, 'save_best_cover', lambda urls: None)
    media_lookup._cache.clear()
    return calls


@pytest.mark.parametrize('title, expected', [
    ('The Wire: The Complete First Season', ('The Wire', 'Season 1')),
    ('Friends - Season 3', ('Friends', 'Season 3')),
    ('Sex and the City 2nd Season', ('Sex and the City', 'Season 2')),
    ('The Sopranos Seasons 1-3', ('The Sopranos', 'Seasons 1-3')),
    ('The Wire: Season 1 - 5 Disc Set', ('The Wire', 'Season 1')),       # a disc count, not a range
    ('Twin Peaks Complete Series', ('Twin Peaks', 'Complete series')),
    ('Season of the Witch', ('Season of the Witch', None)),              # a film's own title
    ('Jaws', ('Jaws', None)),
])
def test_split_season(title, expected):
    assert media_lookup.split_season(title) == expected


def test_search_lists_movies_and_tv_with_their_kind(app, tmdb):
    with app.app_context():
        found = media_lookup.tmdb_search('The Wire')
        assert [(f['kind'], f['title'], f['year']) for f in found] == [
            ('movie', 'The Wire', 1991), ('tv', 'The Wire', 2002)]           # the person is dropped
        # A year ranks rather than filters
        assert [f['kind'] for f in media_lookup.tmdb_search('The Wire', 2002)] == ['tv', 'movie']
    assert [url.rsplit('/', 2)[-2:] for url, _ in tmdb] == [['search', 'multi']] * 2


def test_lookup_a_picked_show(client, people, tmdb):
    login(client, 'alice')
    data = client.get('/videos/lookup?tmdb_id=1438&kind=tv').get_json()
    d = data['details']
    assert data['found'] and tmdb[-1][0].endswith('/tv/1438')
    assert (d['title'], d['author'], d['year'], d['genre'], d['video_kind']) == \
        ('The Wire', 'David Simon', 2002, 'Crime', 'tv')
    assert d['runtime_minutes'] == ''           # a set's total isn't known: left empty


def test_lookup_a_box_set_by_barcode(app, tmdb):
    """UPCitemdb's product name has the season; it's taken off for the search
    (which then prefers the show) and fills Season."""
    with app.app_context():
        d = media_lookup.lookup(barcode=WIRE_EAN)['details']
    assert (d['title'], d['author'], d['video_kind'], d['season'], d['publisher']) == \
        ('The Wire', 'David Simon', 'tv', 'Season 1', 'HBO')
    assert any(p.get('query') == 'The Wire' for url, p in tmdb if url.endswith('/search/multi'))


def test_search_route_says_the_kind(client, people, tmdb):
    login(client, 'alice')
    results = client.get('/videos/search?q=The+Wire').get_json()['results']
    assert {(r['id'], r['kind']) for r in results} == {(5, 'movie'), (1438, 'tv')}


def test_have_online_tv_candidate(client, people, monkeypatch):
    """Do I have this?: a TMDb show is a "TV Show", its add links carry
    kind=tv, and the add page starts on TV and looks the show up as one."""
    monkeypatch.setattr(media_lookup, 'tmdb_key', lambda: 'k')
    monkeypatch.setattr(media_lookup, 'tmdb_search', lambda q, year=None, limit=8: [
        {'id': 1438, 'kind': 'tv', 'title': 'The Wire', 'year': 2002, 'poster': None},
        {'id': 5, 'kind': 'movie', 'title': 'The Wire Movie', 'year': 1991, 'poster': None}])
    for name in ('books_by_text', 'music_by_text'):
        monkeypatch.setattr(have_online, name, lambda q: [])
    login(client, 'alice')
    data = client.get('/have/online?q=the+wire').get_json()
    best = data['best']
    assert (best['title'], best['type_label']) == ('The Wire', 'TV Show')
    assert best['shelf_url'] == '/videos/add?tmdb_id=1438&kind=tv'
    assert best['wishlist_url'] == '/wishlist/add?type=video&tmdb_id=1438&kind=tv'
    group = data['groups'][0]
    assert group['heading'] == 'Other movies and shows'
    assert group['items'][0]['type_label'] == 'Movie' and 'kind=' not in group['items'][0]['shelf_url']

    page = client.get(best['shelf_url']).get_data(as_text=True)
    assert 'data-lookup-url="/videos/lookup?tmdb_id=1438&amp;kind=tv"' in page
    assert 'name="video_kind" value="tv" checked' in page and 'Add a TV Show</h1>' in page
