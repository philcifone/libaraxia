# Database Migrations

SQL files in this directory, applied in name order by `manage.py`, which keeps a ledger in the `schema_migrations` table.

**Check which database you're touching first.** `manage.py` uses `--db PATH`, or else the same path as the app (`DATABASE_PATH`, default `library.db` in the working directory), and prints the absolute path before it does anything.

```bash
python3 manage.py status              # applied / pending
python3 manage.py migrate --dry-run   # what would run
python3 manage.py migrate             # back up, then apply pending (asks first)
```

- **New database:** `manage.py migrate` on a missing or empty file builds it from `create_database.sql` (which already contains the migrations listed in its `schema_migrations` INSERT) and then applies anything newer.
- **Existing database from before the runner** (created by hand, at 013): run `python3 manage.py migrate --baseline` **once**. It records 001–013 as applied without running them. Plain `migrate` refuses to touch a database that has tables but no ledger.
- **Backups:** before changing anything, `migrate` writes `<db>.backup-YYYYMMDD-HHMMSS` next to the database using SQLite's online backup API, and checks it with `integrity_check`. `manage.py backup` does just that step.
- **Transactions:** each file runs in one transaction together with its ledger row, so it applies completely or not at all. Don't put `BEGIN`/`COMMIT` in a migration file; the runner refuses those.
- **Foreign keys** are off while a migration runs, so tables can be rebuilt (SQLite's 12-step `ALTER TABLE` procedure). The migration is rolled back if it leaves any `PRAGMA foreign_key_check` violations that weren't there before.

## Writing a migration

1. Add `migrations/NNN_short_name.sql` with the next number.
2. Test it on a **copy**: `cp library.db /tmp/x.db && python3 manage.py --db /tmp/x.db migrate`.
3. Either fold the change into `create_database.sql` and add the file name to its `schema_migrations` INSERT, or leave it out and let `migrate` apply it after the schema. Folding keeps fresh installs to one file. Check the result matches with a fresh DB: `manage.py --db /tmp/new.db migrate`.

## Migration History

- `001_add_added_by_column.sql` - Adds added_by foreign key to books table to track which user added each book
- `002_add_avatar_url.sql` - Adds avatar_url and reading_goal columns to users table
- `003_add_wishlist_table.sql` - Creates wishlist table for tracking books users want to purchase
- `004_add_collection_timestamps.sql`
- `005_add_dismissed_activities.sql`
- `006_add_reading_sessions.sql`
- `007_add_activity_likes.sql`
- `008_add_notifications.sql`
- `009_add_friend_requests.sql`
- `010_add_email_verification.sql`
- `011_add_bio.sql`
- `012_add_library_members_and_privacy.sql` - Adds library_members table for household sharing and privacy columns for social features
- `013_add_theme_preferences.sql` - Adds `theme_style` (house/classic) and `color_mode` (system/light/dark) to users for Profile → Appearance. The older `theme_mode`/`accent_color` columns are unused legacy.
- `014_cleanup_orphans.sql` - Deletes rows pointing at deleted books/users (left behind while foreign keys weren't enforced). Books whose owner is gone become unowned (`added_by = NULL`) rather than deleted. Data only; a no-op on a fresh DB.
- `015_foreign_key_actions.sql` - Rebuilds `books`, `collections`, `user_collections`, `collection_books`, `dismissed_activities`, `activity_likes` so every FK has a deliberate `ON DELETE` rule (`books.added_by` → `SET NULL`, the rest `CASCADE`), preserving AUTOINCREMENT counters and column order. Needed before `PRAGMA foreign_keys = ON`.
- `016_drop_legacy.sql` - Drops the `discovered_books` table (old Discover tab) and the unused `users` columns `allow_friend_discovery`, `theme_mode`, `accent_color`, by rebuilding `users` with the kept columns (works whether or not a DB has the legacy ones).
- `017_book_removal.sql` - Adds `books.removed_at` / `removed_note` for deaccession: books that leave the house are hidden from library views but keep their record, reviews and reading history.
- `018_library_books_view.sql` - Adds the `library_books` view: books with an owner that aren't the owner's own wishlist entry. Library pages, stats and filter options query it instead of repeating their own wishlist exclusion. A future table rebuild of `books` or `wishlist` must drop the view first and recreate it after.
- `019_clean_goodreads_reviews.sql` - Turns the `<br/>` tags the Goodreads import left in reviews into newlines (`<br/><br/>` = paragraph break). Data only; a no-op on a fresh DB. The importer now stores plain text.
- `020_drop_privacy_columns.sql` - Drops the never-used `privacy` columns (collections, wishlist, reading_sessions, user_collections) and `users.default_privacy` from 012, with their indexes. Access is the circle rule in CLAUDE.md's Access Model.
- `021_household_invites.sql` - Adds `household_invites` (joining a household needs the invitee's consent, see `utils/households.py`). Gives ownerless households to their longest-standing member and dissolves one-person households.
- `022_cover_jobs.sql` - Adds `cover_jobs` (background cover fetching, `utils/cover_jobs.py`).
- `023_add_videos.sql` - Videos (Phase 8): `books.media_type` ('book'/'video'), `format`, `barcode` (EAN-13), `catalog_number`, `runtime_minutes`, appended; rebuilds `collections` so its status CHECK allows 'watched' and 'want to watch'; `library_books` becomes books only and `library_videos` is added. See `utils/media.py`.
- `025_owned.sql` - Adds `books.owned` (0 = read/watched/listened to but never owned, ROADMAP 8B.3). Rows stored as "removed from wishlist; not owned" become not owned instead of removed.
- `026_accent.sql` - Adds `users.accent` (Profile → Appearance accent colour, ROADMAP 8B.5; House style only).
- `027_shelf_types.sql` - Custom shelves get a `media_type` (Books / Movies / Music tabs on Collections, ROADMAP 8C); names unique per section. Rebuilds `user_collections`; a shelf holding only movies or only albums becomes that section's, every other shelf a Books one.
- `028_font.sql` - Adds `users.font` (Profile → Appearance → Font).
- `029_reading_goals.sql` - Reading goals per year (`reading_goals`, ROADMAP 12.3); the existing `users.reading_goal` becomes this year's row and the column is left unused.
