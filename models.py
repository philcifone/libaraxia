#from flask_sqlalchemy import SQLAlchemy
#from flask_bcrypt import Bcrypt
from flask_login import UserMixin

class User(UserMixin):
    def __init__(self, id, username, email, is_active=True):
        self.id = id
        self.username = username
        self.email = email
        self._is_active = is_active  # Store is_active as a private attribute

    def get_id(self):
        return str(self.id)

    @property
    def is_active(self):
        return self._is_active

