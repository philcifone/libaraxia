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
    default_privacy TEXT DEFAULT 'friends' CHECK(default_privacy IN ('private', 'friends', 'public')),
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
    FOREIGN KEY (added_by) REFERENCES users(id) ON DELETE SET NULL
);
CREATE INDEX idx_books_added_by ON books(added_by);

-- Per-user reading status.
CREATE TABLE collections (
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
CREATE INDEX idx_collections_created_at ON collections(created_at);
CREATE INDEX idx_collections_privacy ON collections(user_id, privacy);

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
    privacy TEXT DEFAULT 'friends' CHECK(privacy IN ('private', 'friends', 'public')),
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
    privacy TEXT DEFAULT 'friends' CHECK(privacy IN ('private', 'friends', 'public')),
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
    privacy TEXT DEFAULT 'friends' CHECK(privacy IN ('private', 'friends', 'public')),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
    UNIQUE(user_id, book_id)
);
CREATE INDEX idx_wishlist_user ON wishlist(user_id);
CREATE INDEX idx_wishlist_privacy ON wishlist(user_id, privacy);

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
    ('016_drop_legacy.sql');
