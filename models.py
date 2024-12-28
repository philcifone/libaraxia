#from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import UserMixin

class User(UserMixin):
    def __init__(self, id, username, email, is_active=True, is_admin=False):
        self.id = id
        self.username = username
        self.email = email
        self._is_active = is_active  # Store is_active as a private attribute
        self.is_admin = is_admin

    def get_id(self):
        return str(self.id)

    @property
    def is_active(self):
        return self._is_active

from functools import wraps
from flask import abort
from flask_login import current_user
# admin required function
def admin_required(f):
    """Decorator to restrict access to admin users only."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            return abort(403)  # Return 403 Forbidden
        return f(*args, **kwargs)
    return decorated_function
