"""Site backups (utils/backups.py, admin pages): back up, restore, prune,
delete, download, and the backup the Goodreads import takes first."""
import json
import os
import sqlite3

import pytest

from conftest import add_book, login, scalar


@pytest.fixture
def uploads(static_root):
    """A static/uploads with one cover and one avatar in it."""
    root = static_root / 'uploads'
    (root / 'avatars').mkdir(parents=True)
    (root / 'cover_a.jpg').write_bytes(b'cover a')
    (root / 'avatars' / 'user_1.jpg').write_bytes(b'avatar')
    (root / 'crop').mkdir()
    (root / 'crop' / 'staged.jpg').write_bytes(b'not a cover yet')
    return root


@pytest.fixture
def backups(app, db_path):
    from utils import backups as module
    with app.app_context():
        yield module


def test_backup_holds_the_database_and_links_the_uploads(backups, db, people, uploads):
    add_book(db, people['alice'], 'Dune', 'Frank Herbert')
    made = backups.create('manual', 'alice')

    folder = backups.folder(made['name'])
    copy = sqlite3.connect(os.path.join(folder, 'library.db'))
    assert copy.execute("SELECT COUNT(*) FROM books WHERE title = 'Dune'").fetchone()[0] == 1
    copy.close()
    # The cover is the same file (a hard link), not a copy
    assert os.path.samefile(uploads / 'cover_a.jpg', os.path.join(folder, 'uploads', 'cover_a.jpg'))
    assert os.path.isfile(os.path.join(folder, 'uploads', 'avatars', 'user_1.jpg'))
    assert not os.path.exists(os.path.join(folder, 'uploads', 'crop'))   # staged crops aren't kept
    assert made['files'] == 2 and made['kind'] == 'manual' and made['by'] == 'alice'
    assert made['counts']['users'] == 3
    assert '032_goodreads_import.sql' in made['migrations']
    # The backup folder sits beside the database, never under static/
    assert os.path.dirname(backups.backup_dir()) == os.path.dirname(str(backups.database_path()))


def test_restore_puts_back_the_data_and_deleted_covers(backups, db, people, uploads):
    alice = people['alice']
    kept = add_book(db, alice, 'Dune', 'Frank Herbert')
    made = backups.create('manual', 'alice')

    later = add_book(db, alice, 'Added later', 'Someone')
    db.execute('DELETE FROM books WHERE id = ?', (kept,))
    db.commit()
    os.remove(uploads / 'cover_a.jpg')            # e.g. an undone import deleted it

    result = backups.restore(made['name'], 'alice')

    assert scalar(db, 'SELECT COUNT(*) FROM books WHERE id = ?', kept) == 1
    assert scalar(db, 'SELECT COUNT(*) FROM books WHERE id = ?', later) == 0
    assert (uploads / 'cover_a.jpg').read_bytes() == b'cover a'
    assert result['files'] == 1 and result['migrated'] == []
    # What was there before the restore is itself a backup, newest in the list
    safety = result['safety']
    assert safety['kind'] == 'before_restore' and backups.latest()['name'] == safety['name']
    copy = sqlite3.connect(os.path.join(backups.folder(safety['name']), 'library.db'))
    assert copy.execute('SELECT COUNT(*) FROM books WHERE id = ?', (later,)).fetchone()[0] == 1
    copy.close()


def test_restore_brings_an_older_backup_up_to_date(backups, db, people):
    made = backups.create('manual')
    copy = sqlite3.connect(os.path.join(backups.folder(made['name']), 'library.db'))
    copy.executescript("""
        DROP TABLE goodreads_rows; DROP TABLE goodreads_imports; DROP TABLE goodreads_staging;
        DELETE FROM schema_migrations WHERE name = '032_goodreads_import.sql';""")
    copy.close()

    result = backups.restore(made['name'])
    assert result['migrated'] == ['032_goodreads_import.sql']
    assert scalar(db, "SELECT COUNT(*) FROM sqlite_master WHERE name = 'goodreads_rows'") == 1


def test_restore_refuses_a_backup_from_newer_code(backups, db, people):
    add_book(db, people['alice'], 'Still here', 'Someone')
    made = backups.create('manual')
    copy = sqlite3.connect(os.path.join(backups.folder(made['name']), 'library.db'))
    copy.execute("INSERT INTO schema_migrations (name) VALUES ('999_from_the_future.sql')")
    copy.commit()
    copy.close()
    add_book(db, people['alice'], 'Added after', 'Someone')

    with pytest.raises(backups.BackupError, match='newer'):
        backups.restore(made['name'])
    assert scalar(db, "SELECT COUNT(*) FROM books WHERE title = 'Added after'") == 1
    assert len(backups.list_backups()) == 1        # and no safety backup was taken


def test_automatic_backups_are_pruned_manual_ones_kept(backups, db, people, monkeypatch):
    manual = backups.create('manual')
    for _ in range(backups.KEEP_AUTOMATIC + 2):
        backups.create('goodreads')
    kinds = [b['kind'] for b in backups.list_backups()]
    assert kinds.count('goodreads') == backups.KEEP_AUTOMATIC
    assert manual['name'] in [b['name'] for b in backups.list_backups()]


def test_names_from_urls_are_checked(backups, db_path):
    for bad in ('../library', '..', '', 'x', '20261112-143005/../../etc'):
        with pytest.raises(backups.BackupError):
            backups.folder(bad)
    with pytest.raises(backups.BackupError):
        backups.delete('20261112-143005')          # well-formed, but not there


def test_partial_backups_are_not_listed(backups, db_path):
    os.makedirs(os.path.join(backups.backup_dir(), '.20261112-143005.partial'))
    os.makedirs(os.path.join(backups.backup_dir(), '20261112-143006'))     # no meta.json
    assert backups.list_backups() == []


# --- routes ------------------------------------------------------------------

def test_backup_pages_are_admin_only(client, db, people):
    login(client, 'bob')
    assert client.get('/admin/backups').status_code in (302, 403)
    client.post('/admin/backups/create')
    from utils import backups
    assert backups.list_backups() == []


def test_admin_backs_up_restores_downloads_and_deletes(client, db, people, uploads):
    from utils import backups
    login(client, 'alice')
    r = client.post('/admin/backups/create', follow_redirects=True)
    assert r.status_code == 200 and b'Backed up' in r.data
    name = backups.latest()['name']
    assert name.encode() in client.get('/admin/backups').data or b'newest' in client.get('/admin/backups').data

    add_book(db, people['alice'], 'Added later', 'Someone')
    r = client.post(f'/admin/backups/{name}/restore', follow_redirects=True)
    assert b'Restored the backup' in r.data
    assert scalar(db, "SELECT COUNT(*) FROM books WHERE title = 'Added later'") == 0

    r = client.get(f'/admin/backups/{name}/download')
    assert r.status_code == 200 and r.data.startswith(b'SQLite format 3')
    assert client.get('/admin/backups/nope/download').status_code == 404

    client.post(f'/admin/backups/{name}/delete')
    assert name not in [b['name'] for b in backups.list_backups()]


def test_back_up_now_from_the_goodreads_page(client, db, people):
    login(client, 'alice')
    page = client.get('/user/import_goodreads_page').get_data(as_text=True)
    assert 'Back up first' in page and 'No backups yet' in page
    r = client.post('/admin/backups/create', data={'back': 'goodreads'})
    assert r.headers['Location'].endswith('/user/import_goodreads_page')
    assert 'Last backup' in client.get('/user/import_goodreads_page').get_data(as_text=True)


def test_goodreads_page_tells_non_admins_who_can_restore(client, db, people):
    login(client, 'bob')
    page = client.get('/user/import_goodreads_page').get_data(as_text=True)
    assert 'your admin can restore' in page and 'Back up now' not in page


def test_goodreads_import_backs_up_first(client, db, people, monkeypatch):
    from test_goodreads import run, row
    from utils import backups
    run(client, 'bob', row('Dune'))
    made = backups.latest()
    assert made['kind'] == 'goodreads' and made['by'] == 'bob'
    # The backup is from before the import wrote anything
    copy = sqlite3.connect(os.path.join(backups.folder(made['name']), 'library.db'))
    assert copy.execute("SELECT COUNT(*) FROM books WHERE title = 'Dune'").fetchone()[0] == 0
    copy.close()


def test_goodreads_import_refuses_without_a_backup(client, db, people, monkeypatch):
    from test_goodreads import upload, fingerprint, csv_text, row
    from utils import backups

    def broken(*a, **kw):
        raise backups.BackupError('disk full')
    monkeypatch.setattr(backups, 'create', broken)
    login(client, 'bob')
    upload(client, csv_text(row('Dune')))
    r = client.post('/user/import_goodreads/apply', json={'fingerprint': fingerprint(client)})
    assert r.status_code == 500 and 'nothing was imported' in r.get_json()['error']
    assert scalar(db, "SELECT COUNT(*) FROM books WHERE title = 'Dune'") == 0
