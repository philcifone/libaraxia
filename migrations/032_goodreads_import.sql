-- 032: the granular Goodreads import (ROADMAP 14b, docs/GOODREADS-IMPORT-SPEC.md
-- section 9). Additive only: three new tables, no rebuilds.

-- A Goodreads upload waiting for review. One upload per user: a new one
-- replaces it. Swept after 24 hours. Not in the session cookie.
CREATE TABLE goodreads_staging (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    line INTEGER NOT NULL,          -- CSV line, 2 = first data row
    data TEXT NOT NULL,             -- parse_row() output plus goodreads_id and shelves, JSON
    choice TEXT,                    -- NULL: the box's default
    filename TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, line)
);

-- One row per applied import. Permanent (unlike bulk_edits, swept at 30 days).
CREATE TABLE goodreads_imports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    edit_id INTEGER REFERENCES bulk_edits(id) ON DELETE SET NULL,  -- undo, while it lasts
    filename TEXT,
    row_count INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    undone_at TIMESTAMP
);
CREATE INDEX idx_goodreads_imports_user ON goodreads_imports(user_id);

-- What each CSV row of an import did: the provenance behind the "From
-- Goodreads" filter, the book page note, and the next import's Book Id match.
CREATE TABLE goodreads_rows (
    import_id INTEGER NOT NULL REFERENCES goodreads_imports(id) ON DELETE CASCADE,
    line INTEGER NOT NULL,
    goodreads_id TEXT,              -- the export's Book Id; NULL if missing
    book_id INTEGER REFERENCES books(id) ON DELETE SET NULL,
    outcome TEXT NOT NULL,          -- an OUTCOMES key
    wrote TEXT,                     -- JSON list: book, status, rating, review, sessions, wishlist
    shelves TEXT,                   -- the row's Goodreads shelves, comma-separated
    PRIMARY KEY (import_id, line)
);
CREATE INDEX idx_goodreads_rows_book ON goodreads_rows(book_id);
CREATE INDEX idx_goodreads_rows_gid ON goodreads_rows(goodreads_id);
