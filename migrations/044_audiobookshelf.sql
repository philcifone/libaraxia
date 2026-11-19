-- 044: the Audiobookshelf connection (ROADMAP 16.0e,
-- docs/AUDIOBOOKSHELF-SPEC.md section 6). 043 added books.narrator.

-- A user's ABS API key, encrypted (utils/audiobookshelf.py seal(): Fernet
-- under a key derived from SECRET_KEY), and who it belongs to on ABS. Not a
-- users column: SELECT * FROM users feeds current_user everywhere.
CREATE TABLE abs_accounts (
    user_id      INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    token_enc    TEXT NOT NULL,
    abs_user_id  TEXT NOT NULL,
    abs_username TEXT NOT NULL,
    connected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_sync_at TIMESTAMP
);

-- What the last Sync fetched, waiting for review (one set per user, swept
-- after 24 h), as goodreads_staging is for a CSV.
CREATE TABLE abs_staging (
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    abs_item_id TEXT NOT NULL,
    data        TEXT NOT NULL,          -- JSON: trimmed metadata + progress
    choice      TEXT,                   -- NULL: the box's default
    staged_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, abs_item_id)
);

-- What each ABS item became: re-runs create nothing twice, the item page's
-- note, and the live progress line. book_id SET NULL like goodreads_rows:
-- a deleted book leaves the memory ("imported before, since deleted").
CREATE TABLE abs_links (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    abs_item_id TEXT NOT NULL,
    book_id     INTEGER REFERENCES books(id) ON DELETE SET NULL,
    outcome     TEXT NOT NULL CHECK (outcome IN ('created', 'attached', 'skipped')),
    asin        TEXT,
    session_id  INTEGER REFERENCES reading_sessions(session_id) ON DELETE SET NULL,
    finished_at TIMESTAMP,              -- ABS finishedAt last recorded
    linked_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, abs_item_id)
);
CREATE INDEX idx_abs_links_book ON abs_links(book_id);
