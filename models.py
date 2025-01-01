from flask_login import UserMixin
from functools import wraps
from flask import abort
from flask_login import current_user

class User(UserMixin):
    def __init__(self, id, username, email, is_active=True, is_admin=False):
        self.id = id
        self.username = username
        self.email = email
        self._is_active = is_active
        self.is_admin = is_admin

    def get_id(self):
        return str(self.id)

    @property
    def is_active(self):
        return self._is_active

def admin_required(f):
    """Decorator to restrict access to admin users only."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            return abort(403)
        return f(*args, **kwargs)
    return decorated_function