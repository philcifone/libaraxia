import os
import sqlite3

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def database_path():
    """The SQLite file the app uses: DATABASE_PATH, default library.db.

    Read on every call (not at import), so a value from .env is honoured no
    matter when load_dotenv() runs. A relative path is taken relative to the
    project directory, not the current working directory, so the app,
    manage.py and gunicorn always agree on which file it is.
    """
    path = os.getenv('DATABASE_PATH') or 'library.db'
    return path if os.path.isabs(path) else os.path.join(PROJECT_ROOT, path)


def get_db_connection():
    conn = sqlite3.connect(database_path())
    conn.row_factory = sqlite3.Row  # Allows dict-like access to rows
    # SQLite only enforces foreign keys (and their ON DELETE rules) when each
    # connection asks for it. Needs migrations 014/015 (manage.py migrate).
    conn.execute('PRAGMA foreign_keys = ON')
    return conn
