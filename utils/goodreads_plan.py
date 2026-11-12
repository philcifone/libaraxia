"""The granular Goodreads import (ROADMAP 14b, docs/GOODREADS-IMPORT-SPEC.md).

Three steps, like a bulk edit (utils/bulk.py):

  stage()   parse the upload into goodreads_staging; writes nothing else
  plan()    read-only: sort every staged row into a box (section 6) with a
            default choice, what it would add, and what differs, plus a
            fingerprint of everything the page shows
  apply()   re-plan, refuse if the fingerprint moved, then write row by row,
            each in its own SAVEPOINT, journalling for undo (section 9)

Principles the code keeps: nothing is written that the review didn't show;
imports only add (a missing status, rating, review or reading session; a
new book or wishlist entry), never change or delete what you have, apart
from the wishlist decisions the user makes per row; nothing is added as
owned unless the user says so.

Takes a connection and a user (anything with `id` and `is_admin`) and uses
no Flask context, so tests drive it directly (blueprints/user.py wraps it).

Matching only looks at your own books and your household's shelf
(BookIndex), plus the Goodreads Book Id memory of earlier imports, which
only ever points at a book BookIndex could have matched.
"""
import csv
import hashlib
import json
import logging
from dataclasses import dataclass, field
from io import StringIO

from models import can_view_book, other_users_with_book_data
from utils import media
from utils.bulk import KEEP_DAYS, Action, BulkError
from utils.book_matching import BookIndex
from utils.goodreads import REQUIRED_COLUMNS, ImportFileError, parse_row
from utils.media import BOOK, only
from utils.image_utils import delete_image_file, is_safe_upload_path
from utils.search import fold

logger = logging.getLogger(__name__)

MAX_ROWS = 5000           # per upload; the review page holds every row
STAGING_HOURS = 24        # an upload waits this long for its review

READ_LIKE = ('read', 'currently reading', 'did not finish')

# ------------------------------------------------------------------ boxes and choices

# The boxes of the review page, in the order it shows them (section 6).
# `default` is what a row in the box does if the user picks nothing; `ask`
# means "not imported until you decide". Each box's other choices follow.
# Flip read_new's default to 'library' to restore the old owned default
# (spec section 16, decision 1).
BOXES = {
    'decide_reading': {
        'title': 'Needs a decision: currently reading on Goodreads',
        'text': "Goodreads' \"currently reading\" is as old as your export. Where are you with these now?",
        'default': 'ask', 'choices': ['still_reading', 'finished', 'dnf', 'skip']},
    'decide_wishlist': {
        'title': 'Needs a decision: read on Goodreads, on your Libaraxia wishlist',
        'text': 'You read these on Goodreads, and they are on your wishlist here.',
        'default': 'ask', 'choices': ['keep_wished', 'drop_wish', 'bought', 'skip']},
    'read_new': {
        'title': 'Read, not in your library',
        'text': 'Comes in read, with your rating, review and reading dates. Off the shelf; '
                'under Books, Show: Not owned.',
        'default': 'not_owned', 'choices': ['library', 'skip']},
    'fill': {
        'title': 'Already in Libaraxia, something to add',
        'text': 'Only what is missing is added. Your status, rating and review stay as they are.',
        'default': 'fill', 'choices': ['skip']},
    'want_new': {
        'title': 'On your Goodreads want-to-read list, not in Libaraxia',
        'text': 'Goes to your wishlist, with your Goodreads private notes as the note.',
        'default': 'wishlist', 'choices': ['skip']},
    'want_nothing': {
        'title': 'On your Goodreads want-to-read list, nothing to do',
        'text': 'You already have these here in some form. Shown, not written.',
        'default': None, 'choices': []},
    'unsure': {
        'title': 'Not sure',
        'text': 'On a Goodreads shelf with no reading recorded.',
        'default': 'skip', 'choices': ['not_owned', 'wishlist']},
    'nothing': {
        'title': 'Nothing to do',
        'text': 'Already in Libaraxia with nothing missing, or nothing to import.',
        'default': None, 'choices': []},
}

# What the user can pick, as the selects and the selection bar word it.
# 'ask' is only ever a default, never something the user sets.
CHOICES = {
    'ask':           'Ask',
    'not_owned':     'Add as read, not owned',
    'library':       'Add to my library',
    'wishlist':      'Add to wishlist',
    'fill':          "Add what's missing",
    'still_reading': 'Still reading',
    'finished':      'Finished',
    'dnf':           'Did not finish',
    'keep_wished':   'Read it, still want it',
    'drop_wish':     "Read it, don't want it",
    'bought':        'Bought it',
    'skip':          'Skip',
}

# One per CSV row in the result (section 8). The counts add up to the file.
OUTCOMES = {
    'not_owned': 'Added as read, not owned',
    'library':   'Added to your library',
    'wishlist':  'Added to your wishlist',
    'filled':    'Added what was missing to a book you have',
    'decided':   'Imported as you decided (currently reading, or wishlist and read)',
    'later':     'Left for later (needs a decision)',
    'nothing':   'Nothing to do',
    'skipped':   'Skipped',
    'error':     'Failed, nothing saved for this row',
}

# The status a decision box's answer stands for
DECIDED_STATUS = {'still_reading': 'currently reading', 'finished': 'read', 'dnf': 'did not finish'}

# Why a want-to-read row needs nothing, by what it matched
WANT_REASONS = {
    'shelf': 'you own it now', 'household': 'you own it now',
    'wishlist': 'already on your wishlist', 'not_owned': 'you read it here',
    'removed': 'you let it go',
}


class PlanError(ValueError):
    """A refused request; the message is safe to show a person."""


class StalePlan(PlanError):
    """The data moved between the review and apply. `plan` is the fresh one."""
    def __init__(self, plan):
        super().__init__('Some rows changed since you looked; check them and import again.')
        self.plan = plan


# ------------------------------------------------------------------ the plan

@dataclass
class Row:
    line: int
    data: dict                    # parse_row() output
    box: str
    default: str = None           # the box's default (or 'skip' for a past skip)
    choices: list = field(default_factory=list)   # every valid choice, default first
    choice: str = None            # effective: stored, else the default
    kind: str = 'none'            # match kind: none, wishlist, shelf, not_owned, removed, household
    book: dict = None             # the matched book (id, title, author, cover, owner)
    reason: str = ''              # Nothing to do / want-to-read: why
    same_as: int = None           # "Same book as line N"
    skipped_before: bool = False  # skipped in an earlier import
    home_box: str = None          # for a past skip shown under Nothing to do: the box it came from
    before: dict = None           # your data on the matched book now (fingerprinted)
    parts: dict = None            # what the effective choice would write
    adds: list = field(default_factory=list)      # parts, worded
    differs: list = field(default_factory=list)   # what Goodreads says differently, yours kept
    preview: str = None           # the combined review, when Goodreads' is appended to yours

    @property
    def writes(self):
        """Whether the effective choice writes anything."""
        if self.choice in (None, 'ask', 'skip'):
            return False
        return bool(self.parts and (self.parts.get('create') or self.parts.get('wishlist_move')
                                    or self.adds))

    def as_dict(self):
        d = self.data
        return {
            'line': self.line, 'title': d['title'], 'author': d['author'],
            'box': self.box, 'home_box': self.home_box, 'kind': self.kind, 'book': self.book,
            'default': self.default, 'choices': self.choices, 'choice': self.choice,
            'shelves': d['shelves'], 'status': d['status'], 'date_read': d['date_read'],
            'date_added': d['date_added'], 'rating': d['rating'], 'review': bool(d['review']),
            'audiobook': d['audiobook'], 'adds': self.adds, 'differs': self.differs,
            'reason': self.reason, 'same_as': self.same_as, 'skipped_before': self.skipped_before,
            'preview': self.preview, 'writes': self.writes,
        }


@dataclass
class Plan:
    rows: list
    filename: str
    fingerprint: str

    def count(self, box):
        return sum(r.box == box for r in self.rows)

    @property
    def will_write(self):
        return sum(r.writes for r in self.rows)

    @property
    def undecided(self):
        return sum(r.choice == 'ask' for r in self.rows)

    def reasons(self, box):
        """A summary box's rows by reason, most first: [(reason, count)].
        "Same book as line N" counts as one reason."""
        counts = {}
        for r in self.rows:
            if r.box == box:
                reason = 'same book as another row' if r.same_as else (r.reason or 'nothing to add')
                counts[reason] = counts.get(reason, 0) + 1
        return sorted(counts.items(), key=lambda kv: -kv[1])

    def differing(self, box):
        """How many rows of a box differ from Goodreads, yours kept."""
        return sum(r.box == box and bool(r.differs) for r in self.rows)

    def shelves(self):
        """Every Goodreads shelf in the file, most used first, for the filter."""
        counts = {}
        for r in self.rows:
            for s in r.data['shelves']:
                counts[s] = counts.get(s, 0) + 1
        return [s for s, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]

    def as_dict(self):
        return {
            'filename': self.filename, 'fingerprint': self.fingerprint,
            'total': len(self.rows), 'will_write': self.will_write, 'undecided': self.undecided,
            'boxes': [{'key': k, 'title': b['title'], 'text': b['text'],
                       'default': b['default'], 'default_label': CHOICES.get(b['default']),
                       'count': self.count(k)} for k, b in BOXES.items()],
            'choices': CHOICES, 'shelves': self.shelves(),
            'rows': [r.as_dict() for r in self.rows],
        }


# ------------------------------------------------------------------ stage

def stage(conn, user, text, filename):
    """Parse a decoded Goodreads export into the user's staging, replacing any
    earlier upload. Returns the number of data rows. Commits.

    Raises ImportFileError (message for the user) if it isn't an export or
    is too big. Also sweeps everyone's staging older than a day."""
    reader = csv.DictReader(StringIO(text))
    missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
    if missing:
        raise ImportFileError("This doesn't look like a Goodreads library export "
                              f"(missing column{'s' if len(missing) > 1 else ''}: {', '.join(sorted(missing))}).")
    rows = list(reader)
    if not rows:
        raise ImportFileError('This export has no books in it.')
    if len(rows) > MAX_ROWS:
        raise ImportFileError(f'This file has {len(rows)} rows; the import takes up to {MAX_ROWS}. '
                              'Split it in a spreadsheet and import twice.')

    if not conn.in_transaction:
        conn.execute('BEGIN')
    conn.execute("DELETE FROM goodreads_staging WHERE created_at < datetime('now', ?)",
                 (f'-{STAGING_HOURS} hours',))
    conn.execute('DELETE FROM goodreads_staging WHERE user_id = ?', (user.id,))
    # Line 1 is the header; a "line" is a record (a review can span lines)
    conn.executemany('INSERT INTO goodreads_staging (user_id, line, data, filename) VALUES (?, ?, ?, ?)',
                     [(user.id, n, json.dumps(parse_row(raw)), filename)
                      for n, raw in enumerate(rows, start=2)])
    conn.commit()
    return len(rows)


def has_staging(conn, user):
    return conn.execute("SELECT 1 FROM goodreads_staging WHERE user_id = ? "
                        "AND created_at >= datetime('now', ?) LIMIT 1",
                        (user.id, f'-{STAGING_HOURS} hours')).fetchone() is not None


def discard(conn, user):
    """Start over: the user's staging goes. Commits."""
    conn.execute('DELETE FROM goodreads_staging WHERE user_id = ?', (user.id,))
    conn.commit()


# ------------------------------------------------------------------ what you have

def _your_data(conn, user_id):
    """Your rows on books, by book id, in four queries (not per row): status,
    rating/review, reading session dates, wishlist entries."""
    data = {}

    def entry(book_id):
        return data.setdefault(book_id, {'status': None, 'rating': None, 'comment': None,
                                         'sessions': [], 'wished': False})
    for r in conn.execute(f'SELECT book_id, status FROM collections WHERE user_id = ? AND {only(BOOK)}',
                          (user_id,)):
        entry(r['book_id'])['status'] = r['status']
    for r in conn.execute(f'SELECT book_id, rating, comment FROM read_data WHERE user_id = ? AND {only(BOOK)}',
                          (user_id,)):
        e = entry(r['book_id'])
        e['rating'], e['comment'] = r['rating'], r['comment']
    for r in conn.execute(f'SELECT book_id, date_completed FROM reading_sessions WHERE user_id = ? '
                          f'AND {only(BOOK)} ORDER BY session_id', (user_id,)):
        entry(r['book_id'])['sessions'].append(r['date_completed'])
    for r in conn.execute(f'SELECT book_id FROM wishlist WHERE user_id = ? AND {only(BOOK)}', (user_id,)):
        entry(r['book_id'])['wished'] = True
    return data


def _memory(conn, user_id, index):
    """Earlier imports, by Goodreads Book Id: the book the latest one matched
    or created (only if it still exists and BookIndex could match it), and
    whether the latest one skipped the row. Undone imports don't count."""
    books, skipped = {}, set()
    for r in conn.execute('''
            SELECT r.goodreads_id, r.book_id, r.outcome FROM goodreads_rows r
            JOIN goodreads_imports i ON i.id = r.import_id
            WHERE i.user_id = ? AND i.undone_at IS NULL AND r.goodreads_id IS NOT NULL
            ORDER BY i.id, r.line''', (user_id,)):
        gid = r['goodreads_id']
        if r['outcome'] == 'skipped':
            skipped.add(gid)
        else:
            skipped.discard(gid)
        if r['book_id'] is not None and r['book_id'] in index.by_id:
            books[gid] = index.by_id[r['book_id']]
    return books, skipped


def _kind(book):
    if book['whose'] == 'household':
        return 'household'
    if book['is_wishlist_entry']:
        return 'wishlist'
    if book['removed_at'] is not None:
        return 'removed'
    if not book['owned']:
        return 'not_owned'
    return 'shelf'


# ------------------------------------------------------------------ fill

def _review_label(d):
    """'Goodreads review, read 2011-05-02, ★3:' (date added when not read)."""
    bits = ['Goodreads review']
    if d['date_read']:
        bits.append(f"read {d['date_read']}")
    elif d['date_added']:
        bits.append(f"added {d['date_added']}")
    if d['rating']:
        bits.append(f"★{d['rating']}")
    return ', '.join(bits) + ':'


def appended_review(yours, d):
    """Your review, unchanged, with the Goodreads one below a divider."""
    return f"{yours.rstrip()}\n\n----\n{_review_label(d)}\n{d['review']}"


def _sessions_to_add(d, status, have, finished=False):
    """Reading sessions to add (their date_completed, None = undated). Only
    for 'read'. Never edits or deletes yours, never duplicates a date:
    - no sessions of yours: Read Count sessions, at least one, the last dated
      Date Read (as for a new book); `finished` (a decision with no date): one
    - some: one dated Date Read if none of yours has that date, else none."""
    if status != 'read':
        return []
    if finished:
        return [] if have else [None]
    if not have:
        count = max(d['read_count'], 1)
        return [None] * (count - 1) + [d['date_read']]
    return [d['date_read']] if d['date_read'] and d['date_read'] not in have else []


def _fill(d, status, have, finished=False):
    """What filling `have` (your data on a book, or None for a new one) from
    Goodreads row `d` adds, as parts: status, rating, review ('set' or
    'append', text), sessions. Plus the differences, yours kept."""
    have = have or {'status': None, 'rating': None, 'comment': None, 'sessions': [], 'wished': False}
    parts, differs = {}, []
    if status:
        if have['status'] is None:
            parts['status'] = status
        elif have['status'] != status:
            differs.append(f"status: yours {media.STATUS_LABELS[have['status']]}, "
                           f"Goodreads {media.STATUS_LABELS[status]}")
    if d['rating']:
        if have['rating'] is None:
            parts['rating'] = d['rating']
        elif have['rating'] != d['rating']:
            differs.append(f"rating: yours ★{have['rating']}, Goodreads ★{d['rating']}")
    if d['review']:
        yours = have['comment'] or ''
        if not yours.strip():
            parts['review'] = ('set', d['review'])
        elif fold(d['review']) not in fold(yours):
            parts['review'] = ('append', appended_review(yours, d))
    sessions = _sessions_to_add(d, status, have['sessions'], finished)
    if sessions:
        parts['sessions'] = sessions
    return parts, differs


def _words(parts, new=False):
    """A row's "adds:" list."""
    out = []
    if new:
        out.append({'not_owned': 'new book, not owned', 'library': 'new book, in your library',
                    'wishlist': 'new wishlist entry'}[new])
    if parts.get('wishlist_move'):
        out.append({'drop_wish': 'off your wishlist, as read and not owned',
                    'bought': 'off your wishlist, into your library'}[parts['wishlist_move']])
    if parts.get('status'):
        out.append(f"status {media.STATUS_LABELS[parts['status']]}")
    if parts.get('rating'):
        out.append(f"rating ★{parts['rating']}")
    if parts.get('review'):
        out.append('review' if parts['review'][0] == 'set' else 'Goodreads review below yours')
    sessions = parts.get('sessions') or []
    if len(sessions) == 1:
        out.append(f'a reading session ({sessions[0]})' if sessions[0] else 'a reading session')
    elif sessions:
        dated = [s for s in sessions if s]
        out.append(f'{len(sessions)} reading sessions' + (f' (last {dated[-1]})' if dated else ''))
    return [w for w in out if w]


def _parts_for(row, choice, have):
    """What `choice` on `row` writes: (parts, adds, preview). Parts are what
    apply() writes; `create` is set for a new book ('owned' 0/1, 'wishlist')."""
    d = row.data
    if choice in (None, 'ask', 'skip'):
        return None, [], None
    box = row.home_box or row.box

    if box in ('read_new', 'unsure', 'want_new', 'decide_reading') and row.kind == 'none':
        # A new book
        if choice == 'wishlist':
            parts = {'create': 'wishlist'}
            if d['rating']:
                parts['rating'] = d['rating']
            if d['review']:
                parts['review'] = ('set', d['review'])
            return parts, _words(parts, new='wishlist'), None
        if box == 'decide_reading':
            status, finished = DECIDED_STATUS[choice], choice == 'finished'
        elif box == 'unsure':
            status, finished = 'read', False     # "Add as read": one undated session
        else:
            status, finished = d['status'], False
        parts, _ = _fill(d, status, None, finished)
        parts['create'] = 'library' if choice == 'library' else 'not_owned'
        return parts, _words(parts, new=parts['create']), None

    # A book you (or your household) have
    if box == 'decide_reading':
        status, finished = DECIDED_STATUS[choice], choice == 'finished'
    elif box == 'decide_wishlist':
        # Currently reading on Goodreads, on your wishlist here: as finished
        finished = d['status'] == 'currently reading'
        status = 'read' if finished else d['status']
    else:
        status, finished = d['status'], False
    parts, _ = _fill(d, status, have, finished)
    if box == 'decide_wishlist' and choice in ('drop_wish', 'bought'):
        parts['wishlist_move'] = choice
    preview = parts['review'][1] if parts.get('review', ('',))[0] == 'append' else None
    return parts, _words(parts), preview


# ------------------------------------------------------------------ plan

def _load_staging(conn, user):
    return conn.execute("SELECT line, data, choice, filename FROM goodreads_staging WHERE user_id = ? "
                        "AND created_at >= datetime('now', ?) ORDER BY line",
                        (user.id, f'-{STAGING_HOURS} hours')).fetchall()


def _book_summary(book, owners):
    if book is None or book['id'] < 0:
        return None
    return {'id': book['id'], 'title': book['title'], 'author': book['author'],
            'cover': book.get('cover_image_url'),
            'owner': owners.get(book['added_by']) if book['whose'] == 'household' else None}


def _before(book, have):
    """Your data on a matched book now, as the fingerprint sees it."""
    have = have or {}
    return {'book': [book['id'], book.get('owned'), book.get('removed_at'), bool(book['is_wishlist_entry'])],
            'status': have.get('status'), 'rating': have.get('rating'), 'comment': have.get('comment'),
            'sessions': have.get('sessions', []), 'wished': have.get('wished', False)}


def _classify(row, have):
    """Set row.box (and kind-dependent fields) from what Goodreads says and
    what matched. `have` is your data on the matched book."""
    d, kind = row.data, row.kind
    status = d['status']
    if status is None:
        if kind == 'none':
            row.box = 'unsure'
        else:
            row.box, row.reason = 'nothing', 'on a Goodreads shelf with no reading recorded; you have it'
        return
    if status == 'wishlist':
        if kind == 'none':
            row.box = 'want_new'
        else:
            row.box, row.reason = 'want_nothing', WANT_REASONS[kind]
        return
    # Read-like
    if kind != 'none':
        # What Goodreads says differently on a book you have: shown, yours kept
        _, row.differs = _fill(d, status, have)
    if kind == 'wishlist':
        row.box = 'decide_wishlist'
    elif status == 'currently reading' and (kind == 'none' or not (have and have['status'])):
        row.box = 'decide_reading'
    elif kind == 'none':
        row.box = 'read_new'
    else:
        parts, _ = _fill(d, status, have)
        if parts:
            row.box = 'fill'
        else:
            # Differences are listed on the row and counted on the box
            row.box, row.reason = 'nothing', 'in Libaraxia and nothing missing'


def plan(conn, user):
    """Every staged row, classified fresh against the database now. Writes
    nothing. Returns None if the user has nothing staged."""
    staged = _load_staging(conn, user)
    if not staged:
        return None
    index = BookIndex(conn, user.id)
    remembered, skipped = _memory(conn, user.id, index)
    yours = _your_data(conn, user.id)
    owners = {r['id']: r['username'] for r in conn.execute(
        'SELECT u.id, u.username FROM users u JOIN library_members m ON m.user_id = u.id '
        'JOIN library_members me ON me.library_id = m.library_id WHERE me.user_id = ?', (user.id,))}

    rows, seen_books, seen_ids = [], {}, {}
    for s in staged:
        d = json.loads(s['data'])
        row = Row(s['line'], d, 'nothing')
        rows.append(row)
        if not d['title']:
            row.reason = 'no title'
            continue

        gid = d.get('goodreads_id')
        book = remembered.get(gid) if gid else None
        if book is None:
            book, _ = index.match(d['isbns'], d['title'], d['author'])
        earlier = (seen_ids.get(gid) if gid else None) or (seen_books.get(book['id']) if book else None)
        if earlier:
            row.same_as, row.reason = earlier, f'same book as line {earlier}'
            continue
        if gid:
            seen_ids[gid] = row.line
        if book is not None and book['id'] < 0:
            # A book an earlier row of this file would create
            row.same_as = -book['id']
            row.reason = f'same book as line {row.same_as}'
            continue

        have = None
        if book is not None:
            seen_books[book['id']] = row.line
            row.kind = _kind(book)
            row.book = _book_summary(book, owners)
            have = yours.get(book['id'])
            row.before = _before(book, have)
        _classify(row, have)

        box = BOXES[row.box]
        row.default = box['default']
        row.choices = ([box['default']] if box['default'] and box['default'] != 'ask' else []) + box['choices']
        if gid in skipped and row.box not in ('nothing', 'want_nothing'):
            # Skipped last time: Nothing to do, but the box's choices stay
            # so the skip can be undone. Asked rows are asked again instead.
            row.home_box, row.box = row.box, 'nothing'
            row.skipped_before, row.reason = True, 'skipped last time'
            row.default = 'skip'
            row.choices = ['skip'] + [c for c in row.choices if c != 'skip']

        if row.kind == 'none':
            # A book this row may create: later rows of the same book in
            # this file are "same book as line N", as the old importer had them
            index.add({'id': -row.line, 'isbn': d['isbns'][0] if d['isbns'] else None,
                       'title': d['title'], 'author': d['author'], 'removed_at': None,
                       'whose': 'own', 'is_wishlist_entry': 0, 'owned': 0})

        row.choice = s['choice'] if s['choice'] in row.choices else row.default
        row.parts, row.adds, row.preview = _parts_for(row, row.choice, have)

    digest = hashlib.sha256(json.dumps(
        [(r.line, r.box, r.book and r.book['id'], r.before, r.choice) for r in rows],
        sort_keys=True, default=str).encode()).hexdigest()
    return Plan(rows, staged[0]['filename'], digest)


# ------------------------------------------------------------------ choose

def choose(conn, user, lines, choice):
    """Save `choice` for the staged rows `lines`, where it's valid for the
    row's box. Returns {'saved': [lines], 'refused': [{line, error}],
    'plan': the fresh plan}. Commits."""
    if choice not in CHOICES or choice == 'ask':
        raise PlanError('That choice is not available.')
    try:
        wanted = {int(n) for n in lines or []}
    except (TypeError, ValueError):
        raise PlanError('That selection has a row that is not a line number.')
    if not wanted:
        raise PlanError('Select a row first.')
    current = plan(conn, user)
    if current is None:
        raise PlanError('Upload your export first.')

    saved, refused = [], []
    by_line = {r.line: r for r in current.rows}
    for line in sorted(wanted):
        row = by_line.get(line)
        if row is None:
            refused.append({'line': line, 'error': 'Not in your upload.'})
        elif choice not in row.choices:
            refused.append({'line': line, 'error': f'"{CHOICES[choice]}" is not a choice for this row.'})
        else:
            # The default is stored as NULL, so a row keeps following its box
            conn.execute('UPDATE goodreads_staging SET choice = ? WHERE user_id = ? AND line = ?',
                         (None if choice == row.default else choice, user.id, line))
            saved.append(line)
    conn.commit()
    return {'saved': saved, 'refused': refused, 'plan': plan(conn, user) if saved else current}


# ------------------------------------------------------------------ snapshots (undo)
# A journal item (bulk_edit_items) per book written, holding only the parts
# the row wrote: {"book", "status", "read_data", "sessions", "wishlist"}.
# `before` is those parts as they were (None where no row existed; the whole
# of `before` is NULL for a book the import created).

# Not the cover: the cover job will have set one, and that mustn't block undo
BOOK_PART = ('title', 'author', 'isbn', 'format', 'genre', 'owned', 'removed_at')


def _part(conn, user_id, book_id, name, session_ids=()):
    if name == 'sessions':
        marks = ','.join('?' * len(session_ids)) or 'NULL'
        return [dict(r) for r in conn.execute(
            f'SELECT session_id, date_started, date_completed FROM reading_sessions '
            f'WHERE user_id = ? AND book_id = ? AND session_id IN ({marks}) ORDER BY session_id',
            (user_id, book_id, *session_ids))]
    if name == 'book':
        row = conn.execute(f"SELECT {', '.join(BOOK_PART)} FROM books WHERE id = ? AND media_type = 'book'",
                           (book_id,)).fetchone()
        return None if row is None else dict(row)
    sql = {
        'status': 'SELECT status, created_at, updated_at, quiet FROM collections WHERE book_id = ? AND user_id = ?',
        'read_data': 'SELECT rating, comment FROM read_data WHERE book_id = ? AND user_id = ?',
        'wishlist': 'SELECT added_at, notes, purchase_link FROM wishlist WHERE book_id = ? AND user_id = ?',
    }[name]
    row = conn.execute(sql, (book_id, user_id)).fetchone()
    return None if row is None else dict(row)


def _snapshot(conn, user_id, book_id, names, session_ids=()):
    return {name: _part(conn, user_id, book_id, name, session_ids) for name in names}


def _write_read_data(conn, user_id, book_id, rating, review):
    """Fill a missing rating and/or set or append the review (the plan
    decided which). Never replaces a rating you have."""
    comment = review[1] if review else None
    exists = conn.execute('SELECT 1 FROM read_data WHERE user_id = ? AND book_id = ?',
                          (user_id, book_id)).fetchone()
    if not exists:
        conn.execute('INSERT INTO read_data (user_id, book_id, rating, comment) VALUES (?, ?, ?, ?)',
                     (user_id, book_id, rating, comment))
        return
    if rating:
        conn.execute('UPDATE read_data SET rating = ? WHERE user_id = ? AND book_id = ? AND rating IS NULL',
                     (rating, user_id, book_id))
    if comment is not None:
        conn.execute('UPDATE read_data SET comment = ? WHERE user_id = ? AND book_id = ?',
                     (comment, user_id, book_id))


def _write_row(conn, user, row, edit_id):
    """Write one row's parts and its journal item. Returns (book_id, wrote)."""
    from utils import goodreads as writers
    d, parts = row.data, row.parts
    wrote, names = [], []
    if parts.get('create'):
        create = parts['create']
        book_id = writers.create_book(conn, user.id, d, owned=create != 'not_owned')
        before = None
        wrote.append('book')
        names.append('book')
        if create == 'wishlist':
            writers.add_wishlist(conn, user.id, book_id, d['private_notes'], d['date_added'])
            wrote.append('wishlist')
            names.append('wishlist')
    else:
        book_id = row.book['id']
        # Checked again now, as for any write onto a book id (the household
        # copy may have been given away since the plan)
        if not can_view_book(conn, user, book_id):
            raise PlanError('Not found')
        if parts.get('wishlist_move'):
            names += ['book', 'wishlist']
        if parts.get('status'):
            names.append('status')
        if parts.get('rating') or parts.get('review'):
            names.append('read_data')
        before = _snapshot(conn, user.id, book_id, names)
        if parts.get('sessions'):
            before['sessions'] = []
        if parts.get('wishlist_move'):
            # Read it: off the wishlist; "don't want it" also means not owned
            conn.execute('DELETE FROM wishlist WHERE user_id = ? AND book_id = ?', (user.id, book_id))
            conn.execute('UPDATE books SET owned = ? WHERE id = ? AND added_by = ?',
                         (0 if parts['wishlist_move'] == 'drop_wish' else 1, book_id, user.id))
            wrote.append('wishlist')

    if parts.get('status'):
        writers.set_status(conn, user.id, book_id, parts['status'], d['date_added'], quiet=1)
        wrote.append('status')
    if parts.get('rating') or parts.get('review'):
        _write_read_data(conn, user.id, book_id, parts.get('rating'), parts.get('review'))
        if parts.get('rating'):
            wrote.append('rating')
        if parts.get('review'):
            wrote.append('review' if parts['review'][0] == 'set' else 'review_appended')
    session_ids = []
    if parts.get('sessions'):
        session_ids = writers.add_sessions(conn, user.id, book_id, parts['sessions'])
        wrote.append(f'sessions:{len(session_ids)}')

    if parts.get('create'):
        # A created book's snapshot covers everything written on it
        if parts.get('status'):
            names.append('status')
        if parts.get('rating') or parts.get('review'):
            names.append('read_data')
    if session_ids:
        names.append('sessions')
    after = _snapshot(conn, user.id, book_id, names, session_ids)
    conn.execute('INSERT INTO bulk_edit_items (edit_id, book_id, before, after) VALUES (?, ?, ?, ?)',
                 (edit_id, book_id, None if before is None else json.dumps(before, sort_keys=True),
                  json.dumps(after, sort_keys=True)))
    return book_id, wrote


# ------------------------------------------------------------------ apply

def _outcome(row):
    """The OUTCOMES key of a row that wrote."""
    box = row.home_box or row.box
    if box in ('decide_reading', 'decide_wishlist'):
        return 'decided'
    if box == 'fill':
        return 'filled'
    return row.parts['create']          # not_owned, library or wishlist


SUMMARY_WORDS = (('not_owned', 'added as not owned'), ('library', 'to your library'),
                 ('wishlist', 'to your wishlist'), ('filled', 'filled'), ('decided', 'decided'))


def _summary(counts):
    bits = [f'{counts[k]} {words}' for k, words in SUMMARY_WORDS if counts.get(k)]
    return 'Goodreads import: ' + (', '.join(bits) if bits else 'nothing written')


def apply(conn, user, fingerprint):
    """Write the plan the user reviewed. Raises StalePlan (with the fresh
    plan) if anything moved since `fingerprint`. One outcome per staged row;
    a row that fails leaves nothing behind and the rest carry on. Deletes the
    staging and commits. Returns the report."""
    current = plan(conn, user)
    if current is None:
        raise PlanError('Upload your export first.')
    if current.fingerprint != fingerprint:
        raise StalePlan(current)

    # Lazy sweep of old bulk journals, as bulk.apply does
    conn.execute("DELETE FROM bulk_edits WHERE created_at < datetime('now', ?)", (f'-{KEEP_DAYS} days',))
    # One transaction for the lot: without it the first SAVEPOINT would open
    # the transaction and its RELEASE would commit every row
    if not conn.in_transaction:
        conn.execute('BEGIN')
    edit_id = conn.execute("INSERT INTO bulk_edits (user_id, action, params, summary, item_count) "
                           "VALUES (?, 'goodreads', '{}', '', 0)", (user.id,)).lastrowid
    import_id = conn.execute('INSERT INTO goodreads_imports (user_id, edit_id, filename, row_count) '
                             'VALUES (?, ?, ?, ?)',
                             (user.id, edit_id, current.filename, len(current.rows))).lastrowid
    conn.execute('UPDATE bulk_edits SET params = ? WHERE id = ?',
                 (json.dumps({'import_id': import_id, 'edit_id': edit_id}, sort_keys=True), edit_id))

    counts = {key: 0 for key in OUTCOMES}
    report_rows = []
    written = 0

    def record(row, outcome, book_id, wrote):
        conn.execute('INSERT INTO goodreads_rows (import_id, line, goodreads_id, book_id, outcome, wrote, shelves) '
                     'VALUES (?, ?, ?, ?, ?, ?, ?)',
                     (import_id, row.line, row.data.get('goodreads_id'), book_id, outcome,
                      json.dumps(wrote), ','.join(row.data['shelves'])))

    for row in current.rows:
        book_id = row.book['id'] if row.book else None
        detail = row.reason
        if row.writes:
            conn.execute('SAVEPOINT goodreads_row')
            try:
                book_id, wrote = _write_row(conn, user, row, edit_id)
                outcome = _outcome(row)
                record(row, outcome, book_id, wrote)
                conn.execute('RELEASE goodreads_row')
                written += 1
                detail = ', '.join(row.adds)
            except Exception:
                logger.exception('Goodreads import: line %s (%r) failed', row.line, row.data['title'])
                conn.execute('ROLLBACK TO goodreads_row')
                conn.execute('RELEASE goodreads_row')
                outcome, book_id, detail = 'error', None, "couldn't import this row"
        elif row.choice == 'ask':
            # Not remembered as skipped: the next upload asks again
            outcome, detail = 'later', 'needs a decision'
            if book_id:
                record(row, outcome, book_id, [])
        elif row.choice == 'skip':
            outcome = 'skipped'
            if row.data['title']:
                record(row, outcome, None, [])
            book_id = None
        else:
            outcome = 'nothing'
            if book_id and not row.same_as:
                # Matched, nothing missing: still findable under From Goodreads
                record(row, outcome, book_id, [])
        counts[outcome] += 1
        report_rows.append({'line': row.line, 'title': row.data['title'], 'author': row.data['author'],
                            'outcome': outcome, 'detail': detail, 'book_id': book_id})

    summary = _summary(counts)
    if written:
        conn.execute('UPDATE bulk_edits SET summary = ?, item_count = ? WHERE id = ?', (summary, written, edit_id))
    else:
        # Nothing to undo: no journal (the import's provenance stays)
        conn.execute('DELETE FROM bulk_edits WHERE id = ?', (edit_id,))
        edit_id = None
    conn.execute('DELETE FROM goodreads_staging WHERE user_id = ?', (user.id,))
    conn.commit()
    return {'edit_id': edit_id, 'import_id': import_id, 'summary': summary,
            'total_rows': len(report_rows), 'outcomes': counts,
            'outcome_labels': list(OUTCOMES.items()), 'rows': report_rows}


# ------------------------------------------------------------------ undo (through the bulk journal)

def _journal_after(conn, params, book_id):
    item = conn.execute('SELECT after FROM bulk_edit_items WHERE edit_id = ? AND book_id = ?',
                        (params.get('edit_id'), book_id)).fetchone()
    return json.loads(item['after']) if item and item['after'] else {}


def _current(conn, user, book_id, params):
    """The same parts the import wrote, as they are now (undo's guard
    compares this with the journalled `after`)."""
    after = _journal_after(conn, params, book_id)
    ids = [s['session_id'] for s in after.get('sessions') or []]
    return _snapshot(conn, user.id, book_id, list(after), ids)


def _yours_beyond(conn, user, book_id, after):
    """Whether you have data on a created book that the import didn't write:
    another session, a tag, a collection entry, or a status, review or
    wishlist entry it didn't make."""
    ids = {s['session_id'] for s in after.get('sessions') or []}
    sessions = {r[0] for r in conn.execute('SELECT session_id FROM reading_sessions WHERE user_id = ? '
                                           'AND book_id = ?', (user.id, book_id))}
    if sessions - ids:
        return True
    if conn.execute('SELECT 1 FROM book_tags WHERE user_id = ? AND book_id = ?', (user.id, book_id)).fetchone():
        return True
    if conn.execute('SELECT 1 FROM collection_books cb JOIN user_collections uc ON uc.collection_id = cb.collection_id '
                    'WHERE uc.user_id = ? AND cb.book_id = ?', (user.id, book_id)).fetchone():
        return True
    return any(name not in after and _part(conn, user.id, book_id, name) is not None
               for name in ('status', 'read_data', 'wishlist'))


def _restore(conn, user, book_id, before, after, params):
    if before is None:
        # A book the import created: deleted only if nobody else has data
        # on it and you've added nothing of your own since
        book = conn.execute("SELECT added_by, cover_image_url FROM books WHERE id = ? AND media_type = 'book'",
                            (book_id,)).fetchone()
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
            ids = [s['session_id'] for s in after.get('sessions') or []]
            conn.executemany('DELETE FROM reading_sessions WHERE session_id = ? AND user_id = ? AND book_id = ?',
                             [(i, user.id, book_id) for i in ids])
        elif name == 'status':
            if was is None:
                conn.execute('DELETE FROM collections WHERE user_id = ? AND book_id = ?', (user.id, book_id))
        elif name == 'read_data':
            if was is None:
                conn.execute('DELETE FROM read_data WHERE user_id = ? AND book_id = ?', (user.id, book_id))
            else:
                conn.execute('UPDATE read_data SET rating = ?, comment = ? WHERE user_id = ? AND book_id = ?',
                             (was['rating'], was['comment'], user.id, book_id))
        elif name == 'wishlist' and was is not None:
            conn.execute('INSERT INTO wishlist (user_id, book_id, added_at, notes, purchase_link) '
                         'VALUES (?, ?, ?, ?, ?)',
                         (user.id, book_id, was['added_at'], was['notes'], was['purchase_link']))
        elif name == 'book' and was is not None:
            conn.execute('UPDATE books SET owned = ? WHERE id = ? AND added_by = ?',
                         (was['owned'], book_id, user.id))
    return True


def _after_undo(conn, user, edit_id):
    conn.execute('UPDATE goodreads_imports SET undone_at = CURRENT_TIMESTAMP WHERE edit_id = ? AND user_id = ?',
                 (edit_id, user.id))


def _not_a_bulk_edit(*args, **kwargs):
    raise BulkError('That bulk action is not available.')


# Looked up by bulk._action('goodreads'): only undo and the Profile list use it
ACTION = Action(
    params=_not_a_bulk_edit, plan=_not_a_bulk_edit, write=_not_a_bulk_edit,
    current=_current, restore=_restore,
    describe=lambda p: 'Goodreads import', summary=lambda p, n: 'Goodreads import',
    key=lambda b: None, label=lambda k, p: '', same_text=lambda p: '',
    after_undo=_after_undo)
