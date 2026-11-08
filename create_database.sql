-- Libaraxia: complete schema for a NEW database.
--
--   sqlite3 library.db < create_database.sql
--
-- This is the result of every migration up to and including the last one
-- listed in schema_migrations at the bottom. Existing databases are upgraded
-- with `python3 manage.py migrate` instead; never run this file against them.
--
-- When you add a migration, either fold it in here (and add its row to the
-- schema_migrations INSERT), or leave it out and let `manage.py migrate`
-- apply it after this file.

-- ---------------------------------------------------------------- users

CREATE TABLE users (
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
    theme_style TEXT NOT NULL DEFAULT 'house',
    color_mode TEXT NOT NULL DEFAULT 'system'
);

CREATE TABLE email_verification_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    token TEXT NOT NULL UNIQUE,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    expires_at TEXT NOT NULL,
    used INTEGER DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX idx_verification_tokens_token ON email_verification_tokens(token);
CREATE INDEX idx_verification_tokens_user_id ON email_verification_tokens(user_id);

-- ---------------------------------------------------------------- books

-- Shared catalogue. added_by is the owner (NULL = unowned; deleting a user
-- never deletes books, see migration 015). Wishlist entries are also rows
-- here (plus a wishlist row), so library queries must exclude them.
CREATE TABLE books (
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
    removed_at TIMESTAMP,   -- set when the book leaves the library (deaccession); NULL = on the shelf
    removed_note TEXT,
    -- Videos (migration 023, utils/media.py): a video is a row with media_type 'video'
    media_type TEXT NOT NULL DEFAULT 'book' CHECK (media_type IN ('book', 'video')),
    format TEXT,            -- video format: 'VHS', ...
    barcode TEXT,           -- normalised EAN-13 (UPC-A with a leading 0)
    catalog_number TEXT,    -- studio catalogue number
    runtime_minutes INTEGER,
    FOREIGN KEY (added_by) REFERENCES users(id) ON DELETE SET NULL
);
CREATE INDEX idx_books_added_by ON books(added_by);
CREATE INDEX idx_books_media_type ON books(media_type);
CREATE INDEX idx_books_barcode ON books(barcode);

-- Per-user reading (or, for videos, watching) status.
CREATE TABLE collections (
    collection_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    book_id INTEGER NOT NULL,
    status TEXT CHECK(status IN ('read', 'want to read', 'currently reading', 'did not finish',
                                 'watched', 'want to watch')) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
);
CREATE INDEX idx_collections_created_at ON collections(created_at);

-- Rating and review.
CREATE TABLE read_data (
    user_id INTEGER NOT NULL,
    book_id INTEGER NOT NULL,
    rating INTEGER,
    comment TEXT,
    PRIMARY KEY (user_id, book_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
);

CREATE TABLE reading_sessions (
    session_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    book_id INTEGER NOT NULL,
    date_started DATE,
    date_completed DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
);
CREATE INDEX idx_reading_sessions_user_book ON reading_sessions(user_id, book_id);

CREATE TABLE book_tags (
    tag_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    book_id INTEGER NOT NULL,
    tag_name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
    UNIQUE(user_id, book_id, tag_name)
);
CREATE INDEX idx_book_tags_user_book ON book_tags(user_id, book_id);

-- Custom user collections ("shelves").
CREATE TABLE user_collections (
    collection_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE (user_id, name)
);

CREATE TABLE collection_books (
    collection_id INTEGER NOT NULL,
    book_id INTEGER NOT NULL,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (collection_id, book_id),
    FOREIGN KEY (collection_id) REFERENCES user_collections(collection_id) ON DELETE CASCADE,
    FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
);

CREATE TABLE wishlist (
    wishlist_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    book_id INTEGER NOT NULL,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes TEXT,
    purchase_link TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
    UNIQUE(user_id, book_id)
);
CREATE INDEX idx_wishlist_user ON wishlist(user_id);

-- ---------------------------------------------------------------- feed

CREATE TABLE dismissed_activities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_type TEXT NOT NULL,  -- 'book_added', 'wishlist_added', 'collection_added', 'review_added'
    book_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,     -- the user whose activity this was
    dismissed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(activity_type, book_id, user_id)
);
CREATE INDEX idx_dismissed_activities_lookup ON dismissed_activities(activity_type, book_id, user_id);

CREATE TABLE activity_likes (
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
CREATE INDEX idx_activity_likes_lookup ON activity_likes(activity_type, book_id, activity_user_id);
CREATE INDEX idx_activity_likes_user ON activity_likes(liker_user_id);

CREATE TABLE notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,       -- recipient
    type TEXT NOT NULL,             -- 'like', 'friend_request', ...
    message TEXT NOT NULL,
    related_activity_type TEXT,
    related_book_id INTEGER,
    from_user_id INTEGER,           -- who triggered it
    is_read INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (from_user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (related_book_id) REFERENCES books(id) ON DELETE CASCADE
);
CREATE INDEX idx_notifications_user_unread ON notifications(user_id, is_read);
CREATE INDEX idx_notifications_activity ON notifications(related_activity_type, related_book_id, from_user_id, user_id);

-- ---------------------------------------------------------------- social

CREATE TABLE friend_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sender_id INTEGER NOT NULL,
    receiver_id INTEGER NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('pending', 'declined')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (sender_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (receiver_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(sender_id, receiver_id)
);
CREATE INDEX idx_friend_requests_receiver_pending ON friend_requests(receiver_id, status) WHERE status = 'pending';
CREATE INDEX idx_friend_requests_sender ON friend_requests(sender_id);

-- Stored in canonical order: user_id_1 < user_id_2.
CREATE TABLE friendships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id_1 INTEGER NOT NULL,
    user_id_2 INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id_1) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id_2) REFERENCES users(id) ON DELETE CASCADE,
    CHECK(user_id_1 < user_id_2),
    UNIQUE(user_id_1, user_id_2)
);
CREATE INDEX idx_friendships_user1 ON friendships(user_id_1);
CREATE INDEX idx_friendships_user2 ON friendships(user_id_2);

-- Households: members of one library_id see each other's books.
CREATE TABLE library_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    library_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    role TEXT DEFAULT 'member' CHECK(role IN ('owner', 'member')),
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    added_by INTEGER,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (added_by) REFERENCES users(id) ON DELETE SET NULL,
    UNIQUE(user_id)  -- one library per user
);
CREATE INDEX idx_library_members_library ON library_members(library_id);
CREATE INDEX idx_library_members_user ON library_members(user_id);

-- Pending invites to join a household (deleted on accept/decline/cancel).
CREATE TABLE household_invites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    inviter_id INTEGER NOT NULL,
    invitee_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (inviter_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (invitee_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE (inviter_id, invitee_id)
);
CREATE INDEX idx_household_invites_invitee ON household_invites(invitee_id);

-- Background "fetch missing covers" runs (utils/cover_jobs.py, migration 022).
CREATE TABLE cover_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,                  -- who started it (and sees its progress)
    scope TEXT NOT NULL CHECK (scope IN ('own', 'all')),
    status TEXT NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'done', 'cancelled')),
    total INTEGER NOT NULL DEFAULT 0,          -- books missing a cover when it started
    checked INTEGER NOT NULL DEFAULT 0,
    found INTEGER NOT NULL DEFAULT 0,
    last_book_id INTEGER NOT NULL DEFAULT 0,   -- cursor: books are done in id order
    worker TEXT,                               -- process working on it
    heartbeat_at TIMESTAMP,                    -- stale => another process may take over
    dismissed INTEGER NOT NULL DEFAULT 0,      -- hidden from the progress panel
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX idx_cover_jobs_user ON cover_jobs(user_id, dismissed);
CREATE INDEX idx_cover_jobs_status ON cover_jobs(status);

-- ---------------------------------------------------------------- views

-- Books on their owner's shelf: owned, and not the owner's own wishlist entry.
-- Includes removed books (filter on removed_at). See migrations 018 and 023.
-- Books only: videos are in library_videos.
-- A table rebuild of books or wishlist must drop and recreate these views.
CREATE VIEW library_books AS
SELECT b.*
FROM books b
WHERE b.media_type = 'book'
  AND b.added_by IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM wishlist w
      WHERE w.book_id = b.id AND w.user_id = b.added_by
  );

-- Videos on their owner's shelf (the Videos section). Same rule as above.
CREATE VIEW library_videos AS
SELECT b.*
FROM books b
WHERE b.media_type = 'video'
  AND b.added_by IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM wishlist w
      WHERE w.book_id = b.id AND w.user_id = b.added_by
  );

-- ---------------------------------------------------------------- migrations

-- Ledger used by `manage.py migrate`. Lists every migration already folded
-- into this file, so the runner skips them on a fresh database.
CREATE TABLE schema_migrations (
    name TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO schema_migrations (name) VALUES
    ('001_add_added_by_column.sql'),
    ('002_add_avatar_url.sql'),
    ('003_add_wishlist_table.sql'),
    ('004_add_collection_timestamps.sql'),
    ('005_add_dismissed_activities.sql'),
    ('006_add_reading_sessions.sql'),
    ('007_add_activity_likes.sql'),
    ('008_add_notifications.sql'),
    ('009_add_friend_requests.sql'),
    ('010_add_email_verification.sql'),
    ('011_add_bio.sql'),
    ('012_add_library_members_and_privacy.sql'),
    ('013_add_theme_preferences.sql'),
    ('014_cleanup_orphans.sql'),
    ('015_foreign_key_actions.sql'),
    ('016_drop_legacy.sql'),
    ('017_book_removal.sql'),
    ('018_library_books_view.sql'),
    ('019_clean_goodreads_reviews.sql'),
    ('020_drop_privacy_columns.sql'),
    ('021_household_invites.sql'),
    ('022_cover_jobs.sql'),
    ('023_add_videos.sql');
