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

# If database is in instance folder (check with: ls instance/library.db)
sqlite3 instance/library.db < migrations/001_add_added_by_column.sql
sqlite3 instance/library.db < migrations/002_add_avatar_url.sql
sqlite3 instance/library.db < migrations/003_add_wishlist_table.sql
```

## Migration History

- `001_add_added_by_column.sql` - Adds added_by foreign key to books table to track which user added each book
- `002_add_avatar_url.sql` - Adds avatar_url and reading_goal columns to users table
- `003_add_wishlist_table.sql` - Creates wishlist table for tracking books users want to purchase
