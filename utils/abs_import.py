"""The Audiobookshelf import (ROADMAP 16.0e, docs/AUDIOBOOKSHELF-SPEC.md
section 8): Goodreads' review-then-apply shape (utils/goodreads_plan.py),
for what you've listened to or read on the site's ABS server.

  sync()    read your progress and the book libraries from ABS into
            abs_staging (replacing the last sync); writes nothing else
  plan()    read-only: sort every staged item into a box with a default
            choice and what it would write, plus a fingerprint
  apply()   re-plan, refuse if the fingerprint moved, write row by row
            (a SAVEPOINT each), journalled in bulk_edits for undo

Rules the code keeps:
  - Nothing from ABS is owned unless the catalogue already says so (Phil,
    2026-11-18): a created book is owned = 0, an attached one keeps its
    `owned`, and nothing here ever writes books.owned.
  - Only what you've started comes in (progress above 0, or finished);
    "Also books I haven't started" adds the rest, default skip. Podcasts
    and a book at 0 % never come in.
  - Matching only looks at your own books and your household's shelf
    (BookIndex); your wishlist entries don't match (the listen becomes its
    own unowned row and the wish stays). abs_links remembers every ABS item
    already handled, so a re-run creates nothing twice.

No Flask: takes a connection and a user (anything with `id`); the
blueprint (blueprints/audiobookshelf.py) wraps it.
"""
import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime

from utils import audiobookshelf as abs_
from utils.book_matching import BookIndex
from utils.loans import human_date
from utils.media import AUDIOBOOK, EBOOK, only, BOOK

logger = logging.getLogger(__name__)

STAGING_HOURS = 24        # a sync waits this long for its review

# The review's boxes, in page order. `default` is what a row does if you
# pick nothing; `choices` are the others. `hidden` boxes are only counted.
BOXES = {
    'finished_new': {
        'title': 'Finished, not in Libaraxia',
        'text': 'Comes in as Read with its listening dates, unshelved (not owned). Under Books, Show: Unshelved.',
        'default': 'add', 'choices': ['skip']},
    'progress_new': {
        'title': 'In progress, not in Libaraxia',
        'text': 'Comes in as Currently Reading with the day you started, unshelved (not owned).',
        'default': 'add', 'choices': ['skip']},
    'match': {
        'title': 'Matches a book you have',
        'text': "Your listening goes on that book: its status (if it has none, or is only Want to Read) "
                "and a session. It stays owned or not owned as it is.",
        'default': 'attach', 'choices': ['separate', 'skip']},
    'finished_since': {
        'title': 'Finished since your last sync',
        'text': 'Imported before as in progress; now finished. Completes that session and marks it Read.',
        'default': 'complete', 'choices': ['skip']},
    'not_started': {
        'title': "Not started",
        'text': "In your Audiobookshelf libraries, never opened. Skipped unless you choose otherwise.",
        'default': 'skip', 'choices': ['want']},
    'skipped_before': {
        'title': 'Skipped or deleted before',
        'text': 'You skipped these in an earlier import, or deleted what it made.',
        'default': 'skip', 'choices': ['add']},
    'imported': {
        'title': 'Imported before, nothing new',
        'text': '', 'default': None, 'choices': [], 'hidden': True},
}

CHOICES = {
    'add':      'Add, unshelved',
    'attach':   'Add to my book',
    'separate': 'Add as its own book, unshelved',
    'complete': 'Mark finished',
    'want':     'Add as Want to Read, unshelved',
    'skip':     'Skip',
}


class PlanError(ValueError):
    """A refused request; the message is safe to show a person."""


# ------------------------------------------------------------------ sync

def _day(ms):
    """ABS milliseconds since the epoch as a local date ('2026-03-03'), or None."""
    try:
        return datetime.fromtimestamp(int(ms) / 1000).date().isoformat() if ms else None
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def item_format(item):
    """Audiobook if it has audio (with or without an ebook), Ebook if only an
    ebook, None if neither (a broken item: left out)."""
    if item.get('audio_files'):
        return AUDIOBOOK
    if item.get('ebook_format'):
        return EBOOK
    return None


def _progress_of(fmt, prog):
    """How far along, 0 to 1: the listening for an audiobook, the reading
    for an ebook."""
    if not prog:
        return 0
    value = prog.get('progress') if fmt == AUDIOBOOK else prog.get('ebookProgress')
    try:
        return max(0.0, min(1.0, float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _entry(item, prog):
    """One staged item: the metadata and progress the plan and apply need."""
    fmt = item_format(item)
    finished = bool(prog and prog.get('isFinished'))
    return {
        'item': item, 'format': fmt,
        'progress': 1.0 if finished else _progress_of(fmt, prog),
        'finished': finished,
        'started_on': _day(prog.get('startedAt')) if prog else None,
        'finished_on': _day(prog.get('finishedAt')) if finished else None,
        'finished_ms': int(prog.get('finishedAt') or 0) if finished else 0,
    }


def sync(conn, user, token, include_unstarted=False):
    """Fetch from ABS into the user's staging (replacing the last sync).
    Returns how many items were staged. Raises audiobookshelf.AbsError.
    Commits. Also sweeps everyone's staging older than a day."""
    who = abs_.me(token)
    items = abs_.library_items(token)
    progress = {p['libraryItemId']: p for p in who['books']}

    staged = []
    for item_id, item in items.items():
        if item.get('missing') or item_format(item) is None:
            continue
        entry = _entry(item, progress.get(item_id))
        if entry['finished'] or entry['progress'] > 0:
            staged.append((item_id, entry))
        elif include_unstarted:
            entry['not_started'] = True
            staged.append((item_id, entry))

    if not conn.in_transaction:
        conn.execute('BEGIN')
    conn.execute("DELETE FROM abs_staging WHERE staged_at < datetime('now', ?)", (f'-{STAGING_HOURS} hours',))
    conn.execute('DELETE FROM abs_staging WHERE user_id = ?', (user.id,))
    conn.executemany('INSERT INTO abs_staging (user_id, abs_item_id, data) VALUES (?, ?, ?)',
                     [(user.id, item_id, json.dumps(entry)) for item_id, entry in staged])
    conn.execute('UPDATE abs_accounts SET last_sync_at = CURRENT_TIMESTAMP WHERE user_id = ?', (user.id,))
    conn.commit()
    return len(staged)


def has_staging(conn, user):
    return conn.execute("SELECT 1 FROM abs_staging WHERE user_id = ? AND staged_at >= datetime('now', ?) LIMIT 1",
                        (user.id, f'-{STAGING_HOURS} hours')).fetchone() is not None


def discard(conn, user):
    """Start over: the user's staging goes. Commits."""
    conn.execute('DELETE FROM abs_staging WHERE user_id = ?', (user.id,))
    conn.commit()


# ------------------------------------------------------------------ the plan

@dataclass
class Row:
    item_id: str
    data: dict                    # _entry() output
    box: str = 'imported'
    default: str = None
    choices: list = field(default_factory=list)     # every valid choice, default first
    choice: str = None            # effective: stored, else the default
    book: dict = None             # the matched or linked book (id, title, author, owner, format, owned)
    link: dict = None             # the abs_links row, if any
    before: dict = None           # your data on that book now (fingerprinted)
    w: dict = None                # writes_for(): what the choice writes
    adds: list = field(default_factory=list)        # what the choice writes, worded

    @property
    def title(self):
        return self.data['item']['title']

    @property
    def writes(self):
        return self.choice not in (None, 'skip') and bool(self.adds)


@dataclass
class Plan:
    rows: list
    fingerprint: str

    def box_rows(self, box):
        return [r for r in self.rows if r.box == box]

    def count(self, box):
        return sum(r.box == box for r in self.rows)

    @property
    def will_write(self):
        return sum(r.writes for r in self.rows)


def _your_data(conn, user_id):
    """Your status and reading sessions on books, by book id (two queries)."""
    data = {}
    for r in conn.execute(f'SELECT book_id, status FROM collections WHERE user_id = ? AND {only(BOOK)}',
                          (user_id,)):
        data.setdefault(r['book_id'], {'status': None, 'sessions': []})['status'] = r['status']
    for r in conn.execute(f'''SELECT book_id, session_id, date_started, date_completed FROM reading_sessions
                              WHERE user_id = ? AND {only(BOOK)} ORDER BY session_id''', (user_id,)):
        data.setdefault(r['book_id'], {'status': None, 'sessions': []})['sessions'].append(
            [r['session_id'], r['date_started'], r['date_completed']])
    return data


def _links(conn, user_id):
    return {r['abs_item_id']: dict(r) for r in conn.execute(
        'SELECT * FROM abs_links WHERE user_id = ?', (user_id,))}


def _book_summary(conn, book_id, owners):
    b = conn.execute('SELECT id, title, author, added_by, format, owned FROM books WHERE id = ?',
                     (book_id,)).fetchone()
    if not b:
        return None
    return {'id': b['id'], 'title': b['title'], 'author': b['author'], 'format': b['format'],
            'owned': b['owned'], 'owner': owners.get(b['added_by'])}


def _ms_after(ms, recorded):
    """Whether ABS's finishedAt (ms) is later than the one a link recorded."""
    if not recorded:
        return True
    try:
        return ms > int(recorded)
    except (TypeError, ValueError):
        return True


STATUS_WORDS = {'read': 'Read', 'currently reading': 'Currently Reading', 'want to read': 'Want to Read'}


def _status_for(d, choice):
    if choice == 'want':
        return 'want to read'
    return 'read' if d['finished'] else 'currently reading'


def writes_for(row, have):
    """What a row's choice would write: {'create', 'status', 'session',
    'complete_session', 'fill'}, or None for nothing. `have` is your data on
    row.book. The planner words it (adds); apply (step 5) does it."""
    d, choice = row.data, row.choice
    if choice in (None, 'skip'):
        return None
    status = _status_for(d, choice)
    session = None
    if choice != 'want' and (d['started_on'] or d['finished_on']):
        session = {'started': d['started_on'], 'completed': d['finished_on']}
    if choice in ('add', 'separate', 'want'):
        return {'create': True, 'status': status, 'session': session}

    have = have or {'status': None, 'sessions': []}
    w = {'create': False, 'status': None, 'session': None, 'complete_session': None}
    if choice == 'complete':
        w['status'] = 'read' if have['status'] != 'read' else None
        open_ = [s for s in have['sessions'] if s[2] is None]
        if open_:
            w['complete_session'] = {'id': open_[-1][0], 'completed': d['finished_on']}
        else:
            w['session'] = session          # a re-listen, or the open one was closed by hand
        return w
    # attach: a status where there is none (or only Want to Read), and the
    # session unless you already have one like it
    if have['status'] in (None, 'want to read') and status != have['status']:
        w['status'] = status
    if session:
        if d['finished_on']:
            same = any(s[2] == d['finished_on'] for s in have['sessions'])
        else:
            same = any(s[2] is None for s in have['sessions'])
        if not same:
            w['session'] = session
    return w


def _span(started, completed):
    """'8 Mar to 18 Mar 2026' (the year once when both share it)."""
    end = human_date(completed)
    if not started:
        return f'finished {end}'
    start = human_date(started)
    if started[:4] == completed[:4]:
        start = start.rsplit(' ', 1)[0]
    return f'{start} to {end}'


def _words(row, w):
    """The writes, as the review page lists them."""
    if not w:
        return []
    d = row.data
    verb = 'listened' if d['format'] == AUDIOBOOK else 'read'
    out = []
    if w.get('create'):
        out.append(f"a new unshelved {d['format'].lower()}")
    if w.get('status'):
        out.append(STATUS_WORDS[w['status']])
    s = w.get('session')
    if s:
        if s['completed']:
            out.append(f"{verb} {_span(s['started'], s['completed'])}")
        else:
            out.append(f"started {human_date(s['started'])}")
    if w.get('complete_session'):
        out.append(f"finished {human_date(w['complete_session']['completed'])}")
    return out


def _load_staging(conn, user):
    return conn.execute("SELECT abs_item_id, data, choice FROM abs_staging WHERE user_id = ? "
                        "AND staged_at >= datetime('now', ?) ORDER BY abs_item_id",
                        (user.id, f'-{STAGING_HOURS} hours')).fetchall()


def plan(conn, user):
    """Every staged item, classified fresh against the database now. Writes
    nothing. Returns None if the user has nothing staged."""
    staged = _load_staging(conn, user)
    if not staged:
        return None
    index = BookIndex(conn, user.id)
    links = _links(conn, user.id)
    yours = _your_data(conn, user.id)
    owners = {r['id']: r['username'] for r in conn.execute('SELECT id, username FROM users')}

    rows = []
    for s in staged:
        d = json.loads(s['data'])
        item = d['item']
        row = Row(s['abs_item_id'], d)
        link = links.get(row.item_id)
        row.link = link
        if link:
            if link['outcome'] == 'skipped' or link['book_id'] is None:
                row.box = 'skipped_before'
            elif d['finished'] and _ms_after(d['finished_ms'], link['finished_at']):
                row.box = 'finished_since'
                row.book = _book_summary(conn, link['book_id'], owners)
            else:
                row.box = 'imported'
                row.book = _book_summary(conn, link['book_id'], owners)
        else:
            isbns = [item['isbn']] if item.get('isbn') else []
            book, _ = index.match(isbns, item['title'], item['author'])
            if book is not None and book.get('is_wishlist_entry'):
                book = None                 # a wish isn't a copy: the listen gets its own row
            if book is not None:
                row.box = 'match'
                row.book = _book_summary(conn, book['id'], owners)
            elif d.get('not_started'):
                row.box = 'not_started'
            elif d['finished']:
                row.box = 'finished_new'
            else:
                row.box = 'progress_new'

        box = BOXES[row.box]
        row.default = box['default']
        row.choices = ([box['default']] if box['default'] else []) + box['choices']
        if row.box == 'skipped_before' and d.get('not_started'):
            row.choices = ['skip', 'want']
        row.choice = s['choice'] if s['choice'] in row.choices else row.default
        have = yours.get(row.book['id']) if row.book else None
        if row.book:
            row.before = {'book': [row.book['id'], row.book['format']], 'have': have}
        row.w = writes_for(row, have)
        row.adds = _words(row, row.w)
        rows.append(row)

    order = list(BOXES)
    rows.sort(key=lambda r: (order.index(r.box), (r.title or '').lower()))
    digest = hashlib.sha256(json.dumps(
        [(r.item_id, r.box, r.book and r.book['id'], r.before, r.link and r.link['finished_at'])
         for r in rows], sort_keys=True, default=str).encode()).hexdigest()
    return Plan(rows, digest)


def choose(conn, user, choices):
    """Save the review form's choices ({item id: choice}) where valid for
    the row's box; the default is stored as NULL, so a row keeps following
    its box. Returns the fresh plan. Commits."""
    current = plan(conn, user)
    if current is None:
        raise PlanError('Sync with Audiobookshelf first.')
    by_id = {r.item_id: r for r in current.rows}
    for item_id, choice in choices.items():
        row = by_id.get(item_id)
        if row is None or choice not in row.choices:
            continue
        conn.execute('UPDATE abs_staging SET choice = ? WHERE user_id = ? AND abs_item_id = ?',
                     (None if choice == row.default else choice, user.id, item_id))
    conn.commit()
    return plan(conn, user)


def hours(seconds):
    """ABS seconds as '16 h 10 min' for the review page."""
    from utils.media import format_runtime
    return format_runtime(round((seconds or 0) / 60)) if seconds else ''


# ------------------------------------------------------------------ apply
# Each written row journals one bulk_edit_items row (bulk edit's undo), with
# only the parts it wrote: "book" (a created book), "status", "sessions" (the
# ids added), "completed" (an open session it finished), "fill" (narrator and
# length filled on your own audiobook row). `before` is NULL for a created
# book. abs_links isn't journalled per item: bulk_edits.params lists the
# links this apply made or changed, and undo puts those back (_after_undo).

class StalePlan(PlanError):
    """The data moved between the review and Import. `plan` is the fresh one."""
    def __init__(self, plan):
        super().__init__('Something changed since you looked; check the review and import again.')
        self.plan = plan


BOOK_PART = ('title', 'author', 'format', 'owned', 'narrator', 'runtime_minutes', 'removed_at')
MAX_DESCRIPTION = 5000
SKIP_REMEMBERED = ('finished_new', 'progress_new', 'match')   # a skip here is asked again only as "skipped before"


def _part(conn, user_id, book_id, name, ids=()):
    if name == 'sessions':
        marks = ','.join('?' * len(ids)) or 'NULL'
        return [dict(r) for r in conn.execute(
            f'SELECT session_id, date_started, date_completed FROM reading_sessions '
            f'WHERE user_id = ? AND book_id = ? AND session_id IN ({marks}) ORDER BY session_id',
            (user_id, book_id, *ids))]
    if name == 'completed':
        row = conn.execute('SELECT session_id, date_started, date_completed FROM reading_sessions '
                           'WHERE user_id = ? AND book_id = ? AND session_id = ?',
                           (user_id, book_id, ids[0] if ids else None)).fetchone()
        return None if row is None else dict(row)
    if name == 'book':
        row = conn.execute(f"SELECT {', '.join(BOOK_PART)} FROM books WHERE id = ?", (book_id,)).fetchone()
        return None if row is None else dict(row)
    if name == 'fill':
        row = conn.execute('SELECT narrator, runtime_minutes FROM books WHERE id = ?', (book_id,)).fetchone()
        return None if row is None else dict(row)
    row = conn.execute('SELECT status, created_at, updated_at, quiet FROM collections '
                       'WHERE book_id = ? AND user_id = ?', (book_id, user_id)).fetchone()
    return None if row is None else dict(row)


def _snapshot(conn, user_id, book_id, names, session_ids=(), completed_id=None):
    return {name: _part(conn, user_id, book_id, name,
                        [completed_id] if name == 'completed' else session_ids) for name in names}


def _create_book(conn, user_id, d):
    """A new unowned book from a staged item. Never owned (Phil's rule)."""
    item, fmt = d['item'], d['format']
    audio = fmt == AUDIOBOOK
    cols = {
        'title': item['title'] or 'Untitled', 'subtitle': item.get('subtitle') or None,
        'author': item['author'] or 'Unknown', 'publisher': item.get('publisher') or None,
        'publish_year': item.get('year') or None, 'isbn': item.get('isbn') or None,
        'genre': (item.get('genres') or [None])[0],
        'description': (item.get('description') or '')[:MAX_DESCRIPTION] or None,
        'added_by': user_id, 'owned': 0, 'format': fmt,
        'narrator': (item.get('narrator') or None) if audio else None,
        'runtime_minutes': (round(item['duration'] / 60) or None) if audio and item.get('duration') else None,
    }
    # Dated when you started, so a first import doesn't flood friends' feeds
    # as "added today" (the column default covers an undated one)
    when = d.get('started_on') or d.get('finished_on')
    if when:
        cols['created_at'] = when
    return conn.execute(f"INSERT INTO books ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                        list(cols.values())).lastrowid


def _set_status(conn, user_id, book_id, status, when):
    """A status, quiet (out of friends' feed, migration 031): new, or
    replacing Want to Read (the plan only ever replaces that)."""
    if conn.execute('SELECT 1 FROM collections WHERE user_id = ? AND book_id = ?', (user_id, book_id)).fetchone():
        conn.execute('UPDATE collections SET status = ?, quiet = 1, updated_at = CURRENT_TIMESTAMP '
                     'WHERE user_id = ? AND book_id = ?', (status, user_id, book_id))
    elif when:
        conn.execute('INSERT INTO collections (user_id, book_id, status, created_at, updated_at, quiet) '
                     'VALUES (?, ?, ?, ?, ?, 1)', (user_id, book_id, status, when, when))
    else:
        conn.execute('INSERT INTO collections (user_id, book_id, status, quiet) VALUES (?, ?, ?, 1)',
                     (user_id, book_id, status))


def _fill(conn, user_id, book_id, d):
    """Narrator and length onto your own Audiobook row, only where empty.
    Returns True if anything would be filled (checked before writing)."""
    item = d['item']
    if d['format'] != AUDIOBOOK:
        return False
    book = conn.execute('SELECT added_by, format, narrator, runtime_minutes FROM books WHERE id = ?',
                        (book_id,)).fetchone()
    if not book or book['added_by'] != user_id or book['format'] != AUDIOBOOK:
        return False
    narrator = item.get('narrator') if not book['narrator'] else None
    minutes = round(item['duration'] / 60) if not book['runtime_minutes'] and item.get('duration') else None
    if not (narrator or minutes):
        return False
    conn.execute('UPDATE books SET narrator = COALESCE(narrator, ?), runtime_minutes = COALESCE(runtime_minutes, ?) '
                 'WHERE id = ? AND added_by = ?', (narrator or None, minutes or None, book_id, user_id))
    return True


def _write_row(conn, user, row, edit_id):
    """Write one row and its journal item. Returns (book_id, session_id)."""
    from models import can_view_book
    d, w = row.data, row.w
    when = d.get('started_on') or d.get('finished_on')
    session_id = None
    if w['create']:
        book_id = _create_book(conn, user.id, d)
        before, names = None, ['book']
    else:
        book_id = row.book['id']
        # Checked again now, as for any write onto a book id
        if not can_view_book(conn, user, book_id):
            raise PlanError('Not found')
        names = (['status'] if w.get('status') else []) + (['completed'] if w.get('complete_session') else [])
        completed_id = w['complete_session']['id'] if w.get('complete_session') else None
        before = _snapshot(conn, user.id, book_id, names, completed_id=completed_id)
        if w.get('session'):
            before['sessions'] = []
        fill_before = _part(conn, user.id, book_id, 'fill')
        if _fill(conn, user.id, book_id, d):
            names.append('fill')
            before['fill'] = fill_before

    if w.get('status'):
        _set_status(conn, user.id, book_id, w['status'], when)
        if w['create']:
            names.append('status')
    ids = []
    if w.get('session'):
        s = w['session']
        session_id = conn.execute('INSERT INTO reading_sessions (user_id, book_id, date_started, date_completed) '
                                  'VALUES (?, ?, ?, ?)', (user.id, book_id, s['started'], s['completed'])).lastrowid
        ids.append(session_id)
        names.append('sessions')
    completed_id = None
    if w.get('complete_session'):
        completed_id = session_id = w['complete_session']['id']
        conn.execute('UPDATE reading_sessions SET date_completed = ? '
                     'WHERE session_id = ? AND user_id = ? AND book_id = ? AND date_completed IS NULL',
                     (w['complete_session']['completed'], completed_id, user.id, book_id))
    after = _snapshot(conn, user.id, book_id, names, ids, completed_id)
    conn.execute('INSERT INTO bulk_edit_items (edit_id, book_id, before, after) VALUES (?, ?, ?, ?)',
                 (edit_id, book_id, None if before is None else json.dumps(before, sort_keys=True),
                  json.dumps(after, sort_keys=True)))
    return book_id, session_id


def _link(conn, user, row, outcome, book_id, session_id, params):
    """Record what an ABS item became, remembering the old link for undo."""
    d = row.data
    old = row.link
    if old is None:
        params['created'].append(row.item_id)
    elif row.item_id not in params['updated']:
        params['updated'][row.item_id] = {k: old[k] for k in ('outcome', 'book_id', 'session_id', 'finished_at')}
    conn.execute('''
        INSERT INTO abs_links (user_id, abs_item_id, book_id, outcome, asin, session_id, finished_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (user_id, abs_item_id) DO UPDATE SET
            book_id = excluded.book_id, outcome = excluded.outcome, asin = excluded.asin,
            session_id = COALESCE(excluded.session_id, abs_links.session_id),
            finished_at = COALESCE(excluded.finished_at, abs_links.finished_at),
            linked_at = CURRENT_TIMESTAMP
    ''', (user.id, row.item_id, book_id, outcome, d['item'].get('asin') or None, session_id,
          d['finished_ms'] or None))


SUMMARY_WORDS = (('created', 'added'), ('attached', 'added to books you have'),
                 ('completed', 'marked finished'), ('skipped', 'skipped'), ('error', 'failed'))


def apply(conn, user, fingerprint):
    """Write the plan the user reviewed. Raises StalePlan (with the fresh
    plan) if anything moved since `fingerprint`. A row that fails leaves
    nothing behind and the rest carry on. Deletes the staging and commits.
    Returns {'edit_id', 'summary', 'counts'}."""
    from utils.bulk import KEEP_DAYS
    current = plan(conn, user)
    if current is None:
        raise PlanError('Sync with Audiobookshelf first.')
    if current.fingerprint != fingerprint:
        raise StalePlan(current)

    conn.execute("DELETE FROM bulk_edits WHERE created_at < datetime('now', ?)", (f'-{KEEP_DAYS} days',))
    # One transaction: without it the first SAVEPOINT's RELEASE would commit
    if not conn.in_transaction:
        conn.execute('BEGIN')
    edit_id = conn.execute("INSERT INTO bulk_edits (user_id, action, params, summary, item_count) "
                           "VALUES (?, 'audiobookshelf', '{}', '', 0)", (user.id,)).lastrowid
    params = {'edit_id': edit_id, 'created': [], 'updated': {}}
    counts = {key: 0 for key, _ in SUMMARY_WORDS}
    written = 0

    for row in current.rows:
        if row.box == 'imported' or row.choice is None:
            continue
        if row.choice == 'skip':
            if row.box in SKIP_REMEMBERED:
                _link(conn, user, row, 'skipped', None, None, params)
                counts['skipped'] += 1
            continue
        conn.execute('SAVEPOINT abs_row')
        try:
            if row.writes:
                book_id, session_id = _write_row(conn, user, row, edit_id)
                written += 1
            else:
                book_id, session_id = row.book['id'], None      # attached, nothing missing
            outcome = 'created' if row.w['create'] else 'attached'
            if row.box == 'finished_since':
                outcome = row.link['outcome']
                counts['completed'] += 1
            else:
                counts[outcome] += 1
            _link(conn, user, row, outcome, book_id, session_id, params)
            conn.execute('RELEASE abs_row')
        except Exception:
            logger.exception('Audiobookshelf import: item %s (%r) failed', row.item_id, row.title)
            conn.execute('ROLLBACK TO abs_row')
            conn.execute('RELEASE abs_row')
            counts['error'] += 1

    bits = [f'{counts[k]} {words}' for k, words in SUMMARY_WORDS if counts.get(k)]
    summary = 'Audiobookshelf import: ' + (', '.join(bits) if bits else 'nothing written')
    if written or params['created'] or params['updated']:
        conn.execute('UPDATE bulk_edits SET params = ?, summary = ?, item_count = ? WHERE id = ?',
                     (json.dumps(params, sort_keys=True), summary, written, edit_id))
    else:
        conn.execute('DELETE FROM bulk_edits WHERE id = ?', (edit_id,))
        edit_id = None
    conn.execute('DELETE FROM abs_staging WHERE user_id = ?', (user.id,))
    conn.commit()
    return {'edit_id': edit_id, 'summary': summary, 'counts': counts}


# ------------------------------------------------------------------ covers

COVER_SECONDS = 15


def fetch_covers(conn, user, token, budget=COVER_SECONDS):
    """Covers from ABS for books the import created that have none, until
    the time budget runs out; the rest are tried on the next import.
    Returns (fetched, left). Commits after each cover."""
    import time
    from io import BytesIO
    from PIL import Image
    from utils.book_utils import placeholder_reason, save_cover_image

    rows = conn.execute('''
        SELECT l.abs_item_id, b.id FROM abs_links l JOIN books b ON b.id = l.book_id
        WHERE l.user_id = ? AND l.outcome = 'created' AND b.added_by = ?
          AND (b.cover_image_url IS NULL OR b.cover_image_url = '')
        ORDER BY l.id''', (user.id, user.id)).fetchall()
    deadline = time.monotonic() + budget
    fetched = 0
    for i, r in enumerate(rows):
        if time.monotonic() > deadline:
            return fetched, len(rows) - i
        try:
            img = Image.open(BytesIO(abs_.cover(token, r['abs_item_id'])))
            img.load()
            if placeholder_reason(img):
                continue
            path = save_cover_image(img)
        except Exception as e:          # AbsError, or not an image Pillow can read
            logger.info('Audiobookshelf cover for %s: %s', r['abs_item_id'], type(e).__name__)
            continue
        conn.execute("UPDATE books SET cover_image_url = ? WHERE id = ? AND added_by = ? "
                     "AND (cover_image_url IS NULL OR cover_image_url = '')", (path, r['id'], user.id))
        conn.commit()
        fetched += 1
    return fetched, 0


# ------------------------------------------------------------------ undo (through the bulk journal)

def _journal_after(conn, params, book_id):
    item = conn.execute('SELECT after FROM bulk_edit_items WHERE edit_id = ? AND book_id = ?',
                        (params.get('edit_id'), book_id)).fetchone()
    return json.loads(item['after']) if item and item['after'] else {}


def _current(conn, user, book_id, params):
    """The parts the import wrote, as they are now (undo's guard compares
    this with the journalled `after`)."""
    after = _journal_after(conn, params, book_id)
    ids = [s['session_id'] for s in after.get('sessions') or []]
    completed = (after.get('completed') or {}).get('session_id')
    return _snapshot(conn, user.id, book_id, list(after), ids, completed)


def _restore(conn, user, book_id, before, after, params):
    from models import other_users_with_book_data
    from utils.goodreads_plan import _yours_beyond
    from utils.image_utils import delete_image_file, is_safe_upload_path
    if before is None:
        # A book the import created: deleted only if nobody else has data on
        # it and you've added nothing of your own since (Goodreads' rule)
        book = conn.execute('SELECT added_by, cover_image_url FROM books WHERE id = ?', (book_id,)).fetchone()
        if (book is None or book['added_by'] != user.id
                or other_users_with_book_data(conn, book_id, user.id)
                or _yours_beyond(conn, user, book_id, after)):
            return False
        conn.execute('DELETE FROM books WHERE id = ? AND added_by = ?', (book_id, user.id))
        if book['cover_image_url'] and is_safe_upload_path(book['cover_image_url']):
            delete_image_file(book['cover_image_url'])
        return True
    for name, was in before.items():
        if name == 'sessions':
            conn.executemany('DELETE FROM reading_sessions WHERE session_id = ? AND user_id = ? AND book_id = ?',
                             [(s['session_id'], user.id, book_id) for s in after.get('sessions') or []])
        elif name == 'status':
            if was is None:
                conn.execute('DELETE FROM collections WHERE user_id = ? AND book_id = ?', (user.id, book_id))
            else:
                conn.execute('UPDATE collections SET status = ?, created_at = ?, updated_at = ?, quiet = ? '
                             'WHERE user_id = ? AND book_id = ?',
                             (was['status'], was['created_at'], was['updated_at'], was['quiet'], user.id, book_id))
        elif name == 'completed' and was is not None:
            conn.execute('UPDATE reading_sessions SET date_completed = ? WHERE session_id = ? AND user_id = ?',
                         (was['date_completed'], was['session_id'], user.id))
        elif name == 'fill' and was is not None:
            conn.execute('UPDATE books SET narrator = ?, runtime_minutes = ? WHERE id = ? AND added_by = ?',
                         (was['narrator'], was['runtime_minutes'], book_id, user.id))
    return True


def _after_undo(conn, user, edit_id):
    """The links this import made go; the ones it changed go back."""
    row = conn.execute('SELECT params FROM bulk_edits WHERE id = ? AND user_id = ?', (edit_id, user.id)).fetchone()
    params = json.loads(row['params']) if row else {}
    conn.executemany('DELETE FROM abs_links WHERE user_id = ? AND abs_item_id = ?',
                     [(user.id, item_id) for item_id in params.get('created', [])])
    for item_id, was in (params.get('updated') or {}).items():
        conn.execute('''UPDATE abs_links SET outcome = ?,
                            book_id = (SELECT id FROM books WHERE id = ?),
                            session_id = (SELECT session_id FROM reading_sessions WHERE session_id = ?),
                            finished_at = ?
                        WHERE user_id = ? AND abs_item_id = ?''',
                     (was['outcome'], was['book_id'], was['session_id'], was['finished_at'], user.id, item_id))


def _not_a_bulk_edit(*args, **kwargs):
    from utils.bulk import BulkError
    raise BulkError('That bulk action is not available.')


def _make_action():
    from utils.bulk import Action
    return Action(
        params=_not_a_bulk_edit, plan=_not_a_bulk_edit, write=_not_a_bulk_edit,
        current=_current, restore=_restore,
        describe=lambda p: 'Audiobookshelf import', summary=lambda p, n: 'Audiobookshelf import',
        key=lambda b: None, label=lambda k, p: '', same_text=lambda p: '',
        after_undo=_after_undo)
