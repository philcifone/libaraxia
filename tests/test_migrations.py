"""create_database.sql and the manage.py migration runner."""
import os
import re
import sqlite3

import pytest

import manage
from conftest import ROOT, run_manage

ALL_MIGRATIONS = manage.migration_files()


def connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def schema(path):
    """Columns, foreign keys, indexes and CHECKs of every table. Compared by
    structure, not CREATE text, which differs in quoting/whitespace after a
    table rebuild without meaning anything."""
    conn = connect(path)
    out = {}
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    for t in tables:
        sql = conn.execute("SELECT sql FROM sqlite_master WHERE name = ?", (t,)).fetchone()[0]
        body = re.sub(r'\s+', '', re.sub(r'--[^\n]*', '', sql))
        out[t] = {
            'columns': [tuple(r)[1:6] for r in conn.execute(f"PRAGMA table_info('{t}')")],
            'fks': sorted(tuple(r)[2:7] for r in conn.execute(f"PRAGMA foreign_key_list('{t}')")),
            'indexes': sorted((r[1], r[2], tuple(x[2] for x in conn.execute(f"PRAGMA index_info('{r[1]}')")))
                              for r in conn.execute(f"PRAGMA index_list('{t}')")),
            'checks': sorted(re.findall(r'CHECK\((?:[^()]|\([^()]*\))*\)', body)),
            'autoincrement': 'AUTOINCREMENT' in body.upper(),
        }
    # Views: compare the SELECT with comments and whitespace removed
    for name, sql in conn.execute("SELECT name, sql FROM sqlite_master WHERE type = 'view' ORDER BY name"):
        out['view:' + name] = re.sub(r'\s+', '', re.sub(r'--[^\n]*', '', sql))
    conn.close()
    return out


def test_fresh_database_has_every_migration_and_clean_fks(template_db):
    conn = connect(template_db)
    applied = {r[0] for r in conn.execute('SELECT name FROM schema_migrations')}
    assert applied == set(ALL_MIGRATIONS)
    assert conn.execute('PRAGMA foreign_key_check').fetchall() == []
    assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    conn.close()


def test_create_database_sql_lists_every_migration_file():
    """Adding a migration means folding it in and adding it to the ledger INSERT."""
    with open(os.path.join(ROOT, 'create_database.sql'), encoding='utf-8') as f:
        sql = f.read()
    missing = [m for m in ALL_MIGRATIONS if f"'{m}'" not in sql]
    assert missing == [], f'create_database.sql ledger is missing {missing}'


def test_plain_sqlite3_import_matches_manage_migrate(template_db, tmp_path):
    """`sqlite3 new.db < create_database.sql` gives the same schema as `manage.py migrate`."""
    path = tmp_path / 'plain.db'
    conn = sqlite3.connect(path)
    with open(os.path.join(ROOT, 'create_database.sql'), encoding='utf-8') as f:
        conn.executescript(f.read())
    conn.close()
    assert schema(path) == schema(template_db)
    assert 'Up to date.' in run_manage('--db', str(path), 'migrate', '-y').stdout


def test_migrate_is_idempotent(db_path, tmp_path):
    before = schema(db_path)
    result = run_manage('--db', str(db_path), 'migrate', '-y')
    assert 'Up to date.' in result.stdout
    assert schema(db_path) == before
    assert not [p for p in os.listdir(tmp_path) if '.backup-' in p], 'nothing to do, so no backup'


def test_migrate_refuses_database_without_ledger(tmp_path):
    path = tmp_path / 'old.db'
    conn = sqlite3.connect(path)
    conn.execute('CREATE TABLE users (id INTEGER PRIMARY KEY)')
    conn.close()
    result = run_manage('--db', str(path), 'migrate', '-y', check=False)
    assert result.returncode != 0
    assert '--baseline' in result.stderr


def test_pre_runner_database_with_broken_collections_fks_migrates(template_db, tmp_path):
    """Regression (prod, 2026-11-02): old databases declare collections' keys as
    books(book_id) / users(user_id), which don't exist, so SQLite's foreign key
    check fails with "foreign key mismatch". Baseline + migrate must still work,
    and 014 must still remove orphaned collections rows."""
    path = tmp_path / 'prod-like.db'
    conn = sqlite3.connect(path)
    with open(os.path.join(ROOT, 'create_database.sql'), encoding='utf-8') as f:
        conn.executescript(f.read())
    # Wind the schema back to "migration 013, never baselined".
    conn.executescript("""
        DROP TABLE schema_migrations;
        DROP VIEW library_books;       -- added by 018
        DROP TABLE household_invites;  -- added by 021
        DROP TABLE cover_jobs;         -- added by 022
        -- privacy columns from 012, dropped again by 020
        ALTER TABLE wishlist ADD COLUMN privacy TEXT DEFAULT 'friends';
        ALTER TABLE reading_sessions ADD COLUMN privacy TEXT DEFAULT 'friends';
        ALTER TABLE user_collections ADD COLUMN privacy TEXT DEFAULT 'friends';
        ALTER TABLE users ADD COLUMN default_privacy TEXT DEFAULT 'friends';
        ALTER TABLE books DROP COLUMN removed_note;
        ALTER TABLE books DROP COLUMN removed_at;
        PRAGMA foreign_keys = OFF;
        DROP TABLE collections;
        CREATE TABLE collections (
            collection_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            book_id INTEGER NOT NULL,
            status TEXT NOT NULL, created_at TIMESTAMP, updated_at TIMESTAMP,
            privacy TEXT DEFAULT 'friends',
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            FOREIGN KEY (book_id) REFERENCES books(book_id)
        );
        INSERT INTO users (id, username, email, password) VALUES (1, 'phil', 'p@example.test', 'x');
        INSERT INTO books (id, title, author, added_by) VALUES (10, 'Kept', 'A', 1);
        INSERT INTO collections (user_id, book_id, status) VALUES (1, 10, 'read');   -- valid
        INSERT INTO collections (user_id, book_id, status) VALUES (1, 99, 'read');   -- book gone
        INSERT INTO read_data (user_id, book_id, rating) VALUES (1, 10, 5);          -- valid
        INSERT INTO read_data (user_id, book_id, rating) VALUES (1, 99, 5);          -- book gone
        INSERT INTO books (id, title, author, added_by) VALUES (11, 'Owner gone', 'B', 42);
    """)
    conn.close()

    run_manage('--db', str(path), 'migrate', '--baseline', '-y')
    run_manage('--db', str(path), 'migrate', '-y')

    conn = connect(path)
    assert conn.execute('PRAGMA foreign_key_check').fetchall() == []
    assert [tuple(r) for r in conn.execute('SELECT user_id, book_id FROM collections')] == [(1, 10)]
    assert [tuple(r) for r in conn.execute('SELECT user_id, book_id FROM read_data')] == [(1, 10)]
    # A book whose owner is gone is kept, unowned.
    assert conn.execute('SELECT added_by FROM books WHERE id = 11').fetchone()[0] is None
    conn.close()
    assert schema(path) == schema(template_db)


def test_fk_violations_skips_tables_that_cannot_be_checked(tmp_path):
    conn = manage.connect(str(tmp_path / 'x.db'))
    conn.executescript("""
        CREATE TABLE parent (id INTEGER PRIMARY KEY);
        CREATE TABLE bad (pid INTEGER REFERENCES parent(nope));
        CREATE TABLE good (pid INTEGER REFERENCES parent(id));
        INSERT INTO good VALUES (7);
    """)
    assert manage.fk_violations(conn) == {('good', 1, 'parent', 0)}
    conn.close()


@pytest.fixture
def scratch_migrations(tmp_path, monkeypatch):
    folder = tmp_path / 'migrations'
    folder.mkdir()
    monkeypatch.setattr(manage, 'MIGRATIONS_DIR', str(folder))
    conn = manage.connect(str(tmp_path / 'm.db'))
    conn.executescript("""
        CREATE TABLE parent (id INTEGER PRIMARY KEY);
        CREATE TABLE child (pid INTEGER REFERENCES parent(id));
        INSERT INTO parent VALUES (1);
    """)
    manage.ensure_ledger(conn)
    yield folder, conn
    conn.close()


def test_migration_that_breaks_foreign_keys_is_rolled_back(scratch_migrations):
    folder, conn = scratch_migrations
    (folder / '900_bad.sql').write_text('INSERT INTO child VALUES (1);\nDELETE FROM parent;\n')
    with pytest.raises(RuntimeError, match='foreign key violation'):
        manage.apply_migration(conn, '900_bad.sql')
    assert conn.execute('SELECT COUNT(*) FROM parent').fetchone()[0] == 1
    assert conn.execute('SELECT COUNT(*) FROM child').fetchone()[0] == 0
    assert conn.execute('SELECT COUNT(*) FROM schema_migrations').fetchone()[0] == 0


def test_migration_with_its_own_transaction_is_refused(scratch_migrations):
    folder, conn = scratch_migrations
    (folder / '901_txn.sql').write_text('BEGIN;\nINSERT INTO parent VALUES (2);\nCOMMIT;\n')
    with pytest.raises(RuntimeError, match='BEGIN'):
        manage.apply_migration(conn, '901_txn.sql')
    assert conn.execute('SELECT COUNT(*) FROM parent').fetchone()[0] == 1


def test_good_migration_is_recorded(scratch_migrations):
    folder, conn = scratch_migrations
    (folder / '902_ok.sql').write_text("-- a trigger has ; inside it\n"
                                       "CREATE TRIGGER t AFTER INSERT ON parent BEGIN SELECT 1; END;\n"
                                       "INSERT INTO parent VALUES (2);\n")
    manage.apply_migration(conn, '902_ok.sql')
    assert conn.execute('SELECT COUNT(*) FROM parent').fetchone()[0] == 2
    assert [r[0] for r in conn.execute('SELECT name FROM schema_migrations')] == ['902_ok.sql']
