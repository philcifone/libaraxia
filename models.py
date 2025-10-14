from flask_login import UserMixin
from functools import wraps
from flask import abort, redirect, url_for
from flask_login import current_user
from utils.database import get_db_connection

class User(UserMixin):
    def __init__(self, id, username, email, is_active=True, is_admin=False, avatar_url=None):
        self.id = id
        self.username = username
        self.email = email
        self._is_active = is_active
        self.is_admin = is_admin
        self.avatar_url = avatar_url

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