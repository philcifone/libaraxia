-- Migration: Add reading_sessions table and migrate existing date_read data
-- This migration is SAFE and preserves all existing data
-- Run this on production database to enable multiple reading sessions per book

-- Step 1: Create the new reading_sessions table
CREATE TABLE IF NOT EXISTS reading_sessions (
    session_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    book_id INTEGER NOT NULL,
    date_started DATE,
    date_completed DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
);

-- Step 2: Create index for performance
CREATE INDEX IF NOT EXISTS idx_reading_sessions_user_book
ON reading_sessions(user_id, book_id);

-- Step 3: Migrate existing date_read data to reading_sessions
-- This creates one reading session per existing read_data entry with date_completed
INSERT INTO reading_sessions (user_id, book_id, date_started, date_completed, created_at)
SELECT
    user_id,
    book_id,
    NULL as date_started,  -- Old data didn't track start dates
    date_read as date_completed,
    CURRENT_TIMESTAMP as created_at
FROM read_data
WHERE date_read IS NOT NULL;

-- Step 4: Create new read_data table without date_read column
CREATE TABLE IF NOT EXISTS read_data_new (
    user_id INTEGER NOT NULL,
    book_id INTEGER NOT NULL,
    rating INTEGER,
    comment TEXT,
    PRIMARY KEY (user_id, book_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
);

-- Step 5: Copy existing ratings and comments to new table
INSERT INTO read_data_new (user_id, book_id, rating, comment)
SELECT user_id, book_id, rating, comment
FROM read_data;

-- Step 6: Drop old read_data table and rename new one
DROP TABLE read_data;
ALTER TABLE read_data_new RENAME TO read_data;

-- Migration complete!
-- Verify by running:
-- SELECT COUNT(*) FROM reading_sessions;
-- SELECT COUNT(*) FROM read_data;
