-- 031: bulk edit's journal and the "quiet" flag (ROADMAP 14a, docs/BULK-EDIT-SPEC.md).
-- 030 is reserved for ROADMAP 15.1; the runner applies whatever is missing
-- from the ledger in name order, so landing 031 first is fine.

-- One row per applied bulk edit.
CREATE TABLE bulk_edits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    action TEXT NOT NULL,          -- whitelist key: 'genre', 'status', ...
    params TEXT NOT NULL,          -- JSON of the action's value(s)
    summary TEXT NOT NULL,         -- 'Genre set to Cookbooks on 42 items'
    item_count INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    undone_at TIMESTAMP
);
CREATE INDEX idx_bulk_edits_user ON bulk_edits(user_id, created_at);

-- What each item was before and after, so undo can put it back.
CREATE TABLE bulk_edit_items (
    edit_id INTEGER NOT NULL REFERENCES bulk_edits(id) ON DELETE CASCADE,
    book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    before TEXT,                   -- JSON snapshot; NULL = no row existed
    after TEXT,                    -- JSON snapshot; NULL = no row exists now
    PRIMARY KEY (edit_id, book_id)
);

-- Status rows written in bulk (and later by the import) stay out of the feed.
ALTER TABLE collections ADD COLUMN quiet INTEGER NOT NULL DEFAULT 0;
