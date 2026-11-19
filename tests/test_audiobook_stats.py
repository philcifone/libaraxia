"""The Books tab's Audiobooks block and the overview's hours listened
(ROADMAP 16.0e step 1b, docs/AUDIOBOOKSHELF-SPEC.md section 7)."""
from datetime import datetime

from tests.conftest import add_book, login

TODAY = datetime(2026, 11, 18)


def audiobook(db, owner, title, minutes, status, finished=None):
    book = add_book(db, owner, title=title)
    db.execute("UPDATE books SET format = 'Audiobook', owned = 0, runtime_minutes = ?, page_count = 500"
               " WHERE id = ?", (minutes, book))
    db.execute('INSERT INTO collections (user_id, book_id, status) VALUES (?, ?, ?)', (owner, book, status))
    if finished:
        db.execute('INSERT INTO reading_sessions (user_id, book_id, date_completed) VALUES (?, ?, ?)',
                   (owner, book, finished))
    db.commit()
    return book


def test_audiobook_block(app, db, people):
    from utils.stats import audiobook_stats, type_stats
    alice = people['alice']
    assert audiobook_stats(db, alice, TODAY) is None              # none yet: no block
    audiobook(db, alice, 'Hail Mary', 970, 'read', '2026-03-01')
    audiobook(db, alice, 'Dune', 1260, 'read', '2025-06-01')
    audiobook(db, alice, 'No Length', None, 'read', '2026-04-01')
    audiobook(db, alice, 'Now', 600, 'currently reading')
    audiobook(db, people['bob'], "Bob's", 6000, 'read', '2026-01-01')   # someone else's listening

    a = audiobook_stats(db, alice, TODAY)
    assert (a['done'], a['listening'], a['no_length'], a['done_this_year']) == (3, 1, 1, 2)
    assert (a['hours'], a['hours_this_year']) == (37.2, 16.2)     # (970 + 1260) / 60; 970 / 60
    assert a['longest'] == {'title': 'Dune', 'hours': 21}
    s = type_stats(db, alice, 'book', TODAY)
    assert s['done'] == 3 and s['size_done'] == 0                 # read, but no pages read
    assert s['audio']['hours'] == 37.2


def test_profile_shows_audiobooks_and_hours_listened(client, db, people):
    alice = people['alice']
    audiobook(db, alice, 'Hail Mary', 970, 'read', '2026-03-01')
    audiobook(db, alice, 'No Length', None, 'read', '2026-04-01')
    login(client, 'alice')
    page = client.get('/user/alice').get_data(as_text=True)
    assert 'data-audiobook-stats' in page and 'Hours listened' in page
    assert 'Hours from 1 of 2 (1 has no length).' in page


def test_all_tab_puts_hours_listened_after_pages(app, db, people):
    from utils.stats import all_stats, type_stats
    alice = people['alice']
    audiobook(db, alice, 'Hail Mary', 970, 'read', '2026-03-01')
    printed = add_book(db, alice, 'Print')
    db.execute("UPDATE books SET page_count = 300 WHERE id = ?", (printed,))
    db.execute("INSERT INTO collections (user_id, book_id, status) VALUES (?, ?, 'read')", (alice, printed))
    db.commit()
    a = all_stats(db, alice, {'book': type_stats(db, alice, 'book', TODAY)}, TODAY)
    assert a['time'] == [('book', 300), ('listen', 16.2)]


def test_no_block_without_audiobooks(client, db, people):
    add_book(db, people['alice'], 'Print')
    login(client, 'alice')
    page = client.get('/user/alice').get_data(as_text=True)
    assert 'data-audiobook-stats' not in page and 'hours listened' not in page
