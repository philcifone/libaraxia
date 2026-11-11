"""The cover fetcher for movies and albums (utils/media_covers.py).

Only a cover that can be trusted is kept: one found by barcode, or one whose
title (and, for an album, artist) is the same as ours. The sources are faked;
tests never reach the network."""
import pytest

from conftest import add_book, login, scalar
from utils import discogs_lookup, media_covers, media_lookup, music_lookup


@pytest.mark.parametrize('ours, theirs, same', [
    ('Jaws', 'Jaws', True),
    ('The Wall', 'Wall (Remastered)', True),
    ('Rumours', 'Rumours [Deluxe Edition]', True),
    ('Amélie', 'Amelie', True),
    ('Jaws', 'Jaws 2', False),
    ('Blue', 'Blue Lines', False),
    ('', '', False),
])
def test_same_title(ours, theirs, same):
    assert media_covers.same_title(ours, theirs) is same


@pytest.mark.parametrize('ours, theirs, same', [
    ('Joni Mitchell', 'Joni Mitchell', True),
    ('Simon and Garfunkel', 'Simon & Garfunkel', False),     # 'and' is a word of ours
    ('Simon & Garfunkel', 'Simon & Garfunkel', True),
    ('Nirvana', 'Nirvana (2)', True),                         # Discogs' numbering
    ('Joni Mitchell', 'Mitchell Brothers', False),
])
def test_same_artist(ours, theirs, same):
    assert media_covers.same_artist(ours, theirs) is same


def add_item(db, owner, media_type, title, author='', barcode=None, fmt=None, year=None):
    cur = db.execute('INSERT INTO books (title, author, barcode, format, publish_year, media_type, added_by) '
                     'VALUES (?, ?, ?, ?, ?, ?, ?)', (title, author, barcode, fmt, year, media_type, owner))
    db.commit()
    return cur.lastrowid


@pytest.fixture
def saved(monkeypatch):
    """save_best_cover 'downloads' the first candidate; the list records them."""
    import utils.book_utils as bu
    tried = []

    def save(urls):
        urls = list(urls)
        tried.append(urls)
        return f'uploads/saved-{len(tried)}.jpg' if urls else None
    monkeypatch.setattr(bu, 'save_best_cover', save)
    return tried


def run_job(app, client):
    from utils import cover_jobs
    client.post('/covers/start', data={'scope': 'own'}, headers={'X-Requested-With': 'XMLHttpRequest'})
    with app.app_context():
        cover_jobs.run_pending(worker='test', pause=0)


def cover(db, item_id):
    return scalar(db, 'SELECT cover_image_url FROM books WHERE id = ?', item_id)


# ------------------------------------------------------------ which items qualify

def test_what_the_job_counts(db, people, monkeypatch):
    from utils.book_utils import missing_cover_sql
    alice = people['alice']
    add_item(db, alice, 'video', 'Jaws')                               # no barcode: TMDb only
    add_item(db, alice, 'video', 'Alien', barcode='0012345678905')
    add_item(db, alice, 'record', 'Blue')                              # no barcode, no artist
    add_item(db, alice, 'record', 'Court and Spark', 'Joni Mitchell')
    count = lambda: scalar(db, 'SELECT COUNT(*) ' + missing_cover_sql())
    assert count() == 2
    monkeypatch.setenv('TMDB_API_KEY', 'k')
    assert count() == 3


# ------------------------------------------------------------ movies

def test_movie_poster_kept_only_for_the_same_title(app, client, db, people, saved, monkeypatch):
    monkeypatch.setenv('TMDB_API_KEY', 'k')
    films = {'Jaws': {'title': 'Jaws 2', 'poster': 'https://img/jaws2.jpg'},
             'Alien': {'title': 'Alien', 'poster': 'https://img/alien.jpg'}}
    asked = []
    monkeypatch.setattr(media_lookup, 'tmdb_movie', lambda t, y=None: asked.append((t, y)) or films.get(t))
    jaws = add_item(db, people['alice'], 'video', 'Jaws')
    alien = add_item(db, people['alice'], 'video', 'Alien', year=1979)
    login(client, 'alice')
    run_job(app, client)
    assert cover(db, jaws) is None                     # TMDb's best was another film
    assert cover(db, alien) == 'uploads/saved-1.jpg'
    assert saved == [['https://img/alien.jpg']] and ('Alien', 1979) in asked


def test_movie_barcode_photos_come_first(app, client, db, people, saved, monkeypatch):
    monkeypatch.setattr(media_lookup, 'upcitemdb',
                        lambda code: {'title': 'JAWS VHS', 'images': ['https://upc/sleeve.jpg']})
    tape = add_item(db, people['alice'], 'video', 'Jaws', barcode='0012345678905')
    login(client, 'alice')
    run_job(app, client)
    assert saved == [['https://upc/sleeve.jpg']] and cover(db, tape) == 'uploads/saved-1.jpg'


# ------------------------------------------------------------ albums

def test_album_by_barcode_needs_no_title_check(app, client, db, people, saved, monkeypatch):
    monkeypatch.setattr(music_lookup, 'barcode_search', lambda ean: ['mbid-1'])
    monkeypatch.setattr(music_lookup, 'release_details',
                        lambda mbid: ({'title': 'Something else'}, [f'https://caa/{mbid}.jpg']))
    rec = add_item(db, people['alice'], 'record', 'Blue', barcode='0012345678905')
    login(client, 'alice')
    run_job(app, client)
    assert saved == [['https://caa/mbid-1.jpg']] and cover(db, rec)


def test_album_by_text_needs_title_and_artist(app, client, db, people, saved, monkeypatch):
    rows = [{'id': 'wrong-artist', 'title': 'Blue', 'artist': 'Weezer'},
            {'id': 'right', 'title': 'Blue', 'artist': 'Joni Mitchell'}]
    searched = []
    monkeypatch.setattr(music_lookup, 'search', lambda q, kind='': searched.append((q, kind)) or rows)
    monkeypatch.setattr(music_lookup, 'release_details', lambda mbid: ({}, [f'https://caa/{mbid}.jpg']))
    rec = add_item(db, people['alice'], 'record', 'Blue', 'Joni Mitchell', fmt='CD')
    other = add_item(db, people['alice'], 'record', 'Hejira', 'Joni Mitchell')
    login(client, 'alice')
    run_job(app, client)
    assert cover(db, rec) and cover(db, other) is None
    assert saved == [['https://caa/right.jpg']]
    assert ('Joni Mitchell Blue', 'cd') in searched and ('Joni Mitchell Hejira', 'vinyl') in searched


def test_discogs_first_and_musicbrainz_when_busy(app, client, db, people, saved, monkeypatch):
    monkeypatch.setenv('DISCOGS_TOKEN', 't')

    def busy(*a, **k):
        raise discogs_lookup.Busy()
    monkeypatch.setattr(discogs_lookup, 'search', busy)
    monkeypatch.setattr(music_lookup, 'search',
                        lambda q, kind='': [{'id': 'mb', 'title': 'Blue', 'artist': 'Joni Mitchell'}])
    monkeypatch.setattr(music_lookup, 'release_details', lambda mbid: ({}, ['https://caa/mb.jpg']))
    rec = add_item(db, people['alice'], 'record', 'Blue', 'Joni Mitchell')
    login(client, 'alice')
    run_job(app, client)
    assert saved == [['https://caa/mb.jpg']] and cover(db, rec)


def test_a_failing_source_counts_as_not_found(app, client, db, people, saved, monkeypatch):
    def boom(*a, **k):
        raise music_lookup.Busy()
    monkeypatch.setattr(music_lookup, 'search', boom)
    rec = add_item(db, people['alice'], 'record', 'Blue', 'Joni Mitchell')
    add_book(db, people['alice'])                                    # no ISBN: not in the job
    login(client, 'alice')
    run_job(app, client)
    assert cover(db, rec) is None and saved == []
    job = client.get('/covers/status').get_json()['job']
    assert (job['status'], job['checked'], job['found']) == ('done', 1, 0)


# ------------------------------------------------------------ "Find a better cover"

def run_steps(steps):
    return [(label, run()) for label, run in steps]


def test_find_a_better_cover_movie_steps(app, monkeypatch):
    monkeypatch.setenv('TMDB_API_KEY', 'k')
    monkeypatch.setattr(media_lookup, 'upcitemdb', lambda code: {'images': ['https://upc/a.jpg']})
    films = [{'title': 'Jaws 2', 'year': 1978, 'poster': media_lookup.TMDB_THUMBS + '/j2.jpg'},
             {'title': 'Jaws', 'year': 1975, 'poster': media_lookup.TMDB_THUMBS + '/j.jpg'}]
    monkeypatch.setattr(media_lookup, 'tmdb_search', lambda q, year=None, limit=8: films)
    with app.app_context():
        got = run_steps(media_covers.cover_search_steps('video', title='Jaws', barcode='0012345678905'))
    assert got == [('UPCitemdb', [('https://upc/a.jpg', 'UPCitemdb (barcode)')]),
                   ('TMDb', [(media_lookup.TMDB_IMAGES + '/j.jpg', 'TMDb: Jaws (1975)'),      # exact first
                             (media_lookup.TMDB_IMAGES + '/j2.jpg', 'TMDb: Jaws 2 (1978)')])]


def test_find_a_better_cover_album_steps(app, monkeypatch):
    """Without a Discogs token: MusicBrainz only, the pressing's cover and
    its album's, exact matches first."""
    rows = [{'id': 'w', 'title': 'Blue', 'artist': 'Weezer', 'format_label': 'CD', 'country': 'US', 'year': 1994,
             'thumb': 'https://caa/release-group/g1/front-250'},
            {'id': 'j', 'title': 'Blue', 'artist': 'Joni Mitchell', 'format_label': 'LP', 'country': 'US',
             'year': 1971, 'thumb': 'https://caa/release-group/g2/front-250'}]
    searched = []
    monkeypatch.setattr(music_lookup, 'search', lambda q, kind='': searched.append((q, kind)) or rows)
    with app.app_context():
        steps = media_covers.cover_search_steps('record', title='Blue', author='Joni Mitchell')
        got = run_steps(steps)
    assert [label for label, _ in got] == ['MusicBrainz'] and searched == [('Joni Mitchell Blue', '')]
    urls = got[0][1]
    assert urls[0] == (music_lookup.cover_urls('j')[0], 'MusicBrainz: LP, US, 1971')
    assert urls[1] == ('https://caa/release-group/g2/front-500', 'MusicBrainz: LP, US, 1971 (album)')
    assert urls[2][1] == 'MusicBrainz: CD, US, 1994'
