-- Migration: Add notifications table
-- This table tracks notifications for users (like activity likes)

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,  -- The user receiving the notification
    type TEXT NOT NULL,  -- 'like', 'comment', etc. (extensible for future)
    message TEXT NOT NULL,  -- The notification message
    related_activity_type TEXT,  -- 'book_added', 'wishlist_added', 'collection_added', 'review_added'
    related_book_id INTEGER,
    from_user_id INTEGER,  -- The user who triggered the notification
    is_read INTEGER DEFAULT 0,  -- 0 = unread, 1 = read
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (from_user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (related_book_id) REFERENCES books(id) ON DELETE CASCADE
);

-- Index for faster lookups of unread notifications for a user
CREATE INDEX IF NOT EXISTS idx_notifications_user_unread
ON notifications(user_id, is_read);

-- Index for finding notifications by activity (for cleanup on unlike)
CREATE INDEX IF NOT EXISTS idx_notifications_activity
ON notifications(related_activity_type, related_book_id, from_user_id, user_id);
