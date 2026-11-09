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


# Migration 023's books and collections, with their CHECK constraints (024
# replaced them with the media_types / statuses lookup tables).
BOOKS_023 = """
    CREATE TABLE books (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL, author TEXT NOT NULL, publisher TEXT, publish_year INTEGER,
        isbn TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, page_count INTEGER,
        cover_image_url TEXT, description TEXT, local_thumbnail TEXT, subtitle TEXT,
        genre TEXT, added_by INTEGER, removed_at TIMESTAMP, removed_note TEXT,
        media_type TEXT NOT NULL DEFAULT 'book' CHECK (media_type IN ('book', 'video')),
        format TEXT, barcode TEXT, catalog_number TEXT, runtime_minutes INTEGER,
        FOREIGN KEY (added_by) REFERENCES users(id) ON DELETE SET NULL
    );
    CREATE INDEX idx_books_added_by ON books(added_by);
    CREATE INDEX idx_books_media_type ON books(media_type);
    CREATE INDEX idx_books_barcode ON books(barcode);
    CREATE TABLE collections (
        collection_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        book_id INTEGER NOT NULL,
        status TEXT CHECK(status IN ('read', 'want to read', 'currently reading', 'did not finish',
                                     'watched', 'want to watch')) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
    );
    CREATE INDEX idx_collections_created_at ON collections(created_at);
"""


def wind_back_to_023(conn):
    """Turn a fresh (empty) database into one at migration 023: books and
    collections with their old CHECKs, no lookup tables, no library_records."""
    conn.executescript(f"""
        PRAGMA foreign_keys = OFF;
        DROP VIEW library_books;
        DROP VIEW library_videos;
        DROP VIEW library_records;
        DROP TABLE books;
        DROP TABLE collections;
        DROP TABLE statuses;
        DROP TABLE media_types;
        {BOOKS_023}
        CREATE VIEW library_books AS SELECT b.* FROM books b
        WHERE b.media_type = 'book' AND b.added_by IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM wishlist w WHERE w.book_id = b.id AND w.user_id = b.added_by);
        CREATE VIEW library_videos AS SELECT b.* FROM books b
        WHERE b.media_type = 'video' AND b.added_by IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM wishlist w WHERE w.book_id = b.id AND w.user_id = b.added_by);
        -- 024 rebuilds books and 025 adds books.owned; the rebuilt books
        -- above has neither, so both run again. Later migrations on other
        -- tables (026: users) stay applied.
        DELETE FROM schema_migrations WHERE name IN ('024_add_records.sql', '025_owned.sql');
    """)


def fresh_db(path):
    conn = sqlite3.connect(path)
    with open(os.path.join(ROOT, 'create_database.sql'), encoding='utf-8') as f:
        conn.executescript(f.read())
    return conn


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
    conn = fresh_db(path)
    # Wind the schema back to "migration 013, never baselined".
    wind_back_to_023(conn)
    conn.executescript("""
        DROP TABLE schema_migrations;
        DROP VIEW library_books;       -- added by 018
        DROP TABLE household_invites;  -- added by 021
        DROP TABLE cover_jobs;         -- added by 022
        DROP TABLE reading_goals;      -- added by 029
        -- videos, added by 023
        DROP VIEW library_videos;
        DROP INDEX idx_books_media_type;
        DROP INDEX idx_books_barcode;
        ALTER TABLE books DROP COLUMN runtime_minutes;
        ALTER TABLE books DROP COLUMN catalog_number;
        ALTER TABLE books DROP COLUMN barcode;
        ALTER TABLE books DROP COLUMN format;
        ALTER TABLE books DROP COLUMN media_type;
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


def test_024_keeps_data_ids_and_counters(template_db, tmp_path):
    """024 rebuilds books and collections: every row, id, column order and
    AUTOINCREMENT counter survives, and the views come back (plus
    library_records)."""
    path = tmp_path / 'at-023.db'
    conn = fresh_db(path)
    wind_back_to_023(conn)
    conn.executescript("""
        INSERT INTO users (id, username, email, password) VALUES (1, 'phil', 'p@example.test', 'x');
        INSERT INTO books (id, title, author, added_by) VALUES (1, 'A book', 'A', 1);
        INSERT INTO books (id, title, author, added_by, media_type, format, barcode)
            VALUES (2, 'A tape', 'D', 1, 'video', 'VHS', '0012345678905');
        INSERT INTO books (id, title, author, added_by) VALUES (3, 'Deleted later', 'A', 1);
        INSERT INTO collections (collection_id, user_id, book_id, status) VALUES (1, 1, 1, 'read');
        INSERT INTO collections (collection_id, user_id, book_id, status) VALUES (2, 1, 2, 'watched');
        INSERT INTO collections (collection_id, user_id, book_id, status) VALUES (3, 1, 3, 'read');
        INSERT INTO read_data (user_id, book_id, rating) VALUES (1, 2, 4);
        DELETE FROM collections WHERE collection_id = 3;
        DELETE FROM books WHERE id = 3;   -- counters are now above MAX(id)
    """)
    conn.close()

    run_manage('--db', str(path), 'migrate', '-y')

    conn = connect(path)
    assert conn.execute('PRAGMA foreign_key_check').fetchall() == []
    assert [tuple(r) for r in conn.execute('SELECT id, media_type, format FROM books ORDER BY id')] == [
        (1, 'book', None), (2, 'video', 'VHS')]
    assert [tuple(r) for r in conn.execute('SELECT book_id, status FROM collections ORDER BY 1')] == [
        (1, 'read'), (2, 'watched')]
    assert conn.execute('SELECT rating FROM read_data WHERE book_id = 2').fetchone()[0] == 4
    seq = dict(conn.execute("SELECT name, seq FROM sqlite_sequence WHERE name IN ('books', 'collections')"))
    assert seq == {'books': 3, 'collections': 3}, 'deleted ids must not be reused'
    assert [r[0] for r in conn.execute('SELECT id FROM library_videos')] == [2]
    conn.close()
    assert schema(path) == schema(template_db)


def test_unknown_media_type_or_status_is_refused(db):
    """The lookup tables do what the CHECKs did (foreign keys are on)."""
    db.execute("INSERT INTO users (id, username, email, password) VALUES (900, 'u900', 'u900@x.test', 'x')")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO books (title, author, media_type) VALUES ('x', 'y', 'cd')")
    book = db.execute("INSERT INTO books (title, author, media_type) VALUES ('x', 'y', 'record')").lastrowid
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO collections (user_id, book_id, status) VALUES (900, ?, 'bogus')", (book,))
    db.execute("INSERT INTO collections (user_id, book_id, status) VALUES (900, ?, 'listened')", (book,))


def test_lookup_tables_match_utils_media(db):
    """utils/media.py and the media_types / statuses tables list the same values."""
    from utils import media
    assert {r[0] for r in db.execute('SELECT name FROM media_types')} == set(media.MEDIA_TYPES)
    in_db = {(r[0], r[1]) for r in db.execute('SELECT status, media_type FROM statuses')}
    assert in_db == {(s, t) for t, statuses in media.STATUSES.items() for s in statuses}
