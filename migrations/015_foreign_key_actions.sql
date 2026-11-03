-- 015: give every foreign key a deliberate ON DELETE rule, before
-- foreign keys are switched on (Phase 2.3).
--
--   books.added_by                 -> SET NULL  (deleting a user never deletes books;
--                                                 the app asks who gets them first)
--   collections.user_id / book_id  -> CASCADE   (was: no action, which would make
--   user_collections.user_id       -> CASCADE    deletes fail once FKs are on)
--   collection_books.*             -> CASCADE
--   dismissed_activities.*         -> CASCADE   (had no FKs at all)
--   activity_likes.activity_user_id-> CASCADE   (had no FK)
--
-- Book deletes are limited in the app: a hard delete is refused while any
-- other user has reviews, statuses, sessions, tags or shelves on the book,
-- so these cascades only ever remove the owner's own rows.
--
-- SQLite can't alter a foreign key, so each table is rebuilt (the documented
-- 12-step procedure; the runner turns foreign keys off for this). Column
-- order is unchanged because some templates read rows by position.
-- collections.created_at/updated_at also get the CURRENT_TIMESTAMP default
-- that migration 004 meant to add (databases made before it had none).

-- Keep AUTOINCREMENT counters: dropping a table resets its sqlite_sequence row,
-- which would let new rows reuse ids of deleted ones.
CREATE TEMP TABLE _seq AS SELECT name, seq FROM sqlite_sequence;

-- ------------------------------------------------------------- books
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
    FOREIGN KEY (added_by) REFERENCES users(id) ON DELETE SET NULL
);
INSERT INTO books_new (id, title, author, publisher, publish_year, isbn, created_at, page_count,
                       cover_image_url, description, local_thumbnail, subtitle, genre, added_by)
SELECT id, title, author, publisher, publish_year, isbn, created_at, page_count,
       cover_image_url, description, local_thumbnail, subtitle, genre, added_by
FROM books;
DROP TABLE books;
ALTER TABLE books_new RENAME TO books;
CREATE INDEX idx_books_added_by ON books(added_by);

-- ------------------------------------------------------------- collections
CREATE TABLE collections_new (
    collection_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    book_id INTEGER NOT NULL,
    status TEXT CHECK(status IN ('read', 'want to read', 'currently reading', 'did not finish')) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    privacy TEXT DEFAULT 'friends' CHECK(privacy IN ('private', 'friends', 'public')),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
);
INSERT INTO collections_new (collection_id, user_id, book_id, status, created_at, updated_at, privacy)
SELECT collection_id, user_id, book_id, status, created_at, updated_at, privacy FROM collections;
DROP TABLE collections;
ALTER TABLE collections_new RENAME TO collections;
CREATE INDEX idx_collections_created_at ON collections(created_at);
CREATE INDEX idx_collections_privacy ON collections(user_id, privacy);

-- ------------------------------------------------------------- user_collections
CREATE TABLE user_collections_new (
    collection_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    privacy TEXT DEFAULT 'friends' CHECK(privacy IN ('private', 'friends', 'public')),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE (user_id, name)
);
INSERT INTO user_collections_new (collection_id, user_id, name, created_at, privacy)
SELECT collection_id, user_id, name, created_at, privacy FROM user_collections;
DROP TABLE user_collections;
ALTER TABLE user_collections_new RENAME TO user_collections;

-- ------------------------------------------------------------- collection_books
CREATE TABLE collection_books_new (
    collection_id INTEGER NOT NULL,
    book_id INTEGER NOT NULL,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (collection_id, book_id),
    FOREIGN KEY (collection_id) REFERENCES user_collections(collection_id) ON DELETE CASCADE,
    FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
);
INSERT INTO collection_books_new (collection_id, book_id, added_at)
SELECT collection_id, book_id, added_at FROM collection_books;
DROP TABLE collection_books;
ALTER TABLE collection_books_new RENAME TO collection_books;

-- ------------------------------------------------------------- dismissed_activities
DELETE FROM dismissed_activities
 WHERE book_id NOT IN (SELECT id FROM books) OR user_id NOT IN (SELECT id FROM users);
CREATE TABLE dismissed_activities_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_type TEXT NOT NULL,  -- 'book_added', 'wishlist_added', 'collection_added', 'review_added'
    book_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,     -- the user whose activity this was
    dismissed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(activity_type, book_id, user_id)
);
INSERT INTO dismissed_activities_new (id, activity_type, book_id, user_id, dismissed_at)
SELECT id, activity_type, book_id, user_id, dismissed_at FROM dismissed_activities;
DROP TABLE dismissed_activities;
ALTER TABLE dismissed_activities_new RENAME TO dismissed_activities;
CREATE INDEX idx_dismissed_activities_lookup ON dismissed_activities(activity_type, book_id, user_id);

-- ------------------------------------------------------------- activity_likes
DELETE FROM activity_likes WHERE activity_user_id NOT IN (SELECT id FROM users);
CREATE TABLE activity_likes_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_type TEXT NOT NULL,
    book_id INTEGER NOT NULL,
    activity_user_id INTEGER NOT NULL,  -- the user whose activity this is
    liker_user_id INTEGER NOT NULL,     -- the user who liked it
    liked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (activity_user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (liker_user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
    UNIQUE(activity_type, book_id, activity_user_id, liker_user_id)
);
INSERT INTO activity_likes_new (id, activity_type, book_id, activity_user_id, liker_user_id, liked_at)
SELECT id, activity_type, book_id, activity_user_id, liker_user_id, liked_at FROM activity_likes;
DROP TABLE activity_likes;
ALTER TABLE activity_likes_new RENAME TO activity_likes;
CREATE INDEX idx_activity_likes_lookup ON activity_likes(activity_type, book_id, activity_user_id);
CREATE INDEX idx_activity_likes_user ON activity_likes(liker_user_id);

-- Restore the AUTOINCREMENT counters.
UPDATE sqlite_sequence
   SET seq = (SELECT _seq.seq FROM _seq WHERE _seq.name = sqlite_sequence.name)
 WHERE name IN (SELECT name FROM _seq) AND seq < (SELECT _seq.seq FROM _seq WHERE _seq.name = sqlite_sequence.name);
INSERT INTO sqlite_sequence (name, seq)
SELECT name, seq FROM _seq WHERE name NOT IN (SELECT name FROM sqlite_sequence);
DROP TABLE _seq;
