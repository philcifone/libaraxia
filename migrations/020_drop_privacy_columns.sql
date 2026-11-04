-- 020: drop the per-item privacy columns from migration 012 (Phase 4).
--
-- 012 added a private/friends/public `privacy` column to collections,
-- wishlist, reading_sessions and user_collections, plus users.default_privacy,
-- but nothing ever read them: every row was still the default 'friends' when
-- this was written (2026-11-04). The access rule that actually applies is the
-- circle (self + household + friends), see "Access Model" in CLAUDE.md.
-- Dropping them stops the schema claiming a privacy model the app doesn't
-- have. A real one, if ever wanted, should be designed from scratch.
--
-- Each column has only its own CHECK constraint, so ALTER TABLE DROP COLUMN
-- works once its index is gone (needs SQLite 3.35+). No table rebuild, so the
-- library_books view and the AUTOINCREMENT counters are untouched.

DROP INDEX IF EXISTS idx_collections_privacy;
DROP INDEX IF EXISTS idx_wishlist_privacy;

ALTER TABLE collections      DROP COLUMN privacy;
ALTER TABLE wishlist         DROP COLUMN privacy;
ALTER TABLE reading_sessions DROP COLUMN privacy;
ALTER TABLE user_collections DROP COLUMN privacy;
ALTER TABLE users            DROP COLUMN default_privacy;
