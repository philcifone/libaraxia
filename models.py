from flask_login import UserMixin
from functools import wraps
from flask import abort, redirect, url_for
from flask_login import current_user
from utils.database import get_db_connection

class User(UserMixin):
    def __init__(self, id, username, email, is_active=True, is_admin=False, avatar_url=None, email_verified=True, bio=None):
        self.id = id
        self.username = username
        self.email = email
        self._is_active = is_active
        self.is_admin = is_admin
        self.avatar_url = avatar_url
        self.email_verified = email_verified
        self.bio = bio

    def get_id(self):
        return str(self.id)

    @property
    def is_active(self):
        return self._is_active

def admin_required(f):
    """Decorator to restrict access to admin users only."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # First, check if any users exist in the database
        conn = get_db_connection()
        user_count = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        conn.close()

        # If no users exist, proceed (this is first run)
        if user_count == 0:
            return f(*args, **kwargs)

        # Otherwise check for admin rights
        if not current_user.is_authenticated or not current_user.is_admin:
            return abort(403)
        return f(*args, **kwargs)
    return decorated_function


def is_friends_with(user_id, other_user_id):
    """Check if two users are friends"""
    if user_id == other_user_id:
        return True  # User is always "friends" with themselves

    conn = get_db_connection()
    try:
        friendship = conn.execute('''
            SELECT id FROM friendships
            WHERE (user_id_1 = ? AND user_id_2 = ?)
               OR (user_id_1 = ? AND user_id_2 = ?)
        ''', (min(user_id, other_user_id), max(user_id, other_user_id),
              min(user_id, other_user_id), max(user_id, other_user_id))).fetchone()

        return friendship is not None
    finally:
        conn.close()


def get_friendship_status(current_user_id, target_user_id):
    """
    Get the friendship status between two users.
    Returns one of: 'self', 'friends', 'request_sent', 'request_received', 'none'
    """
    if current_user_id == target_user_id:
        return 'self'

    conn = get_db_connection()
    try:
        # Check if friends
        friendship = conn.execute('''
            SELECT id FROM friendships
            WHERE (user_id_1 = ? AND user_id_2 = ?)
               OR (user_id_1 = ? AND user_id_2 = ?)
        ''', (min(current_user_id, target_user_id), max(current_user_id, target_user_id),
              min(current_user_id, target_user_id), max(current_user_id, target_user_id))).fetchone()

        if friendship:
            return 'friends'

        # Check for pending friend request
        friend_request = conn.execute('''
            SELECT sender_id FROM friend_requests
            WHERE ((sender_id = ? AND receiver_id = ?) OR (sender_id = ? AND receiver_id = ?))
              AND status = 'pending'
        ''', (current_user_id, target_user_id, target_user_id, current_user_id)).fetchone()

        if friend_request:
            if friend_request['sender_id'] == current_user_id:
                return 'request_sent'
            else:
                return 'request_received'

        return 'none'
    finally:
        conn.close()


def get_library_members(user_id):
    """
    Get all users who share a library with the given user (including the user themselves).
    Returns a list of user IDs.
    """
    conn = get_db_connection()
    try:
        # Find the library this user belongs to
        library = conn.execute('''
            SELECT library_id FROM library_members
            WHERE user_id = ?
        ''', (user_id,)).fetchone()

        if not library:
            # User is not in any library group, return just themselves
            return [user_id]

        # Get all members of this library
        members = conn.execute('''
            SELECT user_id FROM library_members
            WHERE library_id = ?
        ''', (library['library_id'],)).fetchall()

        return [m['user_id'] for m in members]
    finally:
        conn.close()


def shares_library_with(user_id, other_user_id):
    """
    Check if two users share a library (are in the same household).
    Returns True if they share a library, False otherwise.
    """
    if user_id == other_user_id:
        return True

    library_members = get_library_members(user_id)
    return other_user_id in library_members


def can_view_content(viewer_id, owner_id, privacy_setting):
    """
    Check if viewer_id can see content owned by owner_id with given privacy setting.

    Privacy settings:
    - 'private': Only the owner can see
    - 'friends': Owner and friends can see
    - 'public': Everyone can see

    Note: Library members are treated as having full access (overrides privacy)
    """
    # Owner can always see their own content
    if viewer_id == owner_id:
        return True

    # Library members can see each other's content (household sharing)
    if shares_library_with(viewer_id, owner_id):
        return True

    # Public content is visible to everyone
    if privacy_setting == 'public':
        return True

    # Private content is only visible to owner (and library members, checked above)
    if privacy_setting == 'private':
        return False

    # Friends-only content requires friendship
    if privacy_setting == 'friends':
        return is_friends_with(viewer_id, owner_id)

    # Default: deny access
    return False