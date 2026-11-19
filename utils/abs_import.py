"""The Audiobookshelf import (ROADMAP 16.0e, docs/AUDIOBOOKSHELF-SPEC.md
section 8): Goodreads' review-then-apply shape (utils/goodreads_plan.py),
for what you've listened to or read on the site's ABS server.

  sync()    read your progress and the book libraries from ABS into
            abs_staging (replacing the last sync); writes nothing else
  plan()    read-only: sort every staged item into a box with a default
            choice and what it would write, plus a fingerprint
  apply()   (step 5) re-plan, refuse if the fingerprint moved, write

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
from dataclasses import dataclass, field
from datetime import datetime

from utils import audiobookshelf as abs_
from utils.book_matching import BookIndex
from utils.loans import human_date
from utils.media import AUDIOBOOK, EBOOK, only, BOOK

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
        row.adds = _words(row, writes_for(row, have))
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
