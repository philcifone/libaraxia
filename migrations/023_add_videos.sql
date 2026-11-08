-- 023: videos (Phase 8). A video is a books row with media_type = 'video'.
--
-- Same table, so reviews, statuses, sessions, tags and custom collections
-- (all keyed on books.id) work for tapes unchanged. The two sections are
-- kept apart by the views: library_books is books only (so the Library, its
-- counts, stats, filters and book matching ignore videos without any other
-- edits), and library_videos feeds the Videos section. See utils/media.py.
--
-- New columns are appended at the end: some templates read rows by position.
--   media_type       'book' | 'video'
--   format           physical format of a video ('VHS'; DVD, LaserDisc... later)
--   barcode          normalised EAN-13 (a UPC-A gets a leading 0)
--   catalog_number   studio catalogue number from the spine/label
--   runtime_minutes  running time
--
-- collections.status also gets the video statuses, which needs a table
-- rebuild (SQLite can't alter a CHECK). Nothing references collections, and
-- the runner turns foreign keys off while this runs.

ALTER TABLE books ADD COLUMN media_type TEXT NOT NULL DEFAULT 'book'
    CHECK (media_type IN ('book', 'video'));
ALTER TABLE books ADD COLUMN format TEXT;
ALTER TABLE books ADD COLUMN barcode TEXT;
ALTER TABLE books ADD COLUMN catalog_number TEXT;
ALTER TABLE books ADD COLUMN runtime_minutes INTEGER;
CREATE INDEX idx_books_media_type ON books(media_type);
CREATE INDEX idx_books_barcode ON books(barcode);

-- ------------------------------------------------------------- collections
-- Keep the AUTOINCREMENT counter (dropping a table resets it).
CREATE TEMP TABLE _seq AS SELECT seq FROM sqlite_sequence WHERE name = 'collections';

CREATE TABLE collections_new (
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
INSERT INTO collections_new (collection_id, user_id, book_id, status, created_at, updated_at)
SELECT collection_id, user_id, book_id, status, created_at, updated_at FROM collections;
DROP TABLE collections;
ALTER TABLE collections_new RENAME TO collections;
CREATE INDEX idx_collections_created_at ON collections(created_at);

UPDATE sqlite_sequence SET seq = MAX(seq, (SELECT seq FROM _seq))
 WHERE name = 'collections' AND EXISTS (SELECT 1 FROM _seq);
INSERT INTO sqlite_sequence (name, seq)
SELECT 'collections', seq FROM _seq
 WHERE NOT EXISTS (SELECT 1 FROM sqlite_sequence WHERE name = 'collections');
DROP TABLE _seq;

-- ------------------------------------------------------------- views
-- library_books: as in 018, now books only.
DROP VIEW IF EXISTS library_books;
CREATE VIEW library_books AS
SELECT b.*
FROM books b
WHERE b.media_type = 'book'
  AND b.added_by IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM wishlist w
      WHERE w.book_id = b.id AND w.user_id = b.added_by
  );

-- library_videos: owned videos. There's no video wishlist (yet), but the
-- same exclusion keeps the two views alike if one is added.
DROP VIEW IF EXISTS library_videos;
CREATE VIEW library_videos AS
SELECT b.*
FROM books b
WHERE b.media_type = 'video'
  AND b.added_by IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM wishlist w
      WHERE w.book_id = b.id AND w.user_id = b.added_by
  );
