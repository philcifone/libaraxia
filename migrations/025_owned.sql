-- 025: ownership separate from removal (ROADMAP 8B.3).
--
-- `owned` = 1: a copy on the owner's shelf (or one that was, see removed_at).
-- `owned` = 0: something they read, watched or listened to but never owned
-- (an audiobook from the library, a movie seen on TV). It's still theirs
-- (added_by), so reviews, statuses and sessions hang on it, but library grids,
-- searches and owned counts leave it out unless "Show: Not owned" is chosen.
--
-- Until now "not owned" was stored as removed (wishlist._keep_as_not_owned,
-- with this exact note). Those rows were never on the shelf, so they become
-- not owned instead of removed. Their "... but not owned" collection is kept.
--
-- ADD COLUMN, no rebuild: the library_* views select b.*, which SQLite
-- expands when a query is compiled, so they pick the column up.

ALTER TABLE books ADD COLUMN owned INTEGER NOT NULL DEFAULT 1 CHECK (owned IN (0, 1));

UPDATE books
   SET owned = 0, removed_at = NULL, removed_note = NULL
 WHERE removed_note = 'Removed from wishlist; not owned';
