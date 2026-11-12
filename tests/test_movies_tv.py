"""Movies & TV (ROADMAP 15.1): a video is a movie or TV.

A TV box set is a video row like a film (same formats, statuses and shelf)
with books.video_kind = 'tv' and an optional free-text season; NULL is a
movie (migration 034, media.video_kind). The migration itself is tested in
test_migrations.py.

people: alice (admin) + bob share a household; carol is alice's friend.
"""
import csv
import io

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
    assert 'Edit TV Show</h1>' in edit and '>Creator</label>' in edit


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
