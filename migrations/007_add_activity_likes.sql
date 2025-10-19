-- Migration: Add activity_likes table
-- This table tracks which users have liked which activity feed items

CREATE TABLE IF NOT EXISTS activity_likes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_type TEXT NOT NULL,  -- 'book_added', 'wishlist_added', 'collection_added', 'review_added'
    book_id INTEGER NOT NULL,
    activity_user_id INTEGER NOT NULL,  -- The user whose activity this is
    liker_user_id INTEGER NOT NULL,  -- The user who liked this activity
    liked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (liker_user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
    -- Prevent duplicate likes from the same user on the same activity
    UNIQUE(activity_type, book_id, activity_user_id, liker_user_id)
);

-- Index for faster lookups when querying likes for activities
CREATE INDEX IF NOT EXISTS idx_activity_likes_lookup
ON activity_likes(activity_type, book_id, activity_user_id);

-- Index for querying likes by user (useful for "liked by you" feature)
CREATE INDEX IF NOT EXISTS idx_activity_likes_user
ON activity_likes(liker_user_id);
