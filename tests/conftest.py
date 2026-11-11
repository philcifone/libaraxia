"""Shared fixtures: a fresh migrated database per test, the app, and seed data.

Run with `pytest` from the project root (see requirements-dev.txt). Nothing
here touches library.db: every test gets its own copy of a database built by
`manage.py migrate` in a temp directory, and DATABASE_PATH points at it.
"""
import os
import shutil
import sqlite3
import subprocess
import sys

import bcrypt
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Set before app/config are imported. load_dotenv() never overrides variables
# that are already set, so a developer's .env can't change how tests run.
os.environ['FLASK_ENV'] = 'development'
os.environ['SECRET_KEY'] = 'test-secret-key'
os.environ['EMAIL_VERIFICATION_REQUIRED'] = 'False'
os.environ['ALLOW_REGISTRATION'] = 'True'
os.environ['TRUSTED_PROXY_COUNT'] = '0'
# Lookups that only switch on with a key: off unless a test turns one on.
# Set (to empty) so load_dotenv can't fill them in from a real .env.
os.environ['DISCOGS_TOKEN'] = ''
os.environ['TMDB_API_KEY'] = ''
os.environ['MUSICBRAINZ_CONTACT'] = ''
os.environ['DATABASE_PATH'] = os.path.join(ROOT, 'tests', '.no-database-yet.db')

PASSWORD = 'correct-horse-battery'
_HASH = bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt(rounds=4)).decode()


def run_manage(*args, check=True):
    """Run manage.py as a subprocess (it calls sys.exit on errors)."""
    result = subprocess.run([sys.executable, os.path.join(ROOT, 'manage.py'), *args],
                            capture_output=True, text=True, cwd=ROOT)
    if check and result.returncode != 0:
        raise AssertionError(f'manage.py {" ".join(args)} failed:\n{result.stdout}\n{result.stderr}')
    return result


@pytest.fixture(scope='session')
def template_db(tmp_path_factory):
    """One database built by `manage.py migrate`; each test gets a copy."""
    path = tmp_path_factory.mktemp('template') / 'template.db'
    run_manage('--db', str(path), 'migrate', '-y')
    return path


@pytest.fixture
def db_path(template_db, tmp_path, monkeypatch):
    path = tmp_path / 'test.db'
    shutil.copy(template_db, path)
    monkeypatch.setenv('DATABASE_PATH', str(path))  # read on every call by utils.database
    return path


@pytest.fixture
def db(db_path):
    """A direct connection for arranging data and checking results."""
    from utils.database import register_functions
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    register_functions(conn)            # fold(), cover_missing(), as the app's
    yield conn
    conn.close()


@pytest.fixture(autouse=True)
def static_root(tmp_path, monkeypatch):
    """Stored cover paths resolve under a temp static/ (utils.image_utils),
    never the checkout's: its uploads/ holds whatever the developer has, and
    cover_missing() would judge test covers by it. Starts with no uploads
    folder, so no cover counts as missing until a test makes the folder."""
    from utils import image_utils
    root = tmp_path / 'static'
    root.mkdir()
    monkeypatch.setattr(image_utils, 'STATIC_ROOT', str(root))
    return root


@pytest.fixture(scope='session')
def app():
    from app import create_app
    from utils.rate_limiting import limiter
    application = create_app()
    application.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    limiter.enabled = False
    return application


@pytest.fixture
def client(app, db_path):
    return app.test_client()


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Tests never reach the internet (Google Books, Open Library, covers)."""
    import requests

    def refuse(*args, **kwargs):
        raise requests.exceptions.ConnectionError('network disabled in tests')
    monkeypatch.setattr(requests.sessions.Session, 'request', refuse)


# --- seed data -------------------------------------------------------------

def add_user(db, username, admin=False, active=True):
    cur = db.execute(
        'INSERT INTO users (username, email, password, is_admin, is_active, email_verified) '
        'VALUES (?, ?, ?, ?, ?, 1)',
        (username, f'{username}@example.test', _HASH, int(admin), int(active)))
    db.commit()
    return cur.lastrowid


def add_book(db, owner_id, title='A Book', author='An Author', cover=None):
    cur = db.execute('INSERT INTO books (title, author, added_by, cover_image_url) VALUES (?, ?, ?, ?)',
                     (title, author, owner_id, cover))
    db.commit()
    return cur.lastrowid


def add_review(db, user_id, book_id, rating=5, comment='Loved it'):
    db.execute('INSERT INTO read_data (user_id, book_id, rating, comment) VALUES (?, ?, ?, ?)',
               (user_id, book_id, rating, comment))
    db.execute("INSERT INTO collections (user_id, book_id, status) VALUES (?, ?, 'read')", (user_id, book_id))
    db.execute("INSERT INTO reading_sessions (user_id, book_id, date_completed) VALUES (?, ?, '2024-01-01')",
               (user_id, book_id))
    db.commit()


def make_household(db, *user_ids):
    for uid in user_ids:
        db.execute("INSERT INTO library_members (library_id, user_id, role) VALUES (?, ?, ?)",
                   (user_ids[0], uid, 'owner' if uid == user_ids[0] else 'member'))
    db.commit()


def make_friends(db, a, b):
    db.execute('INSERT INTO friendships (user_id_1, user_id_2) VALUES (?, ?)', (min(a, b), max(a, b)))
    db.commit()


def login(client, username):
    r = client.post('/auth/login', data={'email': f'{username}@example.test', 'password': PASSWORD})
    assert r.status_code == 302, 'login failed'
    return r


def scalar(db, sql, *params):
    return db.execute(sql, params).fetchone()[0]


def fk_violations(db):
    return db.execute('PRAGMA foreign_key_check').fetchall()


@pytest.fixture
def people(db):
    """alice (admin) and bob share a household; carol is alice's friend, not in it."""
    alice = add_user(db, 'alice', admin=True)
    bob = add_user(db, 'bob')
    carol = add_user(db, 'carol')
    make_household(db, alice, bob)
    make_friends(db, alice, carol)
    return {'alice': alice, 'bob': bob, 'carol': carol}
