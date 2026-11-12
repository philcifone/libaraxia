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
from dataclasses import dataclass, field
from io import StringIO

from utils import media
from utils.book_matching import BookIndex
from utils.goodreads import REQUIRED_COLUMNS, ImportFileError, parse_row
from utils.media import BOOK, only
from utils.search import fold

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
            row.box = 'nothing'
            row.reason = ('in Libaraxia, nothing missing; yours kept' if row.differs
                          else 'in Libaraxia and nothing missing')


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
