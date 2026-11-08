-- 027: custom shelves belong to one section (ROADMAP 8C, decided 2026-11-08):
-- user_collections.media_type, so the Collections page can show Books,
-- Movies and Music shelves on their own tabs.
--
-- A rebuild rather than ADD COLUMN, for two reasons: SQLite won't add a
-- column with a REFERENCES clause and a non-NULL default, and the name only
-- has to be unique per section now ("Favourites" for books and for movies).
-- collection_books refers to user_collections by name, so it follows the
-- renamed table; foreign keys are off while a migration runs.
--
-- Existing shelves: a shelf whose items are all movies (or all albums)
-- becomes a Movies (Music) shelf; everything else, empty and mixed shelves
-- included, is a Books shelf. A shelf still shows every item on it, whatever
-- its type.

CREATE TABLE user_collections_new (
    collection_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    media_type TEXT NOT NULL DEFAULT 'book' REFERENCES media_types(name),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE (user_id, media_type, name)
);

INSERT INTO user_collections_new (collection_id, user_id, name, media_type, created_at)
SELECT uc.collection_id, uc.user_id, uc.name,
       COALESCE((SELECT MIN(b.media_type)
                   FROM collection_books cb JOIN books b ON b.id = cb.book_id
                  WHERE cb.collection_id = uc.collection_id
                 HAVING COUNT(DISTINCT b.media_type) = 1), 'book'),
       uc.created_at
FROM user_collections uc;

DROP TABLE user_collections;
ALTER TABLE user_collections_new RENAME TO user_collections;
