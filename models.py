from flask_login import UserMixin
from functools import wraps
import re
from flask import abort, redirect, url_for
from flask_login import current_user
from utils.database import get_db

# Usernames appear in URLs and in HTML/JS, so keep them to a safe character set
USERNAME_PATTERN = re.compile(r'^[A-Za-z0-9_.-]{3,30}$')
USERNAME_RULES = 'Username must be 3-30 characters: letters, numbers, dots, dashes or underscores.'

def is_valid_username(username):
    return bool(username) and USERNAME_PATTERN.match(username) is not None


# Appearance settings (see the Themes section in static/styles.css).
# To add a style, add its CSS blocks there and its key + label here.
# Keys are stored in users.theme_style and used in CSS; the names are what
# the Appearance picker shows (renamed 2026-11-08, Phil).
THEME_STYLES = {'house': 'Negative Earth', 'classic': 'OG', 'outrun': 'Outrun', 'shelf': 'Shelf'}
THEME_MODES = {'system': 'System', 'light': 'Light', 'dark': 'Dark'}
DEFAULT_THEME_STYLE = 'house'
DEFAULT_THEME_MODE = 'system'
# Accent colours (8B.5), Gruvbox: each has a light and a dark shade in
# static/styles.css ([data-accent]). Both styles; Classic uses the dark shades.
ACCENTS = {'green': 'Green', 'aqua': 'Aqua', 'blue': 'Blue', 'purple': 'Purple',
           'orange': 'Orange', 'red': 'Red', 'yellow': 'Yellow'}
DEFAULT_ACCENT = 'green'
# Font choice (users.font, data-font; styles.css "Font choice"). 'theme'
# keeps the style's own fonts; the others set body and headings alike.
FONTS = {'theme': 'Theme', 'baskerville': 'Baskerville', 'garamond': 'Garamond',
         'literata': 'Literata', 'jost': 'Jost'}
DEFAULT_FONT = 'theme'


class User(UserMixin):
    def __init__(self, id, username, email, is_active=True, is_admin=False, avatar_url=None, email_verified=True, bio=None,
                 theme_style=DEFAULT_THEME_STYLE, theme_mode=DEFAULT_THEME_MODE, accent=DEFAULT_ACCENT, font=DEFAULT_FONT):
        self.id = id
        self.username = username
        self.email = email
        self._is_active = is_active
        self.is_admin = is_admin
        self.avatar_url = avatar_url
        self.email_verified = email_verified
        self.bio = bio
        self.theme_style = theme_style if theme_style in THEME_STYLES else DEFAULT_THEME_STYLE
        self.theme_mode = theme_mode if theme_mode in THEME_MODES else DEFAULT_THEME_MODE
        self.accent = accent if accent in ACCENTS else DEFAULT_ACCENT
        self.font = font if font in FONTS else DEFAULT_FONT

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
        conn = get_db()
        user_count = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]

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

    conn = get_db()
    friendship = conn.execute('''
        SELECT id FROM friendships
        WHERE (user_id_1 = ? AND user_id_2 = ?)
           OR (user_id_1 = ? AND user_id_2 = ?)
    ''', (min(user_id, other_user_id), max(user_id, other_user_id),
          min(user_id, other_user_id), max(user_id, other_user_id))).fetchone()

    return friendship is not None


def get_friendship_status(current_user_id, target_user_id):
    """
    Get the friendship status between two users.
    Returns one of: 'self', 'friends', 'request_sent', 'request_received', 'none'
    """
    if current_user_id == target_user_id:
        return 'self'

    conn = get_db()
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


def get_library_members(user_id):
    """
    Get all users who share a library with the given user (including the user themselves).
    Returns a list of user IDs.
    """
    conn = get_db()
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


def shares_library_with(user_id, other_user_id):
    """
    Check if two users share a library (are in the same household).
    Returns True if they share a library, False otherwise.
    """
    if user_id == other_user_id:
        return True

    library_members = get_library_members(user_id)
    return other_user_id in library_members


def friend_ids(conn, user_id):
    """The user's friends (not themselves, not household members who aren't
    also friends). Friendships are stored with user_id_1 < user_id_2, so
    look both ways."""
    return sorted(r['other'] for r in conn.execute('''
        SELECT CASE WHEN user_id_1 = ? THEN user_id_2 ELSE user_id_1 END AS other
        FROM friendships WHERE user_id_1 = ? OR user_id_2 = ?
    ''', (user_id, user_id, user_id)))


def circle_ids(conn, user_id):
    """The user's circle: themselves, their household members and their friends.

    This is the set of people whose books and activity a user can see
    (see "Access Model" in CLAUDE.md).
    """
    ids = {user_id}
    ids.update(r['user_id'] for r in conn.execute('''
        SELECT m.user_id FROM library_members m
        JOIN library_members me ON me.library_id = m.library_id
        WHERE me.user_id = ?
    ''', (user_id,)))
    ids.update(friend_ids(conn, user_id))
    return sorted(ids)


def can_view_book(conn, user, book_id):
    """Whether `user` may open a book's page or attach their own data to it.

    Allowed for admins, and when someone in the user's circle (themselves,
    household, friends) owns the book or has their own data on it: a review,
    reading status, reading session, tag, wishlist entry or custom-collection
    entry. The second clause keeps a book reachable from the feed and from
    the user's own history after it was given away or its owner deleted.

    Routes that let a user attach data to a book id must call this first, or
    attaching data would itself grant access.
    """
    if user.is_admin:
        return conn.execute('SELECT 1 FROM books WHERE id = ?', (book_id,)).fetchone() is not None
    ids = circle_ids(conn, user.id)
    marks = ','.join('?' * len(ids))
    row = conn.execute(f'''
        SELECT 1 FROM books WHERE id = ? AND added_by IN ({marks})
        UNION ALL SELECT 1 FROM read_data        WHERE book_id = ? AND user_id IN ({marks})
        UNION ALL SELECT 1 FROM collections      WHERE book_id = ? AND user_id IN ({marks})
        UNION ALL SELECT 1 FROM reading_sessions WHERE book_id = ? AND user_id IN ({marks})
        UNION ALL SELECT 1 FROM book_tags        WHERE book_id = ? AND user_id IN ({marks})
        UNION ALL SELECT 1 FROM wishlist         WHERE book_id = ? AND user_id IN ({marks})
        UNION ALL SELECT 1 FROM collection_books cb
                  JOIN user_collections uc ON uc.collection_id = cb.collection_id
                  WHERE cb.book_id = ? AND uc.user_id IN ({marks})
        LIMIT 1
    ''', [book_id, *ids] * 7).fetchone()
    return row is not None


def other_users_with_book_data(conn, book_id, owner_id):
    """Usernames of users other than owner_id with their own data on a book.

    "Data" means a review/rating, reading status, reading session, tag,
    custom-collection entry or wishlist entry. A book that anyone else has
    data on must not be hard-deleted (the delete would cascade into their
    rows); it can only be given away or, later, marked as removed.
    owner_id may be None (unowned book): then every user counts.
    """
    rows = conn.execute('''
        SELECT DISTINCT u.username FROM users u WHERE u.id IS NOT ? AND u.id IN (
            SELECT user_id FROM read_data        WHERE book_id = ?
            UNION SELECT user_id FROM collections      WHERE book_id = ?
            UNION SELECT user_id FROM reading_sessions WHERE book_id = ?
            UNION SELECT user_id FROM book_tags        WHERE book_id = ?
            UNION SELECT user_id FROM wishlist         WHERE book_id = ?
            UNION SELECT uc.user_id FROM collection_books cb
                  JOIN user_collections uc ON uc.collection_id = cb.collection_id
                  WHERE cb.book_id = ?
        ) ORDER BY u.username
    ''', (owner_id, book_id, book_id, book_id, book_id, book_id, book_id)).fetchall()
    return [r['username'] for r in rows]
