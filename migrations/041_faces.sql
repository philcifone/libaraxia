-- 041: faces and placeholders (ROADMAP 16.0c, docs/FACES-SPEC.md).
-- A bottom photo for every item, and the admin's placeholder images that
-- stand in for a face without a photo (a clamshell's plastic top, an
-- orange tape's bottom, a page texture), grouped into named sets an owner
-- picks per item.
--
-- body: which kind of thing a placeholder is for ('book', 'vinyl', 'cd',
-- 'cassette', 'dvd', 'vhs_sleeve', 'vhs_clamshell'; utils/faces.BODIES,
-- checked in code). kind: the face it stands in for. A placeholder's file
-- is under static/uploads/faces/; find_orphaned_images reads this table.

INSERT INTO photo_kinds (code, label, single, position) VALUES ('bottom', 'Bottom', 1, 5);
UPDATE photo_kinds SET position = 6 WHERE code = 'gallery';

CREATE TABLE face_placeholders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    body TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('spine', 'side', 'top', 'bottom')),
    name TEXT NOT NULL,
    path TEXT NOT NULL,              -- 'uploads/faces/...', relative to static/
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_face_placeholders_body ON face_placeholders(body, kind);

-- A named group of placeholders for one body, one per face at most; one
-- set per body may be its default (used where an item chose nothing)
CREATE TABLE face_sets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    body TEXT NOT NULL,
    name TEXT NOT NULL,
    is_default INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0, 1)),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX idx_face_sets_one_default ON face_sets(body) WHERE is_default = 1;

CREATE TABLE face_set_members (
    set_id INTEGER NOT NULL REFERENCES face_sets(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('spine', 'side', 'top', 'bottom')),
    placeholder_id INTEGER NOT NULL REFERENCES face_placeholders(id) ON DELETE CASCADE,
    PRIMARY KEY (set_id, kind)
);

-- An owner's choice of placeholder for one face of one item. A photo of
-- that face wins over it; deleting the placeholder drops the choice.
CREATE TABLE item_faces (
    book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('spine', 'side', 'top', 'bottom')),
    placeholder_id INTEGER NOT NULL REFERENCES face_placeholders(id) ON DELETE CASCADE,
    PRIMARY KEY (book_id, kind)
);
CREATE INDEX idx_item_faces_placeholder ON item_faces(placeholder_id);
