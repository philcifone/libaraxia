-- Migration: Add library members and privacy settings
-- This enables household/library sharing and privacy controls for social features

-- Table to track library membership (households/shared libraries)
-- Users in the same library group share their "My Library" view
CREATE TABLE IF NOT EXISTS library_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    library_id INTEGER NOT NULL,  -- Group/household ID
    user_id INTEGER NOT NULL,  -- User who is part of this library
    role TEXT DEFAULT 'member' CHECK(role IN ('owner', 'member')),  -- Future: different permissions
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    added_by INTEGER,  -- Who invited this user to the library
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (added_by) REFERENCES users(id) ON DELETE SET NULL,
    -- Each user can only be in one library at a time
    UNIQUE(user_id)
);

-- Index for finding all members of a library
CREATE INDEX IF NOT EXISTS idx_library_members_library
ON library_members(library_id);

-- Index for finding which library a user belongs to
CREATE INDEX IF NOT EXISTS idx_library_members_user
ON library_members(user_id);

-- Add privacy settings to collections
ALTER TABLE collections ADD COLUMN privacy TEXT DEFAULT 'friends' CHECK(privacy IN ('private', 'friends', 'public'));

-- Add privacy settings to wishlist
ALTER TABLE wishlist ADD COLUMN privacy TEXT DEFAULT 'friends' CHECK(privacy IN ('private', 'friends', 'public'));

-- Add privacy settings to reading_sessions
ALTER TABLE reading_sessions ADD COLUMN privacy TEXT DEFAULT 'friends' CHECK(privacy IN ('private', 'friends', 'public'));

-- Add privacy settings to user_collections (custom collections)
ALTER TABLE user_collections ADD COLUMN privacy TEXT DEFAULT 'friends' CHECK(privacy IN ('private', 'friends', 'public'));

-- Add user-level privacy preferences
ALTER TABLE users ADD COLUMN default_privacy TEXT DEFAULT 'friends' CHECK(default_privacy IN ('private', 'friends', 'public'));
ALTER TABLE users ADD COLUMN allow_friend_discovery INTEGER DEFAULT 1;  -- Can others find you in user search

-- Create index for privacy-aware queries
CREATE INDEX IF NOT EXISTS idx_collections_privacy
ON collections(user_id, privacy);

CREATE INDEX IF NOT EXISTS idx_wishlist_privacy
ON wishlist(user_id, privacy);

-- Note: Existing data will have privacy set to 'friends' by default
-- This means current behavior is preserved (friends can see everything)
