-- Migration: Add friend requests and friendships tables
-- This enables users to send/accept friend requests and control profile privacy

-- Table to track friend requests (pending or declined)
CREATE TABLE IF NOT EXISTS friend_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sender_id INTEGER NOT NULL,  -- User who sent the request
    receiver_id INTEGER NOT NULL,  -- User who received the request
    status TEXT NOT NULL CHECK(status IN ('pending', 'declined')),  -- Request status
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (sender_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (receiver_id) REFERENCES users(id) ON DELETE CASCADE,
    -- Prevent duplicate requests between the same users
    UNIQUE(sender_id, receiver_id)
);

-- Table to track accepted friendships (bidirectional)
CREATE TABLE IF NOT EXISTS friendships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id_1 INTEGER NOT NULL,  -- First user in friendship
    user_id_2 INTEGER NOT NULL,  -- Second user in friendship
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id_1) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id_2) REFERENCES users(id) ON DELETE CASCADE,
    -- Ensure we don't have duplicate friendships
    -- Store in canonical order (smaller ID first)
    CHECK(user_id_1 < user_id_2),
    UNIQUE(user_id_1, user_id_2)
);

-- Index for quickly finding pending requests for a user
CREATE INDEX IF NOT EXISTS idx_friend_requests_receiver_pending
ON friend_requests(receiver_id, status) WHERE status = 'pending';

-- Index for finding all requests involving a user
CREATE INDEX IF NOT EXISTS idx_friend_requests_sender
ON friend_requests(sender_id);

-- Index for checking friendship status
CREATE INDEX IF NOT EXISTS idx_friendships_user1
ON friendships(user_id_1);

CREATE INDEX IF NOT EXISTS idx_friendships_user2
ON friendships(user_id_2);
