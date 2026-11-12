"""Personal library backups (utils/personal_backups.py, Profile): a user's
own data only, and a restore never touches anyone else's. Also the library
CSV's sections (utils/export.py)."""
import csv
import io
import os

import pytest

from conftest import add_book, add_review, login, scalar


@pytest.fixture
def pb(app, db_path):
    from utils import personal_backups
    with app.app_context():
        yield personal_backups


@pytest.fixture
def conn(app, db_path):
    with app.app_context():
        from utils.database import get_db
        yield get_db()


def session_count(db, user, book):
    return scalar(db, 'SELECT COUNT(*) FROM reading_sessions WHERE user_id = ? AND book_id = ?', user, book)


def test_backup_holds_only_your_rows(pb, conn, db, people):
    alice, bob = people['alice'], people['bob']
    mine = add_book(db, bob, 'Bobs book')
    add_review(db, bob, mine)
    theirs = add_book(db, alice, 'Alices book')
    add_review(db, alice, theirs)              # alice's data: not in bob's backup
    add_review(db, bob, theirs, comment='Bob on alice')

    made = pb.create(conn, bob, 'bob')
    data = pb._load(bob, made['name'])
    t = data['tables']
    assert [r[t['books']['columns'].index('title')] for r in t['books']['rows']] == ['Bobs book']
    users = {r[t['read_data']['columns'].index('user_id')] for r in t['read_data']['rows']}
    assert users == {bob} and len(t['read_data']['rows']) == 2
    assert made['counts']['books'] == 1 and made['counts']['reviews'] == 2
    assert 'users' not in t and 'friendships' not in t      # never the account or the social graph


def test_restore_puts_your_library_back_and_leaves_others_alone(pb, conn, db, people):
    alice, bob = people['alice'], people['bob']
    kept = add_book(db, bob, 'Kept')
    add_review(db, bob, kept, rating=4)
    on_alices = add_book(db, alice, 'Alices book')
    add_review(db, alice, on_alices, comment='Alice wrote this')
    made = pb.create(conn, bob, 'bob')

    # After the backup: bob changes, deletes and adds; alice adds a review
    db.execute('UPDATE read_data SET rating = 1 WHERE user_id = ? AND book_id = ?', (bob, kept))
    db.execute("UPDATE books SET title = 'Renamed' WHERE id = ?", (kept,))
    added = add_book(db, bob, 'Added since')
    db.execute('INSERT INTO reading_sessions (user_id, book_id) VALUES (?, ?)', (bob, on_alices))
    later_alice = add_book(db, alice, 'Alice later')
    add_review(db, alice, later_alice)
    db.commit()

    r = pb.restore(conn, bob, 'bob', made['name'])

    assert scalar(db, 'SELECT title FROM books WHERE id = ?', kept) == 'Kept'
    assert scalar(db, 'SELECT rating FROM read_data WHERE user_id = ? AND book_id = ?', bob, kept) == 4
    assert scalar(db, 'SELECT COUNT(*) FROM books WHERE id = ?', added) == 0
    assert session_count(db, bob, on_alices) == 0
    assert r['books_removed'] == 1
    # Alice's books and data are as she left them
    assert scalar(db, 'SELECT comment FROM read_data WHERE user_id = ? AND book_id = ?', alice, on_alices) == 'Alice wrote this'
    assert scalar(db, 'SELECT COUNT(*) FROM read_data WHERE user_id = ? AND book_id = ?', alice, later_alice) == 1
    # And bob's library as it was before the restore is a backup of its own
    assert r['safety']['kind'] == 'before_restore'
    assert pb.latest(bob)['name'] == r['safety']['name']


def test_restore_brings_back_deleted_items_with_their_ids(pb, conn, db, people):
    bob = people['bob']
    gone = add_book(db, bob, 'Deleted by mistake')
    add_review(db, bob, gone)
    db.execute('INSERT INTO reading_sessions (user_id, book_id, date_completed) VALUES (?, ?, ?)',
               (bob, gone, '2020-01-01'))
    db.commit()
    made = pb.create(conn, bob, 'bob')
    db.execute('DELETE FROM books WHERE id = ?', (gone,))
    db.commit()

    r = pb.restore(conn, bob, 'bob', made['name'])
    assert r['books_back'] == 1
    assert scalar(db, 'SELECT title FROM books WHERE id = ?', gone) == 'Deleted by mistake'
    assert session_count(db, bob, gone) == 2     # add_review's and the one added here


def test_items_others_have_data_on_are_kept(pb, conn, db, people):
    alice, bob = people['alice'], people['bob']
    made = pb.create(conn, bob, 'bob')
    added = add_book(db, bob, 'Alice reviewed it')
    add_review(db, alice, added)

    r = pb.restore(conn, bob, 'bob', made['name'])
    assert scalar(db, 'SELECT COUNT(*) FROM books WHERE id = ?', added) == 1
    assert r['kept'] == [('Alice reviewed it', ['alice'])]


def test_items_given_away_stay_with_their_new_owner(pb, conn, db, people):
    alice, bob = people['alice'], people['bob']
    given = add_book(db, bob, 'Given to alice')
    made = pb.create(conn, bob, 'bob')
    db.execute('UPDATE books SET added_by = ? WHERE id = ?', (alice, given))
    db.commit()

    r = pb.restore(conn, bob, 'bob', made['name'])
    assert scalar(db, 'SELECT added_by FROM books WHERE id = ?', given) == alice
    assert r['given_away'] == ['Given to alice']


def test_data_on_a_book_that_is_gone_is_skipped(pb, conn, db, people):
    alice, bob = people['alice'], people['bob']
    hers = add_book(db, alice, 'Alice deletes it')
    add_review(db, bob, hers)
    made = pb.create(conn, bob, 'bob')
    db.execute('DELETE FROM books WHERE id = ?', (hers,))
    db.commit()

    r = pb.restore(conn, bob, 'bob', made['name'])
    assert r['skipped'] == 3                     # the review, the status and the session
    assert scalar(db, 'SELECT COUNT(*) FROM books WHERE id = ?', hers) == 0


def test_restore_undoes_a_goodreads_import(client, db, people):
    """The import's own backup puts the library back, provenance included."""
    from test_goodreads import run, row
    from utils import personal_backups as pb
    bob = people['bob']
    run(client, 'bob', row('Dune'), row('Emma'))
    assert scalar(db, 'SELECT COUNT(*) FROM goodreads_imports WHERE user_id = ?', bob) == 1
    auto = pb.latest(bob)
    assert auto['kind'] == 'goodreads' and auto['counts']['books'] == 0

    client.post(f'/user/backups/{auto["name"]}/restore')
    assert scalar(db, 'SELECT COUNT(*) FROM books WHERE added_by = ?', bob) == 0
    assert scalar(db, 'SELECT COUNT(*) FROM goodreads_imports WHERE user_id = ?', bob) == 0
    assert scalar(db, 'SELECT COUNT(*) FROM bulk_edits WHERE user_id = ?', bob) == 0


def test_covers_come_back(pb, conn, db, people, static_root):
    bob = people['bob']
    (static_root / 'uploads').mkdir()
    (static_root / 'uploads' / 'cover_b.jpg').write_bytes(b'cover')
    add_book(db, bob, 'With a cover', cover='uploads/cover_b.jpg')
    made = pb.create(conn, bob, 'bob')
    assert made['files'] == 1
    os.remove(static_root / 'uploads' / 'cover_b.jpg')

    r = pb.restore(conn, bob, 'bob', made['name'])
    assert r['files'] == 1 and (static_root / 'uploads' / 'cover_b.jpg').read_bytes() == b'cover'


def test_manual_limit_and_automatic_pruning(pb, conn, db, people):
    bob = people['bob']
    for _ in range(pb.MAX_MANUAL):
        pb.create(conn, bob, 'bob')
    with pytest.raises(pb.PersonalBackupError, match='Delete one'):
        pb.create(conn, bob, 'bob')
    for _ in range(pb.KEEP_AUTOMATIC + 2):
        pb.create(conn, bob, 'bob', 'goodreads')
    kinds = [b['kind'] for b in pb.list_backups(bob)]
    assert kinds.count('goodreads') == pb.KEEP_AUTOMATIC and kinds.count('manual') == pb.MAX_MANUAL


def test_backups_are_per_user(client, db, people):
    """bob can't restore or delete alice's backup, even knowing its name."""
    from utils import personal_backups as pb
    login(client, 'alice')
    client.post('/user/backups/create')
    name = pb.latest(people['alice'])['name']
    add_book(db, people['alice'], 'Alice adds later')

    login(client, 'bob')
    r = client.post(f'/user/backups/{name}/restore', follow_redirects=True)
    assert b'No such backup' in r.data
    client.post(f'/user/backups/{name}/delete')
    assert pb.latest(people['alice'])['name'] == name
    assert scalar(db, "SELECT COUNT(*) FROM books WHERE title = 'Alice adds later'") == 1
    for bad in ('..', '../1/' + name, 'x'):
        with pytest.raises(pb.PersonalBackupError):
            pb.folder(people['bob'], bad)


def test_profile_lists_backups_and_routes_work(client, db, people):
    from utils import personal_backups as pb
    login(client, 'bob')
    page = client.get('/user/bob').get_data(as_text=True)
    assert 'Library backups' in page and 'No backups yet' in page
    r = client.post('/user/backups/create', follow_redirects=True)
    assert b'Library backed up' in r.data and b'Restore' in r.data
    name = pb.latest(people['bob'])['name']
    r = client.post(f'/user/backups/{name}/restore', follow_redirects=True)
    assert b'Your library is back to' in r.data
    client.post(f'/user/backups/{name}/delete')
    assert name not in [b['name'] for b in pb.list_backups(people['bob'])]
    # Not on someone else's profile
    assert 'Library backups' not in client.get('/user/alice').get_data(as_text=True)


def test_goodreads_page_offers_a_library_backup(client, db, people):
    login(client, 'bob')
    page = client.get('/user/import_goodreads_page').get_data(as_text=True)
    assert 'Back up my library' in page and 'no backups yet' in page
    r = client.post('/user/backups/create', data={'back': 'goodreads'})
    assert r.headers['Location'].endswith('/user/import_goodreads_page')
    assert 'Your last backup' in client.get('/user/import_goodreads_page').get_data(as_text=True)


def test_goodreads_import_refuses_without_a_backup(client, db, people, monkeypatch):
    from test_goodreads import upload, fingerprint, csv_text, row
    from utils import personal_backups as pb

    def broken(*a, **kw):
        raise pb.PersonalBackupError('disk full')
    monkeypatch.setattr(pb, 'create', broken)
    login(client, 'bob')
    upload(client, csv_text(row('Dune')))
    r = client.post('/user/import_goodreads/apply', json={'fingerprint': fingerprint(client)})
    assert r.status_code == 500 and 'nothing was imported' in r.get_json()['error']
    assert scalar(db, "SELECT COUNT(*) FROM books WHERE title = 'Dune'") == 0


# --- the library CSV: yours, shared, others' -----------------------------------

def test_library_csv_sections(client, db, people):
    alice, bob, carol = people['alice'], people['bob'], people['carol']
    add_book(db, bob, 'Bobs book')
    shared = add_book(db, alice, 'Alices shelf book')
    add_review(db, alice, shared, comment='Alice private review')
    gone = add_book(db, alice, 'Alice gave it away')
    db.execute("UPDATE books SET removed_at = CURRENT_TIMESTAMP WHERE id = ?", (gone,))
    unowned = add_book(db, alice, 'Alice read, never owned')
    db.execute('UPDATE books SET owned = 0 WHERE id = ?', (unowned,))
    wish = add_book(db, alice, 'Alice wishes')
    db.execute('INSERT INTO wishlist (user_id, book_id) VALUES (?, ?)', (alice, wish))
    friends = add_book(db, carol, 'Carols, bob reviewed')
    add_review(db, bob, friends)
    add_book(db, carol, 'Carols, untouched')
    db.commit()

    login(client, 'bob')
    rows = list(csv.DictReader(io.StringIO(client.get('/user/export_library').get_data(as_text=True))))
    got = [(r['Section'], r['Title']) for r in rows]
    assert got == [('Yours', 'Bobs book'),
                   ('Shared (alice)', 'Alices shelf book'),
                   ("Your data on others' items", 'Carols, bob reviewed')]
    shared_row = rows[1]
    assert shared_row['Review'] == '' and shared_row['Owner'] == 'alice'   # never alice's review
    assert shared_row['You Own It'] == 'no'
