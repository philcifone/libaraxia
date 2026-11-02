# Notification System - Implementation Summary

## Overview
A simple notification system has been implemented to alert users when someone likes their activity feed posts. Notifications appear as flash messages when users log in.

## How It Works

### When Someone Likes Your Activity
1. User A likes User B's activity (book addition, wishlist, collection update, or review)
2. A notification is created in the database for User B
3. The notification message includes:
   - Who liked it (User A's username)
   - What type of activity it was
   - The book title

### When You Log In
1. System checks for unread notifications
2. Displays up to 5 most recent notifications as flash messages (blue info style)
3. Marks all notifications as read after displaying

### When Someone Unlikes
- If someone unlikes your activity, the notification is deleted
- This prevents outdated notifications from appearing

## Database Structure

**New Table: `notifications`** (Migration 008)
```sql
notifications (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,           -- Recipient of notification
    type TEXT,                 -- 'like' (extensible for future)
    message TEXT,              -- Human-readable message
    related_activity_type TEXT,-- Original activity type
    related_book_id INTEGER,   -- Related book
    from_user_id INTEGER,      -- Who triggered it
    is_read INTEGER,           -- 0 = unread, 1 = read
    created_at TIMESTAMP
)
```

## Example Notifications

The system generates friendly messages like:
- "john_doe liked the book you added: The Great Gatsby"
- "jane_smith liked your wishlist addition: 1984"
- "alice liked your collection update: Pride and Prejudice"
- "bob liked your review of: To Kill a Mockingbird"

## Features

✅ **Smart Notification Creation**
- Only creates notification for NEW likes (not duplicate clicks)
- Includes book title in message for context
- Different messages for different activity types

✅ **Auto-Cleanup**
- Notifications deleted when activities are unliked
- Marked as read after being shown once
- CASCADE delete when users/books are deleted

✅ **Login Integration**
- Shows up to 5 most recent unread notifications
- Appears as blue "info" flash messages
- Automatically marks as read after display

✅ **Privacy**
- You don't get notified when you like something (can't like your own posts anyway)
- Notifications only go to the activity owner

## Files Modified

- `migrations/008_add_notifications.sql` (new) - Database schema
- `blueprints/feed.py` - Added notification creation/deletion in like/unlike routes
- `blueprints/auth.py` - Added notification check on login

## Future Enhancements

Possible additions:
- Notification bell icon with badge count
- Dedicated notifications page to view history
- Mark individual notifications as read/unread
- Notifications for other events (comments, follows, etc.)
- Real-time notifications (WebSocket/SSE)
- Email notifications for important events
- Notification preferences/settings

## Testing

To test the notification system:
1. Log in as User A
2. Like a post from User B
3. Log out
4. Log in as User B
5. You should see a flash message: "[User A] liked [your activity]"
6. The notification won't appear again on next login (marked as read)
7. If User A unlikes, the notification is removed from the database
