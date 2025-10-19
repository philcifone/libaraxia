from flask import render_template, Blueprint, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from utils.database import get_db_connection

feed_blueprint = Blueprint('feed', __name__, template_folder='templates')


@feed_blueprint.route("/activity")
@login_required
def activity_feed():
    """Display a social feed of recent book additions and reviews"""
    conn = get_db_connection()
    try:
        # Fetch recent book additions to main library (last 20)
        # Only show books added directly to library (not through wishlist)
        # Exclude dismissed activities
        recent_books = conn.execute("""
            SELECT
                b.id,
                b.title,
                b.author,
                b.cover_image_url,
                b.created_at,
                b.genre,
                b.added_by,
                u.username,
                'book_added' as activity_type
            FROM books b
            LEFT JOIN users u ON b.added_by = u.id
            WHERE b.id NOT IN (
                SELECT book_id FROM wishlist
            )
            AND NOT EXISTS (
                SELECT 1 FROM dismissed_activities da
                WHERE da.activity_type = 'book_added'
                AND da.book_id = b.id
                AND da.user_id = b.added_by
            )
            ORDER BY b.created_at DESC
            LIMIT 20
        """).fetchall()

        # Fetch recent wishlist additions (last 20)
        # Exclude dismissed activities
        recent_wishlist = conn.execute("""
            SELECT
                w.book_id,
                w.user_id,
                w.added_at,
                b.title,
                b.author,
                b.cover_image_url,
                b.genre,
                u.username,
                'wishlist_added' as activity_type
            FROM wishlist w
            JOIN books b ON w.book_id = b.id
            JOIN users u ON w.user_id = u.id
            WHERE NOT EXISTS (
                SELECT 1 FROM dismissed_activities da
                WHERE da.activity_type = 'wishlist_added'
                AND da.book_id = w.book_id
                AND da.user_id = w.user_id
            )
            ORDER BY w.added_at DESC
            LIMIT 20
        """).fetchall()

        # Fetch recent collections additions (books moved to library from wishlist or status changes)
        # Exclude dismissed activities
        recent_collections = conn.execute("""
            SELECT
                c.collection_id,
                c.user_id,
                c.book_id,
                c.status,
                c.created_at,
                b.title,
                b.author,
                b.cover_image_url,
                u.username,
                'collection_added' as activity_type
            FROM collections c
            JOIN books b ON c.book_id = b.id
            JOIN users u ON c.user_id = u.id
            WHERE c.status IN ('currently reading', 'want to read')
            AND NOT EXISTS (
                SELECT 1 FROM dismissed_activities da
                WHERE da.activity_type = 'collection_added'
                AND da.book_id = c.book_id
                AND da.user_id = c.user_id
            )
            ORDER BY c.created_at DESC
            LIMIT 20
        """).fetchall()

        # Fetch recent reviews/ratings (last 20)
        # Exclude dismissed activities
        recent_reviews = conn.execute("""
            SELECT
                r.user_id,
                r.book_id,
                (SELECT MAX(date_completed) FROM reading_sessions
                 WHERE book_id = r.book_id AND user_id = r.user_id) as date_read,
                r.rating,
                r.comment,
                b.title,
                b.author,
                b.cover_image_url,
                u.username,
                'review_added' as activity_type
            FROM read_data r
            JOIN books b ON r.book_id = b.id
            JOIN users u ON r.user_id = u.id
            WHERE (r.rating IS NOT NULL OR r.comment IS NOT NULL)
            AND NOT EXISTS (
                SELECT 1 FROM dismissed_activities da
                WHERE da.activity_type = 'review_added'
                AND da.book_id = r.book_id
                AND da.user_id = r.user_id
            )
            ORDER BY date_read DESC
            LIMIT 20
        """).fetchall()

        # Combine and sort all activities by date
        activities = []

        for book in recent_books:
            # Get like count for this activity
            like_data = conn.execute("""
                SELECT COUNT(*) as like_count,
                       COALESCE(SUM(CASE WHEN liker_user_id = ? THEN 1 ELSE 0 END), 0) as user_liked
                FROM activity_likes
                WHERE activity_type = 'book_added' AND book_id = ? AND activity_user_id = ?
            """, (current_user.id, book['id'], book['added_by'])).fetchone()

            activities.append({
                'type': 'book_added',
                'date': book['created_at'],
                'book_id': book['id'],
                'title': book['title'],
                'author': book['author'],
                'cover_image_url': book['cover_image_url'],
                'genre': book['genre'],
                'username': book['username'],
                'user_id': book['added_by'],
                'like_count': like_data['like_count'],
                'user_liked': like_data['user_liked'] > 0
            })

        for wishlist_item in recent_wishlist:
            # Get like count for this activity
            like_data = conn.execute("""
                SELECT COUNT(*) as like_count,
                       COALESCE(SUM(CASE WHEN liker_user_id = ? THEN 1 ELSE 0 END), 0) as user_liked
                FROM activity_likes
                WHERE activity_type = 'wishlist_added' AND book_id = ? AND activity_user_id = ?
            """, (current_user.id, wishlist_item['book_id'], wishlist_item['user_id'])).fetchone()

            activities.append({
                'type': 'wishlist_added',
                'date': wishlist_item['added_at'],
                'book_id': wishlist_item['book_id'],
                'title': wishlist_item['title'],
                'author': wishlist_item['author'],
                'cover_image_url': wishlist_item['cover_image_url'],
                'genre': wishlist_item['genre'],
                'username': wishlist_item['username'],
                'user_id': wishlist_item['user_id'],
                'like_count': like_data['like_count'],
                'user_liked': like_data['user_liked'] > 0
            })

        for collection in recent_collections:
            # Get like count for this activity
            like_data = conn.execute("""
                SELECT COUNT(*) as like_count,
                       COALESCE(SUM(CASE WHEN liker_user_id = ? THEN 1 ELSE 0 END), 0) as user_liked
                FROM activity_likes
                WHERE activity_type = 'collection_added' AND book_id = ? AND activity_user_id = ?
            """, (current_user.id, collection['book_id'], collection['user_id'])).fetchone()

            activities.append({
                'type': 'collection_added',
                'date': collection['created_at'],
                'book_id': collection['book_id'],
                'collection_id': collection['collection_id'],
                'title': collection['title'],
                'author': collection['author'],
                'cover_image_url': collection['cover_image_url'],
                'username': collection['username'],
                'user_id': collection['user_id'],
                'status': collection['status'],
                'like_count': like_data['like_count'],
                'user_liked': like_data['user_liked'] > 0
            })

        for review in recent_reviews:
            # Get like count for this activity
            like_data = conn.execute("""
                SELECT COUNT(*) as like_count,
                       COALESCE(SUM(CASE WHEN liker_user_id = ? THEN 1 ELSE 0 END), 0) as user_liked
                FROM activity_likes
                WHERE activity_type = 'review_added' AND book_id = ? AND activity_user_id = ?
            """, (current_user.id, review['book_id'], review['user_id'])).fetchone()

            activities.append({
                'type': 'review_added',
                'date': review['date_read'],
                'book_id': review['book_id'],
                'title': review['title'],
                'author': review['author'],
                'cover_image_url': review['cover_image_url'],
                'username': review['username'],
                'user_id': review['user_id'],
                'rating': review['rating'],
                'comment': review['comment'],
                'like_count': like_data['like_count'],
                'user_liked': like_data['user_liked'] > 0
            })

        # Sort by date, most recent first
        activities.sort(key=lambda x: x['date'] if x['date'] else '', reverse=True)

        # Limit to 30 most recent activities
        activities = activities[:30]

        return render_template("activity_feed.html", activities=activities)

    finally:
        conn.close()


@feed_blueprint.route("/dismiss_activity", methods=["POST"])
@login_required
def dismiss_activity():
    """Dismiss an activity item from the feed globally (for all users)"""
    activity_type = request.form.get('activity_type')
    book_id = request.form.get('book_id')
    user_id = request.form.get('user_id')

    if not activity_type or not book_id or not user_id:
        flash('Invalid request', 'error')
        return redirect(url_for('feed.activity_feed'))

    conn = get_db_connection()
    try:
        # Insert into dismissed_activities table
        # The UNIQUE constraint will prevent duplicates
        conn.execute("""
            INSERT OR IGNORE INTO dismissed_activities (activity_type, book_id, user_id)
            VALUES (?, ?, ?)
        """, (activity_type, book_id, user_id))

        conn.commit()
        flash('Activity dismissed from feed', 'success')

    except Exception as e:
        flash(f'Error dismissing activity: {str(e)}', 'error')
    finally:
        conn.close()

    return redirect(url_for('feed.activity_feed'))


@feed_blueprint.route("/like_activity", methods=["POST"])
@login_required
def like_activity():
    """Like an activity item in the feed"""
    data = request.get_json()
    activity_type = data.get('activity_type')
    book_id = data.get('book_id')
    activity_user_id = data.get('activity_user_id')

    if not activity_type or not book_id or not activity_user_id:
        return jsonify({'success': False, 'error': 'Invalid request'}), 400

    # Users cannot like their own activities
    if int(activity_user_id) == current_user.id:
        return jsonify({'success': False, 'error': 'Cannot like your own activity'}), 400

    conn = get_db_connection()
    try:
        # Check if this is a new like (not already liked)
        existing_like = conn.execute("""
            SELECT id FROM activity_likes
            WHERE activity_type = ? AND book_id = ? AND activity_user_id = ? AND liker_user_id = ?
        """, (activity_type, book_id, activity_user_id, current_user.id)).fetchone()

        # Insert like (will be ignored if already exists due to UNIQUE constraint)
        conn.execute("""
            INSERT OR IGNORE INTO activity_likes (activity_type, book_id, activity_user_id, liker_user_id)
            VALUES (?, ?, ?, ?)
        """, (activity_type, book_id, activity_user_id, current_user.id))

        # If this is a new like, create a notification
        if not existing_like:
            # Get book title for the notification message
            book = conn.execute("SELECT title FROM books WHERE id = ?", (book_id,)).fetchone()
            book_title = book['title'] if book else 'your activity'

            # Create activity type friendly message
            activity_messages = {
                'book_added': f'liked the book you added: {book_title}',
                'wishlist_added': f'liked your wishlist addition: {book_title}',
                'collection_added': f'liked your collection update: {book_title}',
                'review_added': f'liked your review of: {book_title}'
            }
            message = f"{current_user.username} {activity_messages.get(activity_type, 'liked your activity')}"

            # Insert notification
            conn.execute("""
                INSERT INTO notifications (user_id, type, message, related_activity_type, related_book_id, from_user_id)
                VALUES (?, 'like', ?, ?, ?, ?)
            """, (activity_user_id, message, activity_type, book_id, current_user.id))

        conn.commit()

        # Get updated like count
        like_count = conn.execute("""
            SELECT COUNT(*) as count
            FROM activity_likes
            WHERE activity_type = ? AND book_id = ? AND activity_user_id = ?
        """, (activity_type, book_id, activity_user_id)).fetchone()['count']

        return jsonify({'success': True, 'like_count': like_count})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


@feed_blueprint.route("/unlike_activity", methods=["POST"])
@login_required
def unlike_activity():
    """Unlike an activity item in the feed"""
    data = request.get_json()
    activity_type = data.get('activity_type')
    book_id = data.get('book_id')
    activity_user_id = data.get('activity_user_id')

    if not activity_type or not book_id or not activity_user_id:
        return jsonify({'success': False, 'error': 'Invalid request'}), 400

    conn = get_db_connection()
    try:
        # Remove like
        conn.execute("""
            DELETE FROM activity_likes
            WHERE activity_type = ? AND book_id = ? AND activity_user_id = ? AND liker_user_id = ?
        """, (activity_type, book_id, activity_user_id, current_user.id))

        # Also delete the notification for this like
        conn.execute("""
            DELETE FROM notifications
            WHERE type = 'like'
            AND related_activity_type = ?
            AND related_book_id = ?
            AND user_id = ?
            AND from_user_id = ?
        """, (activity_type, book_id, activity_user_id, current_user.id))

        conn.commit()

        # Get updated like count
        like_count = conn.execute("""
            SELECT COUNT(*) as count
            FROM activity_likes
            WHERE activity_type = ? AND book_id = ? AND activity_user_id = ?
        """, (activity_type, book_id, activity_user_id)).fetchone()['count']

        return jsonify({'success': True, 'like_count': like_count})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()
