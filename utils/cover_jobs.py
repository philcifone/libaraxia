"""Fetch missing covers in the background.

A cover lookup is several HTTP calls (Google Books, Open Library, cover
sites), so a few hundred books can take minutes: far too long for a web
request (gunicorn kills those after 30 s). Instead a request starts a *job*
(a `cover_jobs` row) and a daemon thread in the app works through it one
book at a time, after the user has left the page.

The row is the source of truth, not the thread:
- progress (checked / found / total) is read from it by any gunicorn worker,
  for the floating panel in `_sidebar.html` (static/cover_jobs.js);
- `last_book_id` is a cursor over book ids, so a book that has no cover
  online is tried once per job and the job always ends;
- `worker` + `heartbeat_at` say who's working on it. If that process dies
  (deploy restart, crash), the heartbeat goes stale and the next status poll
  starts a thread here that takes the job over and carries on from the cursor.

Scopes: 'own' = books the user added (library and wishlist), 'all' = every
book (admins only, from the admin covers page).
"""
import logging
import os
import socket
import threading
import time

from flask import current_app

from utils import book_utils
from utils.database import get_db_connection

logger = logging.getLogger(__name__)

# A heartbeat older than this means the worker is gone. One book can take a
# while (several sources, each with its own timeout), so keep it generous.
STALE_SECONDS = 180
# Pause between books, to be polite to Open Library and Google Books
PAUSE_SECONDS = 0.5

_STALE_SQL = f"(heartbeat_at IS NULL OR heartbeat_at < datetime('now', '-{STALE_SECONDS} seconds'))"

_thread = None
_thread_lock = threading.Lock()


def _worker_id():
    return f'{socket.gethostname()}:{os.getpid()}'


def _scope(job_or_scope, user_id=None):
    """(FROM/WHERE sql, params) for the books a job covers."""
    scope = job_or_scope if isinstance(job_or_scope, str) else job_or_scope['scope']
    if user_id is None and not isinstance(job_or_scope, str):
        user_id = job_or_scope['user_id']
    own = scope == 'own'
    return book_utils.missing_cover_sql(owner=own), ((user_id,) if own else ())


def missing_count(conn, user_id, scope):
    sql, params = _scope(scope, user_id)
    return conn.execute('SELECT COUNT(*) ' + sql, params).fetchone()[0]


def as_dict(job):
    """What the browser gets (no worker ids)."""
    if job is None:
        return None
    keys = ('id', 'scope', 'status', 'total', 'checked', 'found')
    return {k: job[k] for k in keys}


# ------------------------------------------------------------ used by routes

def start_job(conn, user_id, scope):
    """Start a job, or return the one already running for this user and
    scope. Returns (job, created); job is None when nothing needs a cover.
    Commits. The caller then calls kick()."""
    running = conn.execute("SELECT * FROM cover_jobs WHERE user_id = ? AND scope = ? AND status = 'running'",
                           (user_id, scope)).fetchone()
    if running:
        return running, False
    total = missing_count(conn, user_id, scope)
    if not total:
        return None, False
    # One panel at a time: older finished jobs are put away
    conn.execute("UPDATE cover_jobs SET dismissed = 1 WHERE user_id = ? AND status != 'running'", (user_id,))
    job_id = conn.execute('INSERT INTO cover_jobs (user_id, scope, total) VALUES (?, ?, ?)',
                          (user_id, scope, total)).lastrowid
    conn.commit()
    return conn.execute('SELECT * FROM cover_jobs WHERE id = ?', (job_id,)).fetchone(), True


def current_job(conn, user_id):
    """The job the user's progress panel shows: a running one, else the
    latest finished one they haven't dismissed. Has a `stale` column: true
    when it's running but its worker has gone quiet (see needs_worker)."""
    return conn.execute(f'''
        SELECT *, {_STALE_SQL} AS stale FROM cover_jobs WHERE user_id = ? AND dismissed = 0
        ORDER BY status = 'running' DESC, id DESC LIMIT 1
    ''', (user_id,)).fetchone()


def needs_worker(job):
    """A running job (from current_job) that nobody is working on."""
    return job is not None and job['status'] == 'running' and bool(job['stale'])


def kick(app=None):
    """Make sure this process has a worker thread running. Cheap to call;
    does nothing in tests (they call run_pending() directly)."""
    global _thread
    app = app or current_app._get_current_object()
    if app.config.get('TESTING'):
        return
    with _thread_lock:
        if _thread is not None and _thread.is_alive():
            return
        _thread = threading.Thread(target=_thread_main, args=(app,), name='cover-jobs', daemon=True)
        _thread.start()


def _thread_main(app):
    with app.app_context():
        try:
            run_pending()
        except Exception:
            logger.exception('Cover job worker crashed')


# ------------------------------------------------------------ the worker

def _claim(conn, worker):
    """Take the oldest running job nobody else is working on. Returns its id."""
    candidates = conn.execute(f'''
        SELECT id FROM cover_jobs
        WHERE status = 'running' AND (worker = ? OR {_STALE_SQL})
        ORDER BY id
    ''', (worker,)).fetchall()
    for row in candidates:
        # Conditional update, so two processes can't both take it
        taken = conn.execute(f'''
            UPDATE cover_jobs SET worker = ?, heartbeat_at = CURRENT_TIMESTAMP
            WHERE id = ? AND status = 'running' AND (worker = ? OR {_STALE_SQL})
        ''', (worker, row['id'], worker)).rowcount
        conn.commit()
        if taken:
            return row['id']
    return None


def run_pending(worker=None, pause=PAUSE_SECONDS):
    """Work through running jobs until there are none left to claim."""
    worker = worker or _worker_id()
    conn = get_db_connection()
    try:
        while True:
            job_id = _claim(conn, worker)
            if job_id is None:
                return
            _run_job(conn, job_id, worker, pause)
    finally:
        conn.close()


def _run_job(conn, job_id, worker, pause):
    while True:
        job = conn.execute('SELECT * FROM cover_jobs WHERE id = ?', (job_id,)).fetchone()
        # Stopped by the user, or taken over by another process
        if job is None or job['status'] != 'running' or job['worker'] != worker:
            return
        sql, params = _scope(job)
        book = conn.execute('SELECT id, title, isbn ' + sql + ' AND id > ? ORDER BY id LIMIT 1',
                            (*params, job['last_book_id'])).fetchone()
        if book is None:
            conn.execute("UPDATE cover_jobs SET status = 'done', finished_at = CURRENT_TIMESTAMP, "
                         "total = checked WHERE id = ? AND worker = ?", (job_id, worker))
            conn.commit()
            logger.info(f'Cover job {job_id} done: {job["found"]} of {job["checked"]} found')
            return

        found = book_utils.fetch_cover_for_book(conn, book)  # network; commits the cover
        conn.execute('''
            UPDATE cover_jobs
            SET checked = checked + 1, found = found + ?, last_book_id = ?,
                total = MAX(total, checked + 1), heartbeat_at = CURRENT_TIMESTAMP
            WHERE id = ? AND worker = ?
        ''', (int(found), book['id'], job_id, worker))
        conn.commit()
        if pause:
            time.sleep(pause)
