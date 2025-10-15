-- Migration: Add dismissed_activities table
-- This table tracks which activity feed items have been dismissed globally

CREATE TABLE IF NOT EXISTS dismissed_activities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_type TEXT NOT NULL,  -- 'book_added', 'wishlist_added', 'collection_added', 'review_added'
    book_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,  -- The user whose activity this was
    dismissed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(activity_type, book_id, user_id)  -- Prevent duplicate dismissals
);

-- Index for faster lookups when filtering the activity feed
CREATE INDEX IF NOT EXISTS idx_dismissed_activities_lookup
ON dismissed_activities(activity_type, book_id, user_id);
