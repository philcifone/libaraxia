from flask import Blueprint, request, jsonify, flash, redirect, url_for, render_template, current_app
from flask_login import login_required, current_user
from functools import wraps
from utils.database import get_db_connection
import sqlite3

friends_blueprint = Blueprint('friends', __name__, url_prefix='/friends')

def rate_limit(limit_string):
    """
    Decorator to apply rate limiting to a route.

    Args:
        limit_string: Rate limit specification (e.g., "30 per hour")
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Get the limiter from app extensions
            limiter = current_app.extensions.get('limiter')
            if limiter:
                # Check the rate limit
                limiter.limit(limit_string)(lambda: None)()
            return f(*args, **kwargs)
        return decorated_function
    return decorator


@friends_blueprint.route('/send_request/<username>', methods=['POST'])
@login_required
@rate_limit("30 per hour")
def send_request(username):
    """Send a friend request to another user"""
    conn = get_db_connection()
    try:
        # Get the target user
        target_user = conn.execute(
            'SELECT id, username FROM users WHERE username = ?',
            (username,)
        ).fetchone()

        if not target_user:
            flash('User not found!', 'danger')
            return redirect(url_for('base.index'))

        target_user_id = target_user['id']

        # Can't friend yourself
        if target_user_id == current_user.id:
            flash('You cannot send a friend request to yourself!', 'danger')
            return redirect(url_for('user.profile', username=username))

        # Check if already friends
        friendship = conn.execute('''
            SELECT id FROM friendships
            WHERE (user_id_1 = ? AND user_id_2 = ?)
               OR (user_id_1 = ? AND user_id_2 = ?)
        ''', (min(current_user.id, target_user_id), max(current_user.id, target_user_id),
              min(current_user.id, target_user_id), max(current_user.id, target_user_id))).fetchone()

        if friendship:
            flash(f'You are already friends with {username}!', 'info')
            return redirect(url_for('user.profile', username=username))

        # Check for existing pending request
        existing_request = conn.execute('''
            SELECT id, sender_id, status FROM friend_requests
            WHERE (sender_id = ? AND receiver_id = ?)
               OR (sender_id = ? AND receiver_id = ?)
        ''', (current_user.id, target_user_id, target_user_id, current_user.id)).fetchone()

        if existing_request:
            # If they sent us a request, auto-accept it instead
            if existing_request['sender_id'] == target_user_id and existing_request['status'] == 'pending':
                # Delete the request
                conn.execute('DELETE FROM friend_requests WHERE id = ?', (existing_request['id'],))

                # Create friendship
                conn.execute('''
                    INSERT INTO friendships (user_id_1, user_id_2)
                    VALUES (?, ?)
                ''', (min(current_user.id, target_user_id), max(current_user.id, target_user_id)))

                # Create notification for the other user
                conn.execute('''
                    INSERT INTO notifications (user_id, type, message, from_user_id)
                    VALUES (?, 'friend_accept', ?, ?)
                ''', (target_user_id, f'{current_user.username} accepted your friend request!', current_user.id))

                conn.commit()
                flash(f'You are now friends with {username}!', 'success')
                return redirect(url_for('user.profile', username=username))
            elif existing_request['status'] == 'pending':
                # We sent them a pending request
                flash(f'Friend request already sent to {username}!', 'info')
                return redirect(url_for('user.profile', username=username))
            elif existing_request['status'] == 'declined':
                # Request was declined, delete it and allow re-sending
                conn.execute('DELETE FROM friend_requests WHERE id = ?', (existing_request['id'],))
                # Continue to create new request below

        # Create new friend request (no need to create notification, we show from friend_requests table)
        conn.execute('''
            INSERT INTO friend_requests (sender_id, receiver_id, status)
            VALUES (?, ?, 'pending')
        ''', (current_user.id, target_user_id))

        conn.commit()
        flash(f'Friend request sent to {username}!', 'success')

    except sqlite3.IntegrityError:
        flash('Error sending friend request!', 'danger')
    finally:
        conn.close()

    return redirect(url_for('user.profile', username=username))


@friends_blueprint.route('/accept/<int:request_id>', methods=['POST'])
@login_required
@rate_limit("50 per hour")
def accept_request(request_id):
    """Accept a friend request"""
    conn = get_db_connection()
    try:
        # Get the friend request
        friend_request = conn.execute('''
            SELECT fr.*, u.username as sender_username
            FROM friend_requests fr
            JOIN users u ON fr.sender_id = u.id
            WHERE fr.id = ? AND fr.receiver_id = ? AND fr.status = 'pending'
        ''', (request_id, current_user.id)).fetchone()

        if not friend_request:
            flash('Friend request not found!', 'danger')
            return redirect(url_for('base.index'))

        sender_id = friend_request['sender_id']
        sender_username = friend_request['sender_username']

        # Delete the friend request
        conn.execute('DELETE FROM friend_requests WHERE id = ?', (request_id,))

        # Create the friendship
        conn.execute('''
            INSERT INTO friendships (user_id_1, user_id_2)
            VALUES (?, ?)
        ''', (min(current_user.id, sender_id), max(current_user.id, sender_id)))

        # Create notification for the sender
        conn.execute('''
            INSERT INTO notifications (user_id, type, message, from_user_id)
            VALUES (?, 'friend_accept', ?, ?)
        ''', (sender_id, f'{current_user.username} accepted your friend request!', current_user.id))

        conn.commit()
        flash(f'You are now friends with {sender_username}!', 'success')

    except sqlite3.IntegrityError:
        flash('Error accepting friend request!', 'danger')
    finally:
        conn.close()

    return redirect(request.referrer or url_for('base.index'))


@friends_blueprint.route('/decline/<int:request_id>', methods=['POST'])
@login_required
def decline_request(request_id):
    """Decline a friend request"""
    conn = get_db_connection()
    try:
        # Verify the request belongs to the current user
        friend_request = conn.execute('''
            SELECT id FROM friend_requests
            WHERE id = ? AND receiver_id = ? AND status = 'pending'
        ''', (request_id, current_user.id)).fetchone()

        if not friend_request:
            flash('Friend request not found!', 'danger')
            return redirect(url_for('base.index'))

        # Update status to declined (keep record to prevent re-sending)
        conn.execute('''
            UPDATE friend_requests
            SET status = 'declined', updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (request_id,))

        conn.commit()
        flash('Friend request declined.', 'info')

    finally:
        conn.close()

    return redirect(request.referrer or url_for('base.index'))


@friends_blueprint.route('/remove/<int:friend_id>', methods=['POST'])
@login_required
def remove_friend(friend_id):
    """Remove a friend"""
    conn = get_db_connection()
    try:
        # Get friend's username for the flash message
        friend = conn.execute(
            'SELECT username FROM users WHERE id = ?',
            (friend_id,)
        ).fetchone()

        if not friend:
            flash('User not found!', 'danger')
            return redirect(url_for('base.index'))

        # Delete the friendship
        result = conn.execute('''
            DELETE FROM friendships
            WHERE (user_id_1 = ? AND user_id_2 = ?)
               OR (user_id_1 = ? AND user_id_2 = ?)
        ''', (min(current_user.id, friend_id), max(current_user.id, friend_id),
              min(current_user.id, friend_id), max(current_user.id, friend_id)))

        if result.rowcount > 0:
            conn.commit()
            flash(f'Removed {friend["username"]} from friends.', 'info')
        else:
            flash('Friendship not found!', 'danger')

    finally:
        conn.close()

    return redirect(request.referrer or url_for('base.index'))


@friends_blueprint.route('/requests', methods=['GET'])
@login_required
def get_requests():
    """Get all pending friend requests for the current user (JSON API)"""
    conn = get_db_connection()
    try:
        requests = conn.execute('''
            SELECT fr.id, fr.sender_id, u.username, u.avatar_url, fr.created_at
            FROM friend_requests fr
            JOIN users u ON fr.sender_id = u.id
            WHERE fr.receiver_id = ? AND fr.status = 'pending'
            ORDER BY fr.created_at DESC
        ''', (current_user.id,)).fetchall()

        return jsonify([dict(r) for r in requests])

    finally:
        conn.close()


@friends_blueprint.route('/list', methods=['GET'])
@login_required
def get_friends():
    """Get all friends for the current user (JSON API)"""
    conn = get_db_connection()
    try:
        friends = conn.execute('''
            SELECT
                u.id, u.username, u.avatar_url,
                f.created_at as friends_since
            FROM friendships f
            JOIN users u ON (
                CASE
                    WHEN f.user_id_1 = ? THEN f.user_id_2
                    ELSE f.user_id_1
                END = u.id
            )
            WHERE f.user_id_1 = ? OR f.user_id_2 = ?
            ORDER BY u.username
        ''', (current_user.id, current_user.id, current_user.id)).fetchall()

        return jsonify([dict(f) for f in friends])

    finally:
        conn.close()


@friends_blueprint.route('/notifications_page', methods=['GET'])
@login_required
def notifications_page():
    """Display the notifications page"""
    conn = get_db_connection()
    try:
        # Get pending friend requests
        friend_requests = conn.execute('''
            SELECT
                fr.id,
                fr.sender_id,
                u.username,
                u.avatar_url,
                fr.created_at
            FROM friend_requests fr
            JOIN users u ON fr.sender_id = u.id
            WHERE fr.receiver_id = ? AND fr.status = 'pending'
            ORDER BY fr.created_at DESC
        ''', (current_user.id,)).fetchall()

        # Get all notifications (excluding friend_request type)
        notifications = conn.execute('''
            SELECT
                n.id,
                n.type,
                n.message,
                n.from_user_id,
                n.created_at,
                u.username as from_username,
                u.avatar_url as from_avatar_url,
                n.is_read
            FROM notifications n
            LEFT JOIN users u ON n.from_user_id = u.id
            WHERE n.user_id = ?
            AND n.type != 'friend_request'
            ORDER BY n.created_at DESC
            LIMIT 50
        ''', (current_user.id,)).fetchall()

        return render_template('notifications.html',
                             friend_requests=[dict(r) for r in friend_requests],
                             notifications=[dict(n) for n in notifications])
    finally:
        conn.close()


@friends_blueprint.route('/notification_count', methods=['GET'])
@login_required
def notification_count():
    """Get count of unread notifications and pending friend requests (JSON API)"""
    conn = get_db_connection()
    try:
        # Count pending friend requests
        friend_request_count = conn.execute('''
            SELECT COUNT(*) as count
            FROM friend_requests
            WHERE receiver_id = ? AND status = 'pending'
        ''', (current_user.id,)).fetchone()['count']

        # Count unread notifications (excluding friend_request type)
        notification_count = conn.execute('''
            SELECT COUNT(*) as count
            FROM notifications
            WHERE user_id = ? AND is_read = 0 AND type != 'friend_request'
        ''', (current_user.id,)).fetchone()['count']

        total_count = friend_request_count + notification_count

        return jsonify({
            'count': total_count,
            'friend_requests': friend_request_count,
            'notifications': notification_count
        })

    finally:
        conn.close()


@friends_blueprint.route('/dismiss_notification/<int:notification_id>', methods=['POST'])
@login_required
def dismiss_notification(notification_id):
    """Delete/dismiss a notification"""
    conn = get_db_connection()
    try:
        conn.execute('''
            DELETE FROM notifications
            WHERE id = ? AND user_id = ?
        ''', (notification_id, current_user.id))
        conn.commit()
        flash('Notification dismissed', 'info')
    except Exception as e:
        flash('Error dismissing notification', 'danger')
    finally:
        conn.close()

    return redirect(url_for('friends.notifications_page'))


@friends_blueprint.route('/mark_all_read', methods=['POST'])
@login_required
def mark_all_read():
    """Dismiss all notifications for the current user"""
    conn = get_db_connection()
    try:
        result = conn.execute('''
            DELETE FROM notifications
            WHERE user_id = ?
        ''', (current_user.id,))

        count = result.rowcount
        conn.commit()

        if count > 0:
            flash(f'Dismissed {count} notification{"s" if count != 1 else ""} as read', 'success')
        else:
            flash('No notifications to dismiss', 'info')
    except Exception as e:
        flash('Error dismissing notifications', 'danger')
    finally:
        conn.close()

    return redirect(url_for('friends.notifications_page'))


@friends_blueprint.route('/search_users', methods=['GET'])
@login_required
def search_users():
    """Search for users by username (JSON API)"""
    query = request.args.get('q', '').strip()

    if not query or len(query) < 2:
        return jsonify([])

    conn = get_db_connection()
    try:
        # Search for users by username, excluding current user
        users = conn.execute('''
            SELECT
                u.id,
                u.username,
                u.avatar_url,
                CASE
                    WHEN EXISTS (
                        SELECT 1 FROM friendships
                        WHERE (user_id_1 = ? AND user_id_2 = u.id)
                           OR (user_id_1 = u.id AND user_id_2 = ?)
                    ) THEN 'friends'
                    WHEN EXISTS (
                        SELECT 1 FROM friend_requests
                        WHERE sender_id = ? AND receiver_id = u.id AND status = 'pending'
                    ) THEN 'request_sent'
                    WHEN EXISTS (
                        SELECT 1 FROM friend_requests
                        WHERE sender_id = u.id AND receiver_id = ? AND status = 'pending'
                    ) THEN 'request_received'
                    ELSE 'none'
                END as friendship_status
            FROM users u
            WHERE u.username LIKE ? AND u.id != ?
            ORDER BY
                CASE
                    WHEN u.username LIKE ? THEN 0
                    ELSE 1
                END,
                u.username
            LIMIT 10
        ''', (current_user.id, current_user.id, current_user.id, current_user.id,
              f'%{query}%', current_user.id, f'{query}%')).fetchall()

        return jsonify([dict(u) for u in users])

    finally:
        conn.close()
