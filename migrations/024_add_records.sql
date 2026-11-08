-- 024: records (Phase 8.7, the Vinyls section). A record is a books row
-- with media_type = 'record'.
--
-- The allowed media types and statuses move from CHECK constraints into two
-- lookup tables, media_types and statuses. SQLite can't alter a CHECK, so
-- every new type or status used to mean rebuilding books (9 tables point at
-- it) and collections. With lookup tables a new one is an INSERT. Foreign
-- keys are enforced (get_db_connection), so bad values are still refused.
-- utils/media.py keeps the same lists for the app; tests/test_records.py
-- checks the two agree.
--
-- This needs one last rebuild of both tables. The runner runs this file in
-- one transaction with foreign keys off, and rolls it back if it leaves any
-- foreign_key_check violations. Columns keep their order (some templates
-- read rows by position) and ids, and the AUTOINCREMENT counters are kept
-- (dropping a table drops its sqlite_sequence row).
--
-- The views go first: since SQLite 3.26, ALTER TABLE ... RENAME checks
-- every view, and fails if one still names the dropped table.

DROP VIEW IF EXISTS library_books;
DROP VIEW IF EXISTS library_videos;

-- ------------------------------------------------------------- lookups
CREATE TABLE media_types (
    name TEXT PRIMARY KEY
);
INSERT INTO media_types (name) VALUES ('book'), ('video'), ('record');

-- Per-user status (collections.status) and the media type it belongs to.
-- Routes check a status suits the item's type (media.is_valid_status).
CREATE TABLE statuses (
    status TEXT PRIMARY KEY,
    media_type TEXT NOT NULL REFERENCES media_types(name)
);
INSERT INTO statuses (status, media_type) VALUES
    ('read', 'book'), ('want to read', 'book'),
    ('currently reading', 'book'), ('did not finish', 'book'),
    ('watched', 'video'), ('want to watch', 'video'),
    ('listened', 'record'), ('want to listen', 'record');

-- ------------------------------------------------------------- books
CREATE TEMP TABLE _seq AS
SELECT name, seq FROM sqlite_sequence WHERE name IN ('books', 'collections');

CREATE TABLE books_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    author TEXT NOT NULL,
    publisher TEXT,
    publish_year INTEGER,
    isbn TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    page_count INTEGER,
    cover_image_url TEXT,
    description TEXT,
    local_thumbnail TEXT,
    subtitle TEXT,
    genre TEXT,
    added_by INTEGER,
    removed_at TIMESTAMP,
    removed_note TEXT,
    media_type TEXT NOT NULL DEFAULT 'book' REFERENCES media_types(name),
    format TEXT,
    barcode TEXT,
    catalog_number TEXT,
    runtime_minutes INTEGER,
    FOREIGN KEY (added_by) REFERENCES users(id) ON DELETE SET NULL
);
INSERT INTO books_new (id, title, author, publisher, publish_year, isbn, created_at,
                       page_count, cover_image_url, description, local_thumbnail,
                       subtitle, genre, added_by, removed_at, removed_note,
                       media_type, format, barcode, catalog_number, runtime_minutes)
SELECT id, title, author, publisher, publish_year, isbn, created_at,
       page_count, cover_image_url, description, local_thumbnail,
       subtitle, genre, added_by, removed_at, removed_note,
       media_type, format, barcode, catalog_number, runtime_minutes
FROM books;
DROP TABLE books;
ALTER TABLE books_new RENAME TO books;
CREATE INDEX idx_books_added_by ON books(added_by);
CREATE INDEX idx_books_media_type ON books(media_type);
CREATE INDEX idx_books_barcode ON books(barcode);

-- ------------------------------------------------------------- collections
CREATE TABLE collections_new (
    collection_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    book_id INTEGER NOT NULL,
    status TEXT NOT NULL REFERENCES statuses(status),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
);
INSERT INTO collections_new (collection_id, user_id, book_id, status, created_at, updated_at)
SELECT collection_id, user_id, book_id, status, created_at, updated_at FROM collections;
DROP TABLE collections;
ALTER TABLE collections_new RENAME TO collections;
CREATE INDEX idx_collections_created_at ON collections(created_at);

-- ------------------------------------------------------------- counters
-- The new tables' rows were inserted with explicit ids, so their counters
-- are already at MAX(id); restore the old value if it was higher (rows
-- deleted from the end, whose ids mustn't be reused).
UPDATE sqlite_sequence
   SET seq = MAX(seq, (SELECT s.seq FROM _seq s WHERE s.name = sqlite_sequence.name))
 WHERE name IN (SELECT name FROM _seq);
INSERT INTO sqlite_sequence (name, seq)
SELECT s.name, s.seq FROM _seq s
 WHERE NOT EXISTS (SELECT 1 FROM sqlite_sequence q WHERE q.name = s.name);
DROP TABLE _seq;

-- ------------------------------------------------------------- views
-- Owned items on their owner's shelf, one view per section: owned, and not
-- the owner's own wishlist entry. Removed items are included (filter on
-- removed_at). A table rebuild of books or wishlist must drop and recreate
-- these views.
CREATE VIEW library_books AS
SELECT b.*
FROM books b
WHERE b.media_type = 'book'
  AND b.added_by IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM wishlist w
      WHERE w.book_id = b.id AND w.user_id = b.added_by
  );

CREATE VIEW library_videos AS
SELECT b.*
FROM books b
WHERE b.media_type = 'video'
  AND b.added_by IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM wishlist w
      WHERE w.book_id = b.id AND w.user_id = b.added_by
  );

CREATE VIEW library_records AS
SELECT b.*
FROM books b
WHERE b.media_type = 'record'
  AND b.added_by IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM wishlist w
      WHERE w.book_id = b.id AND w.user_id = b.added_by
  );
