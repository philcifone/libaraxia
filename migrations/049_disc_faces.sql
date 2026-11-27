-- 049: disc faces (Phil, 2026-11-26). A DVD or CD kept without its case is
-- photographed as the bare disc (the crop tool's Disc shape) and turns in
-- 3D as a disc: a front and a back, no box. The admin's placeholders gain
-- two faces for it, 'front' (a disc's label side, standing in for an item
-- with no cover photo) and 'back' (its shiny data side), offered on the
-- DVD and CD tabs only (utils/faces.DISC_KINDS, checked in code).
--
-- SQLite can't alter a CHECK, so the three tables that name the kinds are
-- rebuilt with the same columns, ids and order. The runner runs this file
-- in one transaction with foreign keys off and rolls it back if it leaves
-- any foreign_key_check violations. face_placeholders' AUTOINCREMENT
-- counter is kept: dropping a table drops its sqlite_sequence row.

CREATE TEMP TABLE _seq AS SELECT seq FROM sqlite_sequence WHERE name = 'face_placeholders';

CREATE TABLE face_placeholders_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    medium TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('spine', 'side', 'top', 'bottom', 'front', 'back')),
    name TEXT NOT NULL,
    path TEXT NOT NULL,              -- 'uploads/faces/...', relative to static/
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO face_placeholders_new (id, medium, kind, name, path, created_at)
SELECT id, medium, kind, name, path, created_at FROM face_placeholders;
DROP TABLE face_placeholders;
ALTER TABLE face_placeholders_new RENAME TO face_placeholders;
CREATE INDEX idx_face_placeholders_medium ON face_placeholders(medium, kind);

UPDATE sqlite_sequence SET seq = MAX(seq, (SELECT seq FROM _seq))
WHERE name = 'face_placeholders' AND EXISTS (SELECT 1 FROM _seq);
INSERT INTO sqlite_sequence (name, seq)
SELECT 'face_placeholders', seq FROM _seq
WHERE NOT EXISTS (SELECT 1 FROM sqlite_sequence WHERE name = 'face_placeholders');
DROP TABLE _seq;

CREATE TABLE face_set_members_new (
    set_id INTEGER NOT NULL REFERENCES face_sets(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('spine', 'side', 'top', 'bottom', 'front', 'back')),
    placeholder_id INTEGER NOT NULL REFERENCES face_placeholders(id) ON DELETE CASCADE,
    PRIMARY KEY (set_id, kind)
);
INSERT INTO face_set_members_new (set_id, kind, placeholder_id)
SELECT set_id, kind, placeholder_id FROM face_set_members;
DROP TABLE face_set_members;
ALTER TABLE face_set_members_new RENAME TO face_set_members;

CREATE TABLE item_faces_new (
    book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('spine', 'side', 'top', 'bottom', 'front', 'back')),
    placeholder_id INTEGER NOT NULL REFERENCES face_placeholders(id) ON DELETE CASCADE,
    PRIMARY KEY (book_id, kind)
);
INSERT INTO item_faces_new (book_id, kind, placeholder_id)
SELECT book_id, kind, placeholder_id FROM item_faces;
DROP TABLE item_faces;
ALTER TABLE item_faces_new RENAME TO item_faces;
CREATE INDEX idx_item_faces_placeholder ON item_faces(placeholder_id);
