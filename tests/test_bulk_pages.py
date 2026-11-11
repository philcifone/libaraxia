"""ROADMAP 14a step 6: bulk edit on every grid you can edit from, never on a
friend's, and Profile -> Recent bulk edits."""
from datetime import datetime

import pytest

from conftest import add_book, login
from utils import bulk

SELECT = 'id="bulk-select-btn"'


@pytest.fixture
def shelves(db, people):
    """One book, movie and album for alice; a status and a custom collection of each kind."""
    alice = people['alice']
    book = add_book(db, alice, title='Dune')
    movie = add_book(db, alice, title='Alien')
    album = add_book(db, alice, title='Blue')
    db.execute("UPDATE books SET media_type = 'video', format = 'DVD' WHERE id = ?", (movie,))
    db.execute("UPDATE books SET media_type = 'record', format = 'LP' WHERE id = ?", (album,))
    db.execute("INSERT INTO collections (user_id, book_id, status) VALUES (?, ?, 'read')", (alice, book))
    jazz = db.execute("INSERT INTO user_collections (user_id, name, media_type) VALUES (?, 'Jazz', 'book')",
                      (alice,)).lastrowid
    db.execute('INSERT INTO collection_books (collection_id, book_id) VALUES (?, ?)', (jazz, book))
    db.commit()
    return {'book': book, 'movie': movie, 'album': album, 'jazz': jazz}


@pytest.mark.parametrize('url', ['/base/index', '/base/shared-library', '/videos/', '/videos/shared',
                                 '/records/', '/records/shared', '/books/search?search_term=Dune',
                                 '/collections/collections/status/read'])
def test_select_is_on_the_grids_you_can_edit_from(client, people, shelves, url):
    login(client, 'alice')
    html = client.get(url).get_data(as_text=True)
    assert SELECT in html and 'id="bulk-sheet"' in html and 'bulk.js' in html, url
    assert 'data-bulkable' in html


def test_select_is_on_a_custom_collection(client, people, shelves):
    login(client, 'alice')
    html = client.get(f'/collections/collections/{shelves["jazz"]}/view').get_data(as_text=True)
    assert SELECT in html and 'data-bulkable' in html


@pytest.mark.parametrize('url', ['/base/library/alice', '/videos/user/alice', '/records/user/alice',
                                 '/collections/collections/status/read?username=alice'])
def test_no_select_on_a_friends_grids(client, people, shelves, url):
    """carol is alice's friend: she sees the grids, read-only."""
    login(client, 'carol')
    r = client.get(url)
    assert r.status_code == 200, url
    html = r.get_data(as_text=True)
    assert SELECT not in html and 'bulk.js' not in html and 'data-bulkable' not in html, url


def test_no_select_on_an_empty_grid(client, people):
    login(client, 'carol')
    assert SELECT not in client.get('/videos/').get_data(as_text=True)


def test_selection_carries_the_section_type(client, people, shelves):
    """bulk.js reads the type for its pickers from the grid's data-media."""
    login(client, 'alice')
    assert 'data-media="video"' in client.get('/videos/').get_data(as_text=True)
    assert 'data-media="record"' in client.get('/records/shared').get_data(as_text=True)


def test_profile_lists_recent_bulk_edits_with_undo(client, db, people, shelves):
    login(client, 'alice')
    ids = [shelves['book']]
    fp = client.post('/bulk/plan', json={'action': 'genre', 'params': {'genre': 'SF'}, 'ids': ids}
                     ).get_json()['plan']['fingerprint']
    edit_id = client.post('/bulk/apply', json={'action': 'genre', 'params': {'genre': 'SF'}, 'ids': ids,
                                               'fingerprint': fp}).get_json()['edit_id']
    client.get('/base/index')                       # the banner takes the result out of the session
    html = client.get('/user/alice').get_data(as_text=True)
    assert 'Recent bulk edits' in html and 'Genre set to SF on 1 item' in html
    assert f'data-edit-id="{edit_id}"' in html and 'just now' in html

    # Undo from the profile: no banner left waiting for the next grid
    r = client.post(f'/bulk/{edit_id}/undo', json={'banner': False})
    assert r.status_code == 200 and r.get_json()['restored'] == 1
    assert 'data-bulk-banner' not in client.get('/base/index').get_data(as_text=True)
    html = client.get('/user/alice').get_data(as_text=True)
    assert f'data-edit-id="{edit_id}"' not in html and 'Undone' in html


def test_recent_bulk_edits_are_yours_alone(client, db, people, shelves):
    db.execute("INSERT INTO bulk_edits (user_id, action, params, summary, item_count) "
               "VALUES (?, 'genre', '{}', 'Alice did this', 1)", (people['alice'],))
    db.commit()
    login(client, 'carol')
    assert 'Alice did this' not in client.get('/user/alice').get_data(as_text=True)
    assert 'Recent bulk edits' not in client.get('/user/carol').get_data(as_text=True)


def test_ago():
    now = datetime(2026, 11, 10, 12, 0, 0)
    assert bulk.ago('2026-11-10 11:59:30', now) == 'just now'
    assert bulk.ago('2026-11-10 11:59:00', now) == '1 minute ago'
    assert bulk.ago('2026-11-10 09:00:00', now) == '3 hours ago'
    assert bulk.ago('2026-11-08 12:00:00', now) == '2 days ago'
    assert bulk.ago('nonsense', now) == ''


def test_an_edit_with_nothing_left_to_undo_offers_no_undo(client, db, people, shelves):
    """Undo leaves alone what changed since; when that's everything, Profile
    says "Changed since" instead of an Undo that would restore nothing."""
    login(client, 'alice')
    book = shelves['book']
    fp = client.post('/bulk/plan', json={'action': 'genre', 'params': {'genre': 'SF'}, 'ids': [book]}
                     ).get_json()['plan']['fingerprint']
    edit_id = client.post('/bulk/apply', json={'action': 'genre', 'params': {'genre': 'SF'}, 'ids': [book],
                                               'fingerprint': fp}).get_json()['edit_id']
    conn_edit = db.execute('SELECT * FROM bulk_edits WHERE id = ?', (edit_id,)).fetchone()
    assert bulk.undoable(db, bulk_user(people['alice']), conn_edit) == 1
    assert f'data-edit-id="{edit_id}"' in client.get('/user/alice').get_data(as_text=True)

    db.execute("UPDATE books SET genre = 'Fantasy' WHERE id = ?", (book,))      # changed by hand since
    db.commit()
    html = client.get('/user/alice').get_data(as_text=True)
    assert f'data-edit-id="{edit_id}"' not in html and 'Changed since' in html


def bulk_user(user_id):
    class Who:
        id, is_admin = user_id, True
    return Who()


def test_warning_flashes_are_their_own_colour(client, people):
    """Yellow "done, but", not the red of an error (Phil, 2026-11-11)."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parent.parent
    assert "category == 'warning' %}flash-warning" in (root / 'templates' / '_flash_messages.html').read_text()
    assert "if (category === 'warning') return 'flash-warning';" in (root / 'static' / 'common.js').read_text()
    assert '.flash-warning' in (root / 'static' / 'styles.css').read_text()


def test_grid_covers_carry_the_author_for_the_missing_file_fallback(client, db, people):
    """A cover whose file is gone turns into the title binding (common.js),
    which needs the author as well as the alt text."""
    from conftest import add_book as put
    put(db, people['alice'], title='Gone', author='Nobody', cover='uploads/no_such_file.jpg')
    login(client, 'alice')
    assert 'alt="Gone" data-author="Nobody"' in client.get('/base/index').get_data(as_text=True)
