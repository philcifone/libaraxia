"""Fetch missing covers in the background.

A cover lookup is several HTTP calls (Google Books and Open Library for a
book, UPCitemdb and TMDb for a movie, Discogs or MusicBrainz for an album;
utils/media_covers.py), so a few hundred items can take minutes: far too long for a web
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

Scopes: 'own' = items the user added (library and wishlist), 'all' = every
item (admins only, from the admin covers page). Books, movies and albums
alike; book_utils.missing_cover_sql says which items qualify.

Kinds (migration 039): 'cover' fetches missing covers; 'value' fetches
values (ROADMAP 16.0a, utils/valuation.py) for items on the shelf that a
source can answer for, in the sections chosen, skipping values checked in
the last `skip_days` days and never touching a value typed by hand. Values
go slower (VALUE_PAUSE_SECONDS) to stay well inside Discogs' and eBay's
limits, and a busy source is waited out rather than skipped.
"""
import logging
import os
import socket
import threading
import time

from flask import current_app

from utils import book_utils, media_covers
from utils.database import get_db_connection

logger = logging.getLogger(__name__)

# A heartbeat older than this means the worker is gone. One book can take a
# while (several sources, each with its own timeout), so keep it generous.
STALE_SECONDS = 180
# Pause between books, to be polite to Open Library and Google Books
PAUSE_SECONDS = 0.5
# Values: one request every couple of seconds (eBay's default is 5,000 calls
# a day, Discogs 60 a minute); a busy answer waits BUSY_WAIT, at most
# BUSY_TRIES times for one item before it's skipped
VALUE_PAUSE_SECONDS = 2.0
BUSY_WAIT = 30
BUSY_TRIES = 4
KINDS = ('cover', 'value')

_STALE_SQL = f"(heartbeat_at IS NULL OR heartbeat_at < datetime('now', '-{STALE_SECONDS} seconds'))"

_thread = None
_thread_lock = threading.Lock()


def _worker_id():
    return f'{socket.gethostname()}:{os.getpid()}'


def _scope(job_or_scope, user_id=None):
    """(FROM/WHERE sql, params) for the books a job covers."""
    if not isinstance(job_or_scope, str) and job_or_scope['kind'] == 'value':
        types = (job_or_scope['media_types'] or '').split(',') if job_or_scope['media_types'] else None
        return value_scope_sql(job_or_scope['scope'], job_or_scope['user_id'], types,
                               job_or_scope['skip_days'])
    scope = job_or_scope if isinstance(job_or_scope, str) else job_or_scope['scope']
    if user_id is None and not isinstance(job_or_scope, str):
        user_id = job_or_scope['user_id']
    own = scope == 'own'
    return book_utils.missing_cover_sql(owner=own), ((user_id,) if own else ())


def value_scope_sql(scope, user_id, types=None, skip_days=None):
    """(FROM/WHERE sql, params) for the items a value job covers: on a shelf
    (owned, not removed, not a wishlist entry), of the chosen types, that a
    configured source can answer for (a record with Discogs; a book's ISBN
    or a movie's barcode with eBay), whose value wasn't typed by hand, and
    not checked within skip_days."""
    from utils import valuation
    lookable = []
    if valuation.discogs_enabled():
        lookable.append("media_type = 'record'")
    if valuation.ebay_enabled():
        lookable.append("(media_type = 'book' AND isbn IS NOT NULL AND isbn != '')")
        lookable.append("(media_type = 'video' AND barcode IS NOT NULL AND barcode != '')")
    if types:
        lookable = [sql for sql in lookable if any(f"'{t}'" in sql for t in types)]
    sql = f"""
    FROM books
    WHERE {book_utils.on_shelf('books')}
      AND added_by IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM wishlist w WHERE w.book_id = books.id AND w.user_id = books.added_by)
      AND ({' OR '.join(lookable) or '0'})
      AND (value_source IS NULL OR value_source != 'manual')
"""
    params = []
    if skip_days:
        sql += "  AND (value_checked_at IS NULL OR value_checked_at < datetime('now', ?))\n"
        params.append(f'-{int(skip_days)} days')
    if scope == 'own':
        sql += "  AND added_by = ?\n"
        params.append(user_id)
    return sql, tuple(params)


def missing_count(conn, user_id, scope):
    sql, params = _scope(scope, user_id)
    return conn.execute('SELECT COUNT(*) ' + sql, params).fetchone()[0]


def as_dict(job):
    """What the browser gets (no worker ids)."""
    if job is None:
        return None
    keys = ('id', 'scope', 'status', 'total', 'checked', 'found', 'kind')
    return {k: job[k] for k in keys}


# ------------------------------------------------------------ used by routes

def start_job(conn, user_id, scope, kind='cover', media_types=None, skip_days=None):
    """Start a job, or return the one of this kind already running for this
    user and scope. Returns (job, created); job is None when nothing needs
    doing. Commits. The caller then calls kick(). A value job takes the
    sections (media_types, a list or None for all) and skip_days."""
    running = conn.execute("SELECT * FROM cover_jobs WHERE user_id = ? AND scope = ? AND kind = ? "
                           "AND status = 'running'", (user_id, scope, kind)).fetchone()
    if running:
        return running, False
    types = ','.join(media_types) if media_types else None
    if kind == 'value':
        sql, params = value_scope_sql(scope, user_id, media_types, skip_days)
        total = conn.execute('SELECT COUNT(*) ' + sql, params).fetchone()[0]
    else:
        total = missing_count(conn, user_id, scope)
    if not total:
        return None, False
    # One panel at a time: older finished jobs are put away
    conn.execute("UPDATE cover_jobs SET dismissed = 1 WHERE user_id = ? AND status != 'running'", (user_id,))
    job_id = conn.execute('INSERT INTO cover_jobs (user_id, scope, total, kind, media_types, skip_days) '
                          'VALUES (?, ?, ?, ?, ?, ?)',
                          (user_id, scope, total, kind, types, skip_days if kind == 'value' else None)).lastrowid
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
        book = conn.execute('SELECT id, title, author, isbn, barcode, format, publish_year, media_type '
                            + sql + ' AND id > ? ORDER BY id LIMIT 1',
                            (*params, job['last_book_id'])).fetchone()
        if book is None:
            conn.execute("UPDATE cover_jobs SET status = 'done', finished_at = CURRENT_TIMESTAMP, "
                         "total = checked WHERE id = ? AND worker = ?", (job_id, worker))
            conn.commit()
            logger.info(f'Cover job {job_id} done: {job["found"]} of {job["checked"]} found')
            return

        if job['kind'] == 'value':
            found = _fetch_value(conn, book['id'], job_id, worker)
            if found is None:           # the source stayed busy: try this item again
                continue
        else:
            found = media_covers.fetch_cover(conn, book)  # network; commits the cover
        conn.execute('''
            UPDATE cover_jobs
            SET checked = checked + 1, found = found + ?, last_book_id = ?,
                total = MAX(total, checked + 1), heartbeat_at = CURRENT_TIMESTAMP
            WHERE id = ? AND worker = ?
        ''', (int(found), book['id'], job_id, worker))
        conn.commit()
        if pause:
            time.sleep(VALUE_PAUSE_SECONDS if job['kind'] == 'value' and pause == PAUSE_SECONDS else pause)


_busy = {}      # (job id, book id) -> busy answers so far, for this process


def _fetch_value(conn, book_id, job_id, worker):
    """Fetch and store one item's value. True if one was stored, False if
    not; None when the source was busy and the item should be tried again
    after a wait (up to BUSY_TRIES times, then it counts as not found)."""
    from utils import valuation
    row = conn.execute('SELECT * FROM books WHERE id = ?', (book_id,)).fetchone()
    result = valuation.fetch(row)
    if result.busy:
        key = (job_id, book_id)
        _busy[key] = _busy.get(key, 0) + 1
        if _busy[key] < BUSY_TRIES:
            conn.execute('UPDATE cover_jobs SET heartbeat_at = CURRENT_TIMESTAMP WHERE id = ? AND worker = ?',
                         (job_id, worker))
            conn.commit()
            time.sleep(BUSY_WAIT)
            return None
        _busy.pop(key, None)
    if result.release_id and not row['discogs_release_id']:
        conn.execute('UPDATE books SET discogs_release_id = ? WHERE id = ?', (result.release_id, book_id))
    if result.cents is None:
        conn.commit()
        return False
    # Never over a value typed by hand (it could have been typed since the
    # job started), so the condition is in the UPDATE itself
    stored = conn.execute('''
        UPDATE books SET value_cents = ?, value_source = ?, value_note = ?,
               value_checked_at = CURRENT_TIMESTAMP
        WHERE id = ? AND (value_source IS NULL OR value_source != 'manual')
    ''', (result.cents, result.source, result.note, book_id)).rowcount
    conn.commit()
    return bool(stored)
