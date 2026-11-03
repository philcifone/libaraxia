import sqlite3
import os

DATABASE = os.getenv('DATABASE_PATH', 'library.db')

# Helper function to connect to the database
def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row  # Allows dict-like access to rows
    # SQLite only enforces foreign keys (and their ON DELETE rules) when each
    # connection asks for it. Needs migrations 014/015 (manage.py migrate).
    conn.execute('PRAGMA foreign_keys = ON')
    return conn
