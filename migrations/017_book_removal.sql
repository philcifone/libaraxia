-- 017: deaccession. A book that leaves the house (given away, sold, lost) is
-- marked removed instead of deleted, so its record, and everyone's reviews,
-- ratings and reading history on it, stay. Library views hide removed books.
-- Columns are appended at the end because some templates read books rows by
-- position.
ALTER TABLE books ADD COLUMN removed_at TIMESTAMP;   -- NULL = on the shelf
ALTER TABLE books ADD COLUMN removed_note TEXT;      -- e.g. 'Little Free Library'
