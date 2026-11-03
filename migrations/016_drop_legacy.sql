-- 016: drop leftovers nothing uses any more (Phase 2.6).
--
--   discovered_books               cache for the removed Discover tab
--   users.allow_friend_discovery   from migration 012, never read
--   users.theme_mode, accent_color old appearance settings (replaced by
--                                  theme_style / color_mode in 013); only
--                                  databases from before the reskin have them
--
-- users is rebuilt with the columns that are kept, so this works whether or
-- not a given database has the legacy columns (ALTER TABLE DROP COLUMN fails
-- on a missing column). Code reads users rows by name, never by position.

DROP INDEX IF EXISTS idx_discovered_books_genre;
DROP INDEX IF EXISTS idx_discovered_books_cached_at;
DROP TABLE IF EXISTS discovered_books;
DELETE FROM sqlite_sequence WHERE name = 'discovered_books';

CREATE TEMP TABLE _seq AS SELECT seq FROM sqlite_sequence WHERE name = 'users';

CREATE TABLE users_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    is_admin INTEGER DEFAULT 0,
    avatar_url TEXT,
    reading_goal INTEGER DEFAULT 0,
    email_verified INTEGER DEFAULT 0,
    email_verification_sent_at TEXT,
    bio TEXT,
    default_privacy TEXT DEFAULT 'friends' CHECK(default_privacy IN ('private', 'friends', 'public')),
    theme_style TEXT NOT NULL DEFAULT 'house',
    color_mode TEXT NOT NULL DEFAULT 'system'
);
INSERT INTO users_new (id, username, email, password, is_active, is_admin, avatar_url, reading_goal,
                       email_verified, email_verification_sent_at, bio, default_privacy, theme_style, color_mode)
SELECT id, username, email, password, is_active, is_admin, avatar_url, reading_goal,
       email_verified, email_verification_sent_at, bio, default_privacy, theme_style, color_mode
FROM users;
DROP TABLE users;
ALTER TABLE users_new RENAME TO users;

UPDATE sqlite_sequence SET seq = MAX(seq, (SELECT seq FROM _seq)) WHERE name = 'users' AND EXISTS (SELECT 1 FROM _seq);
INSERT INTO sqlite_sequence (name, seq)
SELECT 'users', seq FROM _seq WHERE NOT EXISTS (SELECT 1 FROM sqlite_sequence WHERE name = 'users');
DROP TABLE _seq;
