import os
import sqlite3
from utils import search

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
    # WAL (set on the file by manage.py migrate, ROADMAP 16.0g): NORMAL is
    # safe there (a power cut can lose the last commit, never corrupt the
    # file) and saves an fsync per commit. busy_timeout: wait up to 5 s for
    # another worker's write instead of failing with "database is locked".
    conn.execute('PRAGMA synchronous = NORMAL')
    conn.execute('PRAGMA busy_timeout = 5000')
    register_functions(conn)
    return conn


def register_functions(conn):
    """The app's own SQL functions, on any connection (tests call this on
    theirs too):
      fold()           accent- and punctuation-free matching for the search
                       boxes (utils/search.py)
      cover_missing()  a cover link whose file is gone (utils/image_utils.py)"""
    from utils.image_utils import cover_missing
    search.register(conn)
    conn.create_function('cover_missing', 1, cover_missing)


def get_db():
    """The request's shared connection (opened on first use, closed at teardown).

    Use this in routes and helpers called from routes: no try/finally or
    close() needed. Commit explicitly after writes; anything not committed
    is rolled back when the request ends. Outside a request (manage.py,
    scripts) use get_db_connection() and close it yourself.
    """
    from flask import g
    if 'db' not in g:
        g.db = get_db_connection()
        # Dev only (PROFILE_REQUESTS=1, utils/profiling.py): count statements
        from utils import profiling
        if profiling.enabled():
            g.db.set_trace_callback(profiling.count_statement)
    return g.db


def close_db(exc=None):
    """teardown_appcontext hook: close the request's connection, if any."""
    from flask import g
    conn = g.pop('db', None)
    if conn is not None:
        conn.close()  # uncommitted changes are rolled back
