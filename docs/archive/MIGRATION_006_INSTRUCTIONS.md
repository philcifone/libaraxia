# Migration 006: Reading Sessions

## Overview
This migration adds support for tracking multiple reading sessions per book with start and end dates, while preserving all existing rating and review data.

## What Changes
- **New table**: `reading_sessions` - allows multiple reads of the same book with date_started and date_completed
- **Modified table**: `read_data` - removes `date_read` column (migrated to reading_sessions), keeps `rating` and `comment`
- All existing data is preserved and migrated automatically

## Pre-Migration Checklist
1. ✅ **Backup your database** before running this migration
2. ✅ Ensure you have SQLite 3.25.0 or later (for better foreign key support)
3. ✅ Stop the application to prevent concurrent writes during migration

## Running the Migration on Production

### Option 1: Using sqlite3 command line
```bash
# 1. Backup your database
cp library.db library.db.backup_$(date +%Y%m%d_%H%M%S)

# 2. Stop your application
sudo systemctl stop libaraxia  # adjust based on your service name

# 3. Run the migration
sqlite3 library.db < migrations/006_add_reading_sessions.sql

# 4. Verify the migration (should show counts of migrated data)
sqlite3 library.db "SELECT COUNT(*) as sessions FROM reading_sessions;"
sqlite3 library.db "SELECT COUNT(*) as reviews FROM read_data;"

# 5. Restart your application
sudo systemctl start libaraxia
```

### Option 2: Using Python script
```python
import sqlite3
from pathlib import Path

# Backup
import shutil
from datetime import datetime
backup_name = f"library.db.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
shutil.copy2('library.db', backup_name)
print(f"Backup created: {backup_name}")

# Run migration
conn = sqlite3.connect('library.db')
migration_sql = Path('migrations/006_add_reading_sessions.sql').read_text()
conn.executescript(migration_sql)
conn.commit()

# Verify
sessions = conn.execute("SELECT COUNT(*) FROM reading_sessions").fetchone()[0]
reviews = conn.execute("SELECT COUNT(*) FROM read_data").fetchone()[0]
print(f"Migration complete: {sessions} reading sessions, {reviews} reviews")
conn.close()
```

## What Happens During Migration

1. **Creates `reading_sessions` table** - new table for tracking multiple reads
2. **Migrates existing data** - all `date_read` values from `read_data` are copied to `reading_sessions` as `date_completed` (with `date_started = NULL` for old data)
3. **Recreates `read_data` table** - removes `date_read` column while preserving all ratings and comments
4. **Adds indexes** - for efficient querying of reading sessions

## Data Mapping
```
OLD read_data:
  user_id | book_id | date_read  | rating | comment
  1       | 42      | 2024-01-15 | 5      | "Great book!"

NEW structure:
  read_data:
    user_id | book_id | rating | comment
    1       | 42      | 5      | "Great book!"

  reading_sessions:
    session_id | user_id | book_id | date_started | date_completed | created_at
    1          | 1       | 42      | NULL         | 2024-01-15     | 2025-10-18 ...
```

## Verification Queries

After migration, verify data integrity:

```sql
-- Check all reading sessions were created
SELECT COUNT(*) as total_sessions FROM reading_sessions;

-- Check all reviews were preserved
SELECT COUNT(*) as total_reviews FROM read_data;

-- View a sample of migrated data
SELECT
    rs.session_id,
    b.title,
    rs.date_started,
    rs.date_completed,
    rd.rating,
    rd.comment
FROM reading_sessions rs
JOIN books b ON rs.book_id = b.id
LEFT JOIN read_data rd ON rs.user_id = rd.user_id AND rs.book_id = rd.book_id
LIMIT 5;
```

## Rollback (if needed)

If you need to rollback, restore from backup:

```bash
# Stop application
sudo systemctl stop libaraxia

# Restore backup
cp library.db.backup_YYYYMMDD_HHMMSS library.db

# Start application
sudo systemctl start libaraxia
```

## Next Steps After Migration

Once the migration is complete and verified:

1. The application will continue to work with existing functionality
2. You can now add UI to create/edit reading sessions with start/end dates
3. The `date_read` field in forms should be updated to use reading_sessions
4. Users will be able to log multiple reads of the same book

## Impact on Existing Code

The migration is designed to be **backward compatible**:
- ✅ Existing queries for `rating` and `comment` in `read_data` will work unchanged
- ⚠️ Queries referencing `read_data.date_read` will need to be updated to query `reading_sessions` instead
- ✅ All foreign key relationships are preserved

## Questions?
If you encounter any issues during migration, check:
1. Database file permissions
2. Available disk space (migration creates temporary tables)
3. SQLite version (`sqlite3 --version`)
