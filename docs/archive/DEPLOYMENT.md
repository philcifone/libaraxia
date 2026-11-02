# Deployment Guide

## Database Migration for Activity Feed Feature

### Changes Made
1. Added `added_by` column to `books` table to track which user added each book
2. Updated activity feed to display "[username] added a new book" similar to reviews
3. Updated book addition code to record the user who adds books

### Pre-Deployment Checklist

1. **Backup your production database**
   ```bash
   cp library.db library.db.backup-$(date +%Y%m%d-%H%M%S)
   ```

2. **Verify your current database location**
   - Check your `.env` file for `DATABASE_PATH` variable
   - Default is `library.db` in the project root
   - Could also be in `instance/library.db`

### Migration Steps

#### Option 1: Using the migration script (Recommended)
```bash
# Navigate to your production directory
cd /path/to/libaraxia

# Backup first!
cp library.db library.db.backup

# Apply the migration
sqlite3 library.db < migrations/001_add_added_by_column.sql
```

#### Option 2: Manual SQL command
```bash
# Backup first!
cp library.db library.db.backup

# Run the ALTER TABLE command
sqlite3 library.db "ALTER TABLE books ADD COLUMN added_by INTEGER REFERENCES users(id);"
```

### Post-Migration

1. **Verify the migration**
   ```bash
   sqlite3 library.db "PRAGMA table_info(books);"
   ```
   You should see `added_by` as the last column (column 13).

2. **Optional: Attribute existing books to a user**
   If you want existing books (those added before this update) to show a username in the activity feed:
   ```bash
   # This will set all NULL added_by values to your first admin user
   sqlite3 library.db "UPDATE books SET added_by = (SELECT id FROM users WHERE is_admin = 1 LIMIT 1) WHERE added_by IS NULL;"
   ```

   Or attribute them to a specific user by username:
   ```bash
   sqlite3 library.db "UPDATE books SET added_by = (SELECT id FROM users WHERE username = 'your_username') WHERE added_by IS NULL;"
   ```

3. **Deploy code changes**
   ```bash
   git pull origin main
   # Or copy the updated files
   ```

4. **Restart your application**
   ```bash
   # If using systemd
   sudo systemctl restart libaraxia

   # If using docker
   docker-compose restart

   # If running manually with Flask
   # Stop the current process and restart
   python app.py
   ```

### Rollback (if needed)

If something goes wrong:
```bash
# Stop the application
# Restore the backup
cp library.db.backup library.db
# Restart the application
```

### Files Changed in This Update

- `blueprints/books.py` - Now records `added_by` when books are added
- `blueprints/feed.py` - Updated query to fetch username for book additions
- `templates/activity_feed.html` - Updated UI to display "[username] added a new book"
- `create_database.sql` - Updated schema documentation
- `migrations/001_add_added_by_column.sql` - Migration script (NEW)

### Notes

- Books added before this update will show "New Book Added" (without username) unless you run the optional attribution query
- Books added after this update will automatically show the username of who added them
- The `added_by` column can be NULL for backwards compatibility
