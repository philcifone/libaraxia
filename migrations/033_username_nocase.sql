-- 033: usernames are unique ignoring case (14c follow-up). Lookups stay
-- exact, but "Phil" and "phil" as two accounts would look the same in the
-- sidebar (it capitalizes) and on every page that names them. The app checks
-- this too (models.username_error); the index is the guarantee. It fails,
-- and so does the migration, if two existing names differ only by case:
-- rename one first.
CREATE UNIQUE INDEX idx_users_username_nocase ON users(username COLLATE NOCASE);
