-- Migration: Add avatar_url column to users table
-- This allows users to upload and store their profile pictures

ALTER TABLE users ADD COLUMN avatar_url TEXT;
ALTER TABLE users ADD COLUMN reading_goal INTEGER DEFAULT 0;

-- Update existing users to have a reading goal of 0
UPDATE users SET reading_goal = 0 WHERE reading_goal IS NULL;
