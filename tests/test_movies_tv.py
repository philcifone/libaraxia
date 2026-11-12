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
