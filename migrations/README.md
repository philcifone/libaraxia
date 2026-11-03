# Database Migrations

SQL files in this directory, applied in name order by `manage.py`, which keeps a ledger in the `schema_migrations` table.

**Check which database you're touching first.** `manage.py` uses `--db PATH`, or else the same path as the app (`DATABASE_PATH`, default `library.db` in the working directory), and prints the absolute path before it does anything.

```bash
python3 manage.py status              # applied / pending
python3 manage.py migrate --dry-run   # what would run
python3 manage.py migrate             # back up, then apply pending (asks first)
```

- **New database:** `manage.py migrate` on a missing or empty file builds it from `create_database.sql` (which already contains 001–013) and then applies anything newer.
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
