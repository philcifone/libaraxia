"""Manual reading progress (ROADMAP 16.0f, docs/PROGRESS-MERGE-SPEC.md part A):
utils/reading_progress.py and POST /read/<book_id>/progress.

People (conftest): alice (admin) and bob share a household; carol is
alice's friend. alice is an admin, so access checks use bob.
"""
from datetime import date

import pytest

from conftest import add_book, add_user, fk_violations, login, scalar
from utils import reading_progress
from utils.reading_progress import ProgressError

TODAY = date.today().isoformat()


def book_with(db, owner, title='Dune', page_count=None, fmt=None, media_type='book'):
    book_id = add_book(db, owner, title)
    db.execute('UPDATE books SET page_count = ?, format = ?, media_type = ? WHERE id = ?',
               (page_count, fmt, media_type, book_id))
    db.commit()
    return book_id


def sessions(db, user_id, book_id):
    return [tuple(r) for r in db.execute(
        'SELECT date_started, date_completed, progress, progress_page FROM reading_sessions '
        'WHERE user_id = ? AND book_id = ? ORDER BY session_id', (user_id, book_id))]


def status(db, user_id, book_id):
    row = db.execute('SELECT status, quiet FROM collections WHERE user_id = ? AND book_id = ?',
                     (user_id, book_id)).fetchone()
    return tuple(row) if row else None


def test_a_page_is_stored_with_its_percent(db, people):
    dune = book_with(db, people['alice'], page_count=400)
    done = reading_progress.set_progress(db, people['alice'], dune, page='100')
    db.commit()
    assert done == {'progress': 0.25, 'page': 100, 'opened': True, 'status_set': True}
    assert sessions(db, people['alice'], dune) == [(TODAY, None, 0.25, 100)]
    # Setting progress by hand is announced, as the status chip is
    assert status(db, people['alice'], dune) == ('currently reading', 0)
    assert scalar(db, 'SELECT progress_at IS NOT NULL FROM reading_sessions') == 1


def test_without_a_page_count_it_takes_a_percent(db, people):
    dune = book_with(db, people['alice'])
    with pytest.raises(ProgressError, match='no page count'):
        reading_progress.set_progress(db, people['alice'], dune, page='10')
    reading_progress.set_progress(db, people['alice'], dune, percent='40')
    assert sessions(db, people['alice'], dune) == [(TODAY, None, 0.4, None)]


def test_ebooks_and_audiobooks_take_a_percent_even_with_a_page_count(db, people):
    for fmt in ('Ebook', 'Audiobook'):
        item = book_with(db, people['alice'], title=fmt, page_count=300, fmt=fmt)
        with pytest.raises(ProgressError):
            reading_progress.set_progress(db, people['alice'], item, page='10')
        assert reading_progress.set_progress(db, people['alice'], item, percent='12.5')['progress'] == 0.125


def test_a_page_past_the_end_counts_as_finished_reading_but_keeps_the_page(db, people):
    dune = book_with(db, people['alice'], page_count=400)
    reading_progress.set_progress(db, people['alice'], dune, page='412')
    assert sessions(db, people['alice'], dune) == [(TODAY, None, 1.0, 412)]


@pytest.mark.parametrize('page, percent, message', [
    ('-3', None, '0 or more'),
    ('abc', None, 'as a number'),
    ('12.5', None, 'whole page'),
    ('nan', None, '0 or more'),
    (None, '101', 'up to 100'),
    (None, None, 'page you are on'),
])
def test_junk_is_refused_and_nothing_is_written(db, people, page, percent, message):
    dune = book_with(db, people['alice'], page_count=400)
    with pytest.raises(ProgressError, match=message):
        reading_progress.set_progress(db, people['alice'], dune, page=page, percent=percent)
    assert sessions(db, people['alice'], dune) == []
    assert status(db, people['alice'], dune) is None


def test_progress_goes_on_the_open_session_never_a_finished_or_undated_one(db, people):
    dune = book_with(db, people['alice'], page_count=400)
    db.executemany('INSERT INTO reading_sessions (user_id, book_id, date_started, date_completed) VALUES (?, ?, ?, ?)',
                   [(people['alice'], dune, '2020-01-01', '2020-02-01'),     # finished
                    (people['alice'], dune, None, None),                     # undated, read long ago
                    (people['alice'], dune, '2026-11-01', None)])            # open
    db.execute("INSERT INTO collections (user_id, book_id, status, quiet) VALUES (?, ?, 'currently reading', 1)",
               (people['alice'], dune))
    done = reading_progress.set_progress(db, people['alice'], dune, page='200')
    assert (done['opened'], done['status_set']) == (False, False)
    assert sessions(db, people['alice'], dune) == [
        ('2020-01-01', '2020-02-01', None, None),
        (None, None, None, None),
        ('2026-11-01', None, 0.5, 200)]
    assert status(db, people['alice'], dune) == ('currently reading', 1)    # untouched


def test_a_reread_starts_again_at_zero(db, people):
    dune = book_with(db, people['alice'], page_count=400)
    reading_progress.set_progress(db, people['alice'], dune, page='400')
    db.execute('UPDATE reading_sessions SET date_completed = ?', (TODAY,))
    db.execute("UPDATE collections SET status = 'read'")
    # Reading it again: a new session, and the status back to Currently Reading
    done = reading_progress.set_progress(db, people['alice'], dune, page='20')
    assert (done['opened'], done['status_set']) == (True, True)
    assert sessions(db, people['alice'], dune) == [(TODAY, TODAY, 1.0, 400), (TODAY, None, 0.05, 20)]
    assert status(db, people['alice'], dune) == ('currently reading', 0)


def test_movies_and_music_have_no_progress(db, people):
    for kind in ('video', 'record'):
        item = book_with(db, people['alice'], title=kind, media_type=kind)
        with pytest.raises(ProgressError, match='books only'):
            reading_progress.set_progress(db, people['alice'], item, percent='50')


def test_rings_are_yours_and_from_the_latest_open_session(db, people):
    dune = book_with(db, people['alice'], page_count=400)
    emma = book_with(db, people['alice'], title='Emma', page_count=100)
    reading_progress.set_progress(db, people['alice'], dune, page='100')
    reading_progress.set_progress(db, people['bob'], emma, page='50')      # bob's, on alice's book
    reading_progress.set_progress(db, people['alice'], emma, page='0')     # 0: no ring
    db.commit()
    alice = reading_progress.rings(db, people['alice'])
    assert set(alice) == {dune} and alice[dune][0] == 0.25 and alice[dune][1]
    assert set(reading_progress.rings(db, people['bob'])) == {emma}
    assert reading_progress.rings(db, people['carol']) == {}


def test_the_route_saves_and_lands_on_the_reading_history(client, db, people):
    dune = book_with(db, people['bob'], page_count=400)
    login(client, 'bob')
    r = client.post(f'/read/{dune}/progress', data={'page': '100'})
    assert r.status_code == 302 and r.headers['Location'].endswith(f'/books/book/{dune}#item-history')
    assert sessions(db, people['bob'], dune) == [(TODAY, None, 0.25, 100)]
    # A refusal flashes and writes nothing
    r = client.post(f'/read/{dune}/progress', data={'page': 'lots'})
    assert r.status_code == 302
    assert sessions(db, people['bob'], dune) == [(TODAY, None, 0.25, 100)]
    assert fk_violations(db) == []


def test_the_route_is_a_404_on_a_book_you_cannot_see(client, db, people):
    erin = add_user(db, 'erin')
    hers = book_with(db, erin, page_count=400)
    login(client, 'bob')
    assert client.post(f'/read/{hers}/progress', data={'page': '1'}).status_code == 404
    assert sessions(db, people['bob'], hers) == []
