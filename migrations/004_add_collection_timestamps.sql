-- Migration: Add timestamp columns to collections table
-- This allows proper chronological ordering in activity feeds
-- Date: 2025-10-15

-- SQLite doesn't support adding columns with CURRENT_TIMESTAMP default in ALTER TABLE
-- So we need to use a multi-step approach

-- Step 1: Add columns without default values
ALTER TABLE collections ADD COLUMN created_at TIMESTAMP;
ALTER TABLE collections ADD COLUMN updated_at TIMESTAMP;

-- Step 2: Set default values for existing rows (use current time)
UPDATE collections SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL;
UPDATE collections SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL;

-- Step 3: Create index for faster queries by timestamp
CREATE INDEX IF NOT EXISTS idx_collections_created_at ON collections(created_at);
