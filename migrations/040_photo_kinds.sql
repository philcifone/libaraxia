-- 040: photo kinds as a lookup table, and two more of them (ROADMAP 16.0a).
-- The 3D view grows from books to movies and music: a VHS sleeve is printed
-- on its top and both long sides, so it needs a 'top' and a 'side' (the
-- right-hand side; 'spine' is the left, as on a book). 036 held the kinds in
-- a CHECK, which SQLite can't alter, so item_photos is rebuilt with a
-- foreign key instead (as media_types and statuses: the next kind is an
-- INSERT). `single` = 1: an item has at most one of that kind, which the
-- one unique index now says for all of them. Which kinds a format takes is
-- utils/photos.kinds_for; a test keeps this table and utils/photos in step.

CREATE TABLE photo_kinds (
    code TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    single INTEGER NOT NULL DEFAULT 1 CHECK (single IN (0, 1)),
    position INTEGER NOT NULL DEFAULT 0     -- the gallery's order
);
INSERT INTO photo_kinds (code, label, single, position) VALUES
    ('back', 'Back', 1, 1),
    ('spine', 'Spine', 1, 2),
    ('side', 'Right side', 1, 3),
    ('top', 'Top', 1, 4),
    ('gallery', 'Photo', 0, 5);

CREATE TABLE item_photos_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    kind TEXT NOT NULL REFERENCES photo_kinds(code),
    path TEXT NOT NULL,              -- 'uploads/photos/...', relative to static/
    caption TEXT,                    -- optional, e.g. "Inner sleeve"
    position INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO item_photos_new (id, book_id, kind, path, caption, position, created_at)
    SELECT id, book_id, kind, path, caption, position, created_at FROM item_photos;
DROP TABLE item_photos;
ALTER TABLE item_photos_new RENAME TO item_photos;
CREATE INDEX idx_item_photos_book ON item_photos(book_id, kind, position);
CREATE UNIQUE INDEX idx_item_photos_one_each ON item_photos(book_id, kind) WHERE kind <> 'gallery';
