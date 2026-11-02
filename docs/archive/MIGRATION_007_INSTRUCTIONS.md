# Migration 007: Activity Likes System

## Overview
This migration adds a liking system to the activity feed, allowing users to like different types of activities (book additions, wishlist additions, collection updates, and reviews).

## Database Changes

### New Table: `activity_likes`
Tracks which users have liked which activity feed items.

**Columns:**
- `id` - Primary key
- `activity_type` - Type of activity ('book_added', 'wishlist_added', 'collection_added', 'review_added')
- `book_id` - ID of the book associated with the activity
- `activity_user_id` - ID of the user who performed the activity
- `liker_user_id` - ID of the user who liked the activity
- `liked_at` - Timestamp when the like was created

**Constraints:**
- Foreign key on `liker_user_id` referencing `users(id)` with CASCADE delete
- Foreign key on `book_id` referencing `books(id)` with CASCADE delete
- UNIQUE constraint on (activity_type, book_id, activity_user_id, liker_user_id) to prevent duplicate likes

**Indexes:**
- `idx_activity_likes_lookup` on (activity_type, book_id, activity_user_id) for fast activity like counts
- `idx_activity_likes_user` on (liker_user_id) for user's liked activities

## Production Deployment Instructions

### Step 1: Backup Database
```bash
# Create a backup before running the migration
cp library.db library.db.backup_$(date +%Y%m%d_%H%M%S)
```

### Step 2: Apply Migration
```bash
# Run the migration script
sqlite3 library.db < migrations/007_add_activity_likes.sql
```

### Step 3: Verify Migration
```bash
# Verify the table was created
sqlite3 library.db "SELECT sql FROM sqlite_master WHERE name='activity_likes';"

# Verify indexes were created
sqlite3 library.db "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='activity_likes';"
```

### Step 4: Test the Feature
1. Navigate to the activity feed
2. Click the heart icon on an activity
3. Verify the like count increases
4. Click the heart again to unlike
5. Verify the like count decreases

## Rollback Instructions
If you need to rollback this migration:

```bash
# Restore from backup
cp library.db.backup_YYYYMMDD_HHMMSS library.db

# OR manually remove the table
sqlite3 library.db "DROP TABLE IF EXISTS activity_likes;"
```

## Notes
- Users cannot like their own activities (enforced in application logic)
- Deleting a user will cascade delete all their likes
- Deleting a book will cascade delete all likes on activities related to that book
- The system uses AJAX for real-time like updates without page refresh
