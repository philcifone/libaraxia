-- 036: photos beyond the cover (ROADMAP 16.0a, docs/PHOTOS-VALUE-SPEC.md).
-- Each item (a books row: each user's copy is its own row) can have one back
-- photo, one spine photo (books only, enforced in blueprints/photos.py) and a
-- gallery. The cover stays in books.cover_image_url; a photo row is never the
-- cover. Files live under static/uploads/photos/<book_id>/ and are removed
-- through image_utils.delete_image_file; find_orphaned_images reads this
-- table so the admin cleanup never deletes them.

CREATE TABLE item_photos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('back', 'spine', 'gallery')),
    path TEXT NOT NULL,              -- 'uploads/photos/...', relative to static/
    caption TEXT,                    -- optional, e.g. "Inner sleeve"
    position INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_item_photos_book ON item_photos(book_id, kind, position);
CREATE UNIQUE INDEX idx_item_photos_one_back ON item_photos(book_id) WHERE kind = 'back';
CREATE UNIQUE INDEX idx_item_photos_one_spine ON item_photos(book_id) WHERE kind = 'spine';
