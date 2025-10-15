# Database Migrations

This directory contains SQL migration files for updating the database schema.

## Running Migrations

**Important:** Check where your database file is located first!

Run migrations in order:

```bash
# If database is in project root (check with: ls library.db)
sqlite3 library.db < migrations/001_add_added_by_column.sql
sqlite3 library.db < migrations/002_add_avatar_url.sql
sqlite3 library.db < migrations/003_add_wishlist_table.sql
sqlite3 library.db < migrations/004_add_collection_timestamps.sql
sqlite3 library.db < migrations/005_add_dismissed_activities.sql
```

## Migration History

- `001_add_added_by_column.sql` - Adds added_by foreign key to books table to track which user added each book
- `002_add_avatar_url.sql` - Adds avatar_url and reading_goal columns to users table
- `003_add_wishlist_table.sql` - Creates wishlist table for tracking books users want to purchase
- `004_add_collection_timestamps.sql`
 `005_add_dismissed_activities.sql`
