-- Migration: Add added_by column to books table
-- This tracks which user added each book to enable proper activity feed attribution
-- Date: 2025-10-13

-- Add the new column
ALTER TABLE books ADD COLUMN added_by INTEGER REFERENCES users(id);

-- Optional: Update existing books to set added_by to the first admin user
-- Uncomment if you want to attribute old books to someone:
-- UPDATE books SET added_by = (SELECT id FROM users WHERE is_admin = 1 LIMIT 1) WHERE added_by IS NULL;
