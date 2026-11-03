-- 014: remove rows that point at deleted books or users.
--
-- Foreign keys were never enforced (no PRAGMA foreign_keys = ON), so the
-- schema's ON DELETE CASCADE rules never fired and deletes left rows behind.
-- This clears them so foreign keys can be switched on (Phase 2.3).
--
-- Books are never deleted here: a book whose owner no longer exists becomes
-- unowned (added_by = NULL) instead. Everything else that points at a
-- missing book or user is deleted. Those rows can't be shown anywhere
-- today (the book or user they belong to is gone). The runner's backup
-- keeps a copy.
--
-- To see what this will remove first:  sqlite3 library.db 'PRAGMA foreign_key_check'

-- Owners / inviters that no longer exist: keep the row, drop the link.
UPDATE books SET added_by = NULL
 WHERE added_by IS NOT NULL AND added_by NOT IN (SELECT id FROM users);
UPDATE library_members SET added_by = NULL
 WHERE added_by IS NOT NULL AND added_by NOT IN (SELECT id FROM users);

-- Child rows of deleted books / users / custom collections.
-- Older databases declare collections' keys as books(book_id) / users(user_id),
-- columns that don't exist, so the pragma can't check that table ("foreign key
-- mismatch"). Check it by hand; 015 rebuilds it with correct keys.
DELETE FROM collections
 WHERE book_id NOT IN (SELECT id FROM books) OR user_id NOT IN (SELECT id FROM users);
DELETE FROM read_data                 WHERE rowid IN (SELECT rowid FROM pragma_foreign_key_check('read_data'));
DELETE FROM reading_sessions          WHERE rowid IN (SELECT rowid FROM pragma_foreign_key_check('reading_sessions'));
DELETE FROM book_tags                 WHERE rowid IN (SELECT rowid FROM pragma_foreign_key_check('book_tags'));
DELETE FROM wishlist                  WHERE rowid IN (SELECT rowid FROM pragma_foreign_key_check('wishlist'));
DELETE FROM user_collections          WHERE rowid IN (SELECT rowid FROM pragma_foreign_key_check('user_collections'));
DELETE FROM collection_books          WHERE rowid IN (SELECT rowid FROM pragma_foreign_key_check('collection_books'));
DELETE FROM activity_likes            WHERE rowid IN (SELECT rowid FROM pragma_foreign_key_check('activity_likes'));
DELETE FROM notifications             WHERE rowid IN (SELECT rowid FROM pragma_foreign_key_check('notifications'));
DELETE FROM friend_requests           WHERE rowid IN (SELECT rowid FROM pragma_foreign_key_check('friend_requests'));
DELETE FROM friendships               WHERE rowid IN (SELECT rowid FROM pragma_foreign_key_check('friendships'));
DELETE FROM email_verification_tokens WHERE rowid IN (SELECT rowid FROM pragma_foreign_key_check('email_verification_tokens'));
DELETE FROM library_members           WHERE rowid IN (SELECT rowid FROM pragma_foreign_key_check('library_members'));
