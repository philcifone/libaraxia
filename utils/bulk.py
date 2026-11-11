"""Bulk edit (ROADMAP 14, docs/BULK-EDIT-SPEC.md): plan, apply, undo.

Every write goes through the same three-step shape:

  plan()   read-only: what would change, grouped, with a fingerprint
  apply()  re-plans, refuses if the fingerprint moved (StalePlan), then writes
           item by item, each in its own SAVEPOINT, journalling what it did
  undo()   puts the journalled "before" back, item by item, but only where
           the item still looks like the journalled "after"

Takes a connection and a user (anything with `id` and `is_admin`) and uses no
Flask context, so tests and scripts drive it directly. The caller's request
only has to turn ids and JSON into these calls (blueprints/bulk.py).

The request names an action key; which table and column it touches comes
from ACTIONS, never from the request.

Two kinds of action:
  item edits  change the `books` row: genre, format, owned, remove, restore.
              Owner or admin only.
  marks       change the user's own rows on any item they can view
              (models.can_view_book): status, shelves, tags.

Snapshots. `before` and `after` are dicts of every column an action touches
(None where no row existed), so undo is exact. A mark's snapshot is the whole
row, with its timestamps.
"""
import hashlib
import json
import logging
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone

from models import can_view_book
from utils import media, search
from utils.shelves import SECTION_NAMES

logger = logging.getLogger(__name__)

MAX_ITEMS = 500           # per operation: a bounded edit is a bounded mistake
KEEP_DAYS = 30            # how long the journal can undo
MAX_GENRE = 80
MAX_TAG = 50              # tags.py has no cap; a bulk edit shouldn't be the way to find that out
MAX_SHELF = 60
MAX_NOTE = 200            # the single-item remove route's cap

# Skip reasons, worded for the review sheet
NOT_FOUND = 'Not found'
NOT_YOURS = 'Not yours'
ALREADY_REMOVED = 'Already removed'


class BulkError(Exception):
    """A refused request; the message is safe to show a person."""


class TooMany(BulkError):
    pass


class StalePlan(BulkError):
    """The data moved between plan and apply. `plan` is the fresh one."""
    def __init__(self, plan):
        super().__init__('Some items changed since you looked.')
        self.plan = plan


@dataclass
class PlanRow:
    id: int
    outcome: str                  # 'change', 'same' or 'skip'
    reason: str = ''              # why, for a skip
    # The next four are left empty for items the user can't see, so a forged
    # id can't read another user's catalogue through the review
    title: str = ''
    creator: str = ''
    cover: str = None
    media_type: str = ''
    before: dict = None           # snapshot of what the action touches, now (None: no row)
    after: dict = None            # ...and what it would be
    removed: bool = False


@dataclass
class Group:
    """Changes that share a before value, so 44 changes read as three lines."""
    key: object
    label: str
    ids: list = field(default_factory=list)

    @property
    def count(self):
        return len(self.ids)


@dataclass
class Plan:
    action: str
    params: dict
    rows: list
    groups: list
    same: int
    same_text: str
    skipped: dict                 # reason -> [ids]
    notes: list
    fingerprint: str

    @property
    def changes(self):
        return sum(g.count for g in self.groups)

    def as_dict(self):
        """The review sheet's data (JSON-safe). Items carry a title and cover
        only for what the user may see (PlanRow leaves the rest empty)."""
        by_id = {r.id: r for r in self.rows}

        def item(book_id):
            r = by_id[book_id]
            return {'id': r.id, 'title': r.title, 'creator': r.creator, 'cover': r.cover}
        return {
            'action': self.action, 'params': self.params, 'fingerprint': self.fingerprint,
            'describe': ACTIONS[self.action].describe(self.params),
            'changes': self.changes, 'same': self.same, 'same_text': self.same_text,
            'groups': [{'key': g.key, 'label': g.label, 'count': g.count,
                        'items': [item(i) for i in g.ids]} for g in self.groups],
            'skipped': [{'reason': reason, 'count': len(ids), 'items': [item(i) for i in ids]}
                        for reason, ids in self.skipped.items()],
            'notes': self.notes,
            'ids': [r.id for r in self.rows],         # in order: a view selection's resolved ids
        }


@dataclass
class Result:
    edit_id: int                  # None when nothing was written
    summary: str
    changed: int = 0
    failed: int = 0
    skipped: int = 0              # undo: items changed since, left alone


def _quote(text):
    return f'“{text}”'


def _count(n):
    return f'{n} item{"" if n == 1 else "s"}'


def _owner_ok(user):
    """The SQL half of owner-or-admin: `AND (added_by = ? OR ? = 1)`."""
    return ' AND (added_by = ? OR ? = 1)', [user.id, int(user.is_admin)]


# ------------------------------------------------------------------ genre

def clean_genre(value):
    """Trim, collapse inner whitespace, refuse control characters, cap the
    length. Case is the user's: "Sci-Fi" stays "Sci-Fi". Returns the cleaned
    text, or raises BulkError."""
    text = re.sub(r'\s+', ' ', str(value)).strip() if value is not None else ''
    if not text:
        raise BulkError('Pick a genre first.')
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in text):
        raise BulkError("That genre has characters that can't be used.")
    if len(text) > MAX_GENRE:
        raise BulkError(f'Keep the genre under {MAX_GENRE + 1} characters.')
    return text


def _genre_params(conn, user, params):
    """{'genre': text} sets it, {'genre': None} clears it ("(no genre)")."""
    if not isinstance(params, dict) or 'genre' not in params:
        raise BulkError('Pick a genre first.')
    return {'genre': None if params['genre'] is None else clean_genre(params['genre'])}


def _genre_plan(conn, user, book, params):
    before = {'genre': book['genre']}
    after = {'genre': params['genre']}
    # "" and NULL both mean no genre
    return ('same' if (book['genre'] or None) == params['genre'] else 'change'), '', before, after


def _genre_write(conn, user, book_id, before, after, params):
    """The WHERE repeats the permission and the value the plan saw, so a
    change in between is skipped, not overwritten."""
    guard, args = _owner_ok(user)
    cur = conn.execute('UPDATE books SET genre = ? WHERE id = ? AND genre IS ?' + guard,
                       (after['genre'], book_id, before['genre'], *args))
    return cur.rowcount == 1, after


def _genre_current(conn, user, book_id, params):
    row = conn.execute('SELECT genre FROM books WHERE id = ?', (book_id,)).fetchone()
    return None if row is None else {'genre': row['genre']}


def _genre_restore(conn, user, book_id, before, after, params):
    guard, args = _owner_ok(user)
    return conn.execute('UPDATE books SET genre = ? WHERE id = ?' + guard,
                        (before['genre'], book_id, *args)).rowcount == 1


# ------------------------------------------------------------------ format

def _format_choices():
    """Every format a request may name: each type's own, plus 'Book'."""
    return {f for formats in media.FORMATS.values() for f in formats}


def _format_params(conn, user, params):
    value = params.get('format') if isinstance(params, dict) else None
    if value not in _format_choices():
        raise BulkError('Pick a format first.')
    return {'format': value}


def _stored_format(media_type, value):
    """What goes in books.format: a plain book stores NULL, never 'Book'."""
    return media.book_format(value) if media_type == media.BOOK else value


def _format_plan(conn, user, book, params):
    kind = media.media_type_of(book)
    if params['format'] not in media.FORMATS.get(kind, ()):
        return 'skip', f'Not a format for {SECTION_NAMES[kind]}', None, None
    stored = _stored_format(kind, params['format'])
    now = _stored_format(kind, book['format']) if kind == media.BOOK else (book['format'] or None)
    # 'type' only names the group ("Book" for a plain book); undo restores 'format' alone
    return ('same' if now == stored else 'change'), '', {'format': book['format'], 'type': kind}, {'format': stored}


def _format_write(conn, user, book_id, before, after, params):
    guard, args = _owner_ok(user)
    cur = conn.execute('UPDATE books SET format = ? WHERE id = ? AND format IS ?' + guard,
                       (after['format'], book_id, before['format'], *args))
    return cur.rowcount == 1, after


def _format_current(conn, user, book_id, params):
    row = conn.execute('SELECT format FROM books WHERE id = ?', (book_id,)).fetchone()
    return None if row is None else {'format': row['format']}


def _format_restore(conn, user, book_id, before, after, params):
    guard, args = _owner_ok(user)
    return conn.execute('UPDATE books SET format = ? WHERE id = ?' + guard,
                        (before['format'], book_id, *args)).rowcount == 1


def _format_notes(rows, params):
    changing = [r for r in rows if r.outcome == 'change']
    if params['format'] == media.AUDIOBOOK and changing:
        return ["Audiobooks don't count toward pages read."]
    return []


# ------------------------------------------------------------------ owned

def _owned_params(conn, user, params):
    value = params.get('owned') if isinstance(params, dict) else None
    if value in (1, True, '1'):
        return {'owned': 1}
    if value in (0, False, '0'):
        return {'owned': 0}
    raise BulkError('Choose owned or not owned first.')


def _owned_plan(conn, user, book, params):
    before, after = {'owned': book['owned']}, {'owned': params['owned']}
    return ('same' if book['owned'] == params['owned'] else 'change'), '', before, after


def _owned_write(conn, user, book_id, before, after, params):
    guard, args = _owner_ok(user)
    cur = conn.execute('UPDATE books SET owned = ? WHERE id = ? AND owned = ?' + guard,
                       (after['owned'], book_id, before['owned'], *args))
    return cur.rowcount == 1, after


def _owned_current(conn, user, book_id, params):
    row = conn.execute('SELECT owned FROM books WHERE id = ?', (book_id,)).fetchone()
    return None if row is None else {'owned': row['owned']}


def _owned_restore(conn, user, book_id, before, after, params):
    guard, args = _owner_ok(user)
    return conn.execute('UPDATE books SET owned = ? WHERE id = ?' + guard,
                        (before['owned'], book_id, *args)).rowcount == 1


def _owned_name(value):
    return 'Owned' if value else 'Not owned'


def _owned_notes(rows, params):
    notes = []
    if not params['owned'] and any(r.outcome == 'change' for r in rows):
        notes.append('Not owned items leave your shelf. Reviews, ratings and history stay.')
    # The single-item route also puts a removed item back; a bulk edit says what it
    # writes and nothing else, so removal is left as it is
    if any(r.removed and r.outcome in ('change', 'same') for r in rows):
        notes.append('Items that were removed from the library stay removed.')
    return notes


# ------------------------------------------------------------------ remove / restore

def _remove_params(conn, user, params):
    note = (params.get('note') if isinstance(params, dict) else None) or ''
    return {'note': str(note).strip()[:MAX_NOTE] or None}


def _remove_plan(conn, user, book, params):
    if book['removed_at']:
        return 'skip', ALREADY_REMOVED, None, None
    before = {'removed_at': book['removed_at'], 'removed_note': book['removed_note']}
    # The timestamp is the database's, taken when the row is written (write()
    # returns the real one); this placeholder only makes the fingerprint stable
    return 'change', '', before, {'removed_at': 'now', 'removed_note': params['note']}


def _removal_now(conn, book_id):
    row = conn.execute('SELECT removed_at, removed_note FROM books WHERE id = ?', (book_id,)).fetchone()
    return None if row is None else {'removed_at': row['removed_at'], 'removed_note': row['removed_note']}


def _remove_write(conn, user, book_id, before, after, params):
    guard, args = _owner_ok(user)
    cur = conn.execute('UPDATE books SET removed_at = CURRENT_TIMESTAMP, removed_note = ? '
                       'WHERE id = ? AND removed_at IS NULL' + guard, (params['note'], book_id, *args))
    return cur.rowcount == 1, _removal_now(conn, book_id)


def _removal_current(conn, user, book_id, params):
    return _removal_now(conn, book_id)


def _removal_restore(conn, user, book_id, before, after, params):
    guard, args = _owner_ok(user)
    return conn.execute('UPDATE books SET removed_at = ?, removed_note = ? WHERE id = ?' + guard,
                        (before['removed_at'], before['removed_note'], book_id, *args)).rowcount == 1


def _remove_notes(rows, params):
    return ['These leave your shelf. Reviews, ratings and history stay.'] if any(
        r.outcome == 'change' for r in rows) else []


def _restore_params(conn, user, params):
    return {}


def _restore_plan(conn, user, book, params):
    if not book['removed_at']:
        return 'same', '', None, None
    before = {'removed_at': book['removed_at'], 'removed_note': book['removed_note']}
    return 'change', '', before, {'removed_at': None, 'removed_note': None}


def _restore_write(conn, user, book_id, before, after, params):
    guard, args = _owner_ok(user)
    cur = conn.execute('UPDATE books SET removed_at = NULL, removed_note = NULL WHERE id = ? '
                       'AND removed_at IS ? AND removed_note IS ?' + guard,
                       (book_id, before['removed_at'], before['removed_note'], *args))
    return cur.rowcount == 1, after


# ------------------------------------------------------------------ status (a mark)

def _status_params(conn, user, params):
    value = params.get('status') if isinstance(params, dict) else None
    allowed = {s for statuses in media.STATUSES.values() for s in statuses} | {'untracked'}
    if value not in allowed:
        raise BulkError('Pick a status first.')
    return {'status': value}


def _status_row(conn, user, book_id):
    """The user's collections row as a snapshot, or None. Every column an
    undo needs to put it back exactly."""
    row = conn.execute('SELECT status, created_at, updated_at, quiet FROM collections '
                       'WHERE user_id = ? AND book_id = ?', (user.id, book_id)).fetchone()
    return None if row is None else dict(row)


def _status_plan(conn, user, book, params):
    kind = media.media_type_of(book)
    row = _status_row(conn, user, book['id'])
    if params['status'] == 'untracked':
        return ('same' if row is None else 'change'), '', row, None
    if not media.is_valid_status(kind, params['status']):
        return 'skip', f'Not a status for {SECTION_NAMES[kind]}', None, None
    if row and row['status'] == params['status']:
        return 'same', '', row, None
    return 'change', '', row, {'status': params['status']}


def _status_write(conn, user, book_id, before, after, params):
    """Never creates reading sessions or ratings. A new row is quiet (kept out
    of friends' feed); an update leaves quiet as it was."""
    if params['status'] == 'untracked':
        cur = conn.execute('DELETE FROM collections WHERE user_id = ? AND book_id = ? AND status = ?',
                           (user.id, book_id, before['status']))
        return cur.rowcount == 1, None
    if before is None:
        cur = conn.execute(
            'INSERT INTO collections (user_id, book_id, status, created_at, updated_at, quiet) '
            'SELECT ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1 '
            'WHERE NOT EXISTS (SELECT 1 FROM collections WHERE user_id = ? AND book_id = ?)',
            (user.id, book_id, params['status'], user.id, book_id))
    else:
        cur = conn.execute('UPDATE collections SET status = ?, updated_at = CURRENT_TIMESTAMP '
                           'WHERE user_id = ? AND book_id = ? AND status = ?',
                           (params['status'], user.id, book_id, before['status']))
    return cur.rowcount == 1, _status_row(conn, user, book_id)


def _status_current(conn, user, book_id, params):
    return _status_row(conn, user, book_id)


def _status_restore(conn, user, book_id, before, after, params):
    if before is None:                       # the edit created the row
        return conn.execute('DELETE FROM collections WHERE user_id = ? AND book_id = ?',
                            (user.id, book_id)).rowcount == 1
    if after is None:                        # the edit deleted it: put it back as it was
        conn.execute('INSERT INTO collections (user_id, book_id, status, created_at, updated_at, quiet) '
                     'VALUES (?, ?, ?, ?, ?, ?)', (user.id, book_id, before['status'], before['created_at'],
                                                   before['updated_at'], before['quiet']))
        return True
    return conn.execute('UPDATE collections SET status = ?, created_at = ?, updated_at = ?, quiet = ? '
                        'WHERE user_id = ? AND book_id = ?',
                        (before['status'], before['created_at'], before['updated_at'], before['quiet'],
                         user.id, book_id)).rowcount == 1


def _status_name(value):
    return media.STATUS_LABELS.get(value) or 'No status'


def _status_notes(rows, params):
    if not any(r.outcome == 'change' for r in rows):
        return []
    if params['status'] == 'untracked':
        # Clearing a status never touches what hangs on the item (data principles):
        # reviews, ratings and reading dates go only from the item's own page
        return ['Reviews, ratings and reading dates are kept. Delete those on the item\'s page.']
    return ['No reading dates are added, and no reviews.',
            "These changes don't appear in your friends' feed."]


# ------------------------------------------------------------------ shelves (a mark)

def _shelf_params_for(adding):
    def params_for(conn, user, params):
        params = params if isinstance(params, dict) else {}
        kind = params.get('media_type')
        if kind not in media.MEDIA_TYPES:
            raise BulkError('Pick a collection first.')
        new = params.get('new_shelf')
        if new is not None:
            if not adding:
                raise BulkError('Pick a collection first.')
            name = re.sub(r'\s+', ' ', str(new)).strip()
            if not name:
                raise BulkError('Give the new collection a name.')
            if len(name) > MAX_SHELF or any(ord(ch) < 32 for ch in name):
                raise BulkError(f'Keep the collection name to {MAX_SHELF} plain characters or fewer.')
            if conn.execute('SELECT 1 FROM user_collections WHERE user_id = ? AND media_type = ? AND name = ?',
                            (user.id, kind, name)).fetchone():
                raise BulkError(f'You already have a collection called {_quote(name)} in {SECTION_NAMES[kind]}. '
                                'Pick it from the list.')
            return {'new_shelf': name, 'shelf_name': name, 'media_type': kind}
        shelf = conn.execute('SELECT collection_id, name, media_type FROM user_collections '
                             'WHERE collection_id = ? AND user_id = ?', (params.get('shelf_id'), user.id)).fetchone()
        if shelf is None:
            raise BulkError('That collection was not found.')
        return {'shelf_id': shelf['collection_id'], 'shelf_name': shelf['name'], 'media_type': shelf['media_type']}
    return params_for


def _shelf_row(conn, shelf_id, book_id):
    row = conn.execute('SELECT collection_id AS shelf_id, added_at FROM collection_books '
                       'WHERE collection_id = ? AND book_id = ?', (shelf_id, book_id)).fetchone()
    return None if row is None else dict(row)


def _shelf_prepare(conn, user, params):
    """Create a "New shelf..." now, inside apply's transaction, so it exists
    for the items and goes away again if none were written."""
    if 'new_shelf' not in params:
        return params
    try:
        shelf_id = conn.execute('INSERT INTO user_collections (user_id, name, media_type) VALUES (?, ?, ?)',
                                (user.id, params['new_shelf'], params['media_type'])).lastrowid
    except sqlite3.IntegrityError:
        raise BulkError(f'You already have a collection called {_quote(params["new_shelf"])} there.')
    return {**params, 'shelf_id': shelf_id, 'created_shelf': True}


def _shelf_add_plan(conn, user, book, params):
    kind = media.media_type_of(book)
    if kind != params['media_type']:
        return 'skip', f'Collection is for {SECTION_NAMES[params["media_type"]]}', None, None
    row = None if 'new_shelf' in params else _shelf_row(conn, params['shelf_id'], book['id'])
    return ('same' if row else 'change'), '', None, ({'shelf': params['shelf_name']} if not row else None)


def _shelf_add_write(conn, user, book_id, before, after, params):
    cur = conn.execute('INSERT INTO collection_books (collection_id, book_id) SELECT ?, ? '
                       'WHERE NOT EXISTS (SELECT 1 FROM collection_books WHERE collection_id = ? AND book_id = ?)',
                       (params['shelf_id'], book_id, params['shelf_id'], book_id))
    return cur.rowcount == 1, _shelf_row(conn, params['shelf_id'], book_id)


def _shelf_current(conn, user, book_id, params):
    return _shelf_row(conn, params['shelf_id'], book_id)


def _shelf_add_restore(conn, user, book_id, before, after, params):
    return conn.execute('DELETE FROM collection_books WHERE collection_id = ? AND book_id = ?',
                        (params['shelf_id'], book_id)).rowcount == 1


def _shelf_remove_plan(conn, user, book, params):
    kind = media.media_type_of(book)
    if kind != params['media_type']:
        return 'skip', f'Collection is for {SECTION_NAMES[params["media_type"]]}', None, None
    row = _shelf_row(conn, params['shelf_id'], book['id'])
    return ('change' if row else 'same'), '', row, None


def _shelf_remove_write(conn, user, book_id, before, after, params):
    cur = conn.execute('DELETE FROM collection_books WHERE collection_id = ? AND book_id = ?',
                       (params['shelf_id'], book_id))
    return cur.rowcount == 1, None


def _shelf_remove_restore(conn, user, book_id, before, after, params):
    conn.execute('INSERT OR IGNORE INTO collection_books (collection_id, book_id, added_at) VALUES (?, ?, ?)',
                 (params['shelf_id'], book_id, before['added_at']))
    return True


def _shelf_add_notes(rows, params):
    return [f'A new collection {_quote(params["new_shelf"])} will be created.'] if 'new_shelf' in params else []


# ------------------------------------------------------------------ tags (a mark)

def _tag_params(conn, user, params):
    """Cleaned as blueprints/tags.py does: strip, lowercase."""
    tag = str((params.get('tag') if isinstance(params, dict) else None) or '').strip().lower()
    if not tag:
        raise BulkError('Pick a tag first.')
    if len(tag) > MAX_TAG or any(ord(ch) < 32 for ch in tag):
        raise BulkError(f'Keep the tag to {MAX_TAG} plain characters or fewer.')
    return {'tag': tag}


def _tag_row(conn, user, book_id, tag):
    row = conn.execute('SELECT tag_name AS tag, created_at FROM book_tags '
                       'WHERE user_id = ? AND book_id = ? AND tag_name = ?', (user.id, book_id, tag)).fetchone()
    return None if row is None else dict(row)


def _tag_add_plan(conn, user, book, params):
    row = _tag_row(conn, user, book['id'], params['tag'])
    return ('same' if row else 'change'), '', None, (None if row else {'tag': params['tag']})


def _tag_add_write(conn, user, book_id, before, after, params):
    cur = conn.execute('INSERT INTO book_tags (user_id, book_id, tag_name) SELECT ?, ?, ? WHERE NOT EXISTS '
                       '(SELECT 1 FROM book_tags WHERE user_id = ? AND book_id = ? AND tag_name = ?)',
                       (user.id, book_id, params['tag'], user.id, book_id, params['tag']))
    return cur.rowcount == 1, _tag_row(conn, user, book_id, params['tag'])


def _tag_current(conn, user, book_id, params):
    return _tag_row(conn, user, book_id, params['tag'])


def _tag_add_restore(conn, user, book_id, before, after, params):
    return conn.execute('DELETE FROM book_tags WHERE user_id = ? AND book_id = ? AND tag_name = ?',
                        (user.id, book_id, params['tag'])).rowcount == 1


def _tag_remove_plan(conn, user, book, params):
    row = _tag_row(conn, user, book['id'], params['tag'])
    return ('change' if row else 'same'), '', row, None


def _tag_remove_write(conn, user, book_id, before, after, params):
    cur = conn.execute('DELETE FROM book_tags WHERE user_id = ? AND book_id = ? AND tag_name = ?',
                       (user.id, book_id, params['tag']))
    return cur.rowcount == 1, None


def _tag_remove_restore(conn, user, book_id, before, after, params):
    conn.execute('INSERT OR IGNORE INTO book_tags (user_id, book_id, tag_name, created_at) VALUES (?, ?, ?, ?)',
                 (user.id, book_id, before['tag'], before['created_at']))
    return True


# ------------------------------------------------------------------ the whitelist

def _no_notes(rows, params):
    return []


@dataclass(frozen=True)
class Action:
    """One whitelist entry."""
    params: callable       # (conn, user, request params) -> normalised params, or BulkError
    plan: callable         # (conn, user, book, params) -> (outcome, reason, before, after)
    write: callable        # (conn, user, book_id, before, after, params) -> (written?, real after)
    current: callable      # (conn, user, book_id, params) -> the snapshot now, for undo's check
    restore: callable      # (conn, user, book_id, before, after, params) -> written?
    describe: callable     # (params) -> the review's header
    summary: callable      # (params, count) -> the banner, after the fact
    key: callable          # (before) -> what changes are grouped by
    label: callable        # (key, params) -> a group's line
    same_text: callable    # (params) -> "Already ..."
    notes: callable = _no_notes
    owner_only: bool = False         # item edits: the owner or an admin; marks: anyone who can view it
    prepare: callable = None         # (conn, user, params) -> params, once per apply


def _genre_name(value):
    return value or '(no genre)'


def _arrow(before, after):
    return f'{before} → {after}'


ACTIONS = {
    'genre': Action(
        _genre_params, _genre_plan, _genre_write, _genre_current, _genre_restore,
        describe=lambda p: f'Set genre to {_quote(p["genre"])}' if p['genre'] else 'Clear the genre',
        summary=lambda p, n: (f'Genre set to {p["genre"]}' if p['genre'] else 'Genre cleared') + f' on {_count(n)}',
        key=lambda b: (b['genre'] or None), label=lambda k, p: _arrow(_genre_name(k), _genre_name(p['genre'])),
        same_text=lambda p: f'Already {_quote(p["genre"])}' if p['genre'] else 'Already no genre',
        owner_only=True),
    'format': Action(
        _format_params, _format_plan, _format_write, _format_current, _format_restore,
        describe=lambda p: f'Set format to {media.format_label(p["format"])}',
        summary=lambda p, n: f'Format set to {media.format_label(p["format"])} on {_count(n)}',
        key=lambda b: media.format_label(b['format']) or ('Book' if b.get('type') == media.BOOK else None),
        label=lambda k, p: _arrow(k or '(no format)', media.format_label(p['format'])),
        same_text=lambda p: f'Already {media.format_label(p["format"])}',
        notes=_format_notes, owner_only=True),
    'owned': Action(
        _owned_params, _owned_plan, _owned_write, _owned_current, _owned_restore,
        describe=lambda p: f'Mark as {_owned_name(p["owned"]).lower()}',
        summary=lambda p, n: f'Marked {_owned_name(p["owned"]).lower()} on {_count(n)}',
        key=lambda b: _owned_name(b['owned']), label=lambda k, p: _arrow(k, _owned_name(p['owned'])),
        same_text=lambda p: f'Already {_owned_name(p["owned"]).lower()}',
        notes=_owned_notes, owner_only=True),
    'remove': Action(
        _remove_params, _remove_plan, _remove_write, _removal_current, _removal_restore,
        describe=lambda p: 'Remove from the library' + (f' ({p["note"]})' if p['note'] else ''),
        summary=lambda p, n: f'Removed {_count(n)} from the library',
        key=lambda b: None,
        label=lambda k, p: 'On the shelf → Removed' + (f' ({p["note"]})' if p['note'] else ''),
        same_text=lambda p: 'Already removed',
        notes=_remove_notes, owner_only=True),
    'restore': Action(
        _restore_params, _restore_plan, _restore_write, _removal_current, _removal_restore,
        describe=lambda p: 'Put back on the shelf',
        summary=lambda p, n: f'Put {_count(n)} back on the shelf',
        key=lambda b: None, label=lambda k, p: 'Removed → On the shelf',
        same_text=lambda p: 'Already on the shelf', owner_only=True),
    'status': Action(
        _status_params, _status_plan, _status_write, _status_current, _status_restore,
        describe=lambda p: 'Clear the status' if p['status'] == 'untracked'
                           else f'Set status to {_status_name(p["status"])}',
        summary=lambda p, n: ('Status cleared' if p['status'] == 'untracked'
                              else f'Status set to {_status_name(p["status"])}') + f' on {_count(n)}',
        key=lambda b: (b['status'] if b else None),
        label=lambda k, p: _arrow(_status_name(k), 'No status' if p['status'] == 'untracked'
                                  else _status_name(p['status'])),
        same_text=lambda p: 'Already no status' if p['status'] == 'untracked'
                            else f'Already {_status_name(p["status"])}',
        notes=_status_notes),
    'shelf_add': Action(
        _shelf_params_for(True), _shelf_add_plan, _shelf_add_write, _shelf_current, _shelf_add_restore,
        describe=lambda p: f'Add to {_quote(p["shelf_name"])}',
        summary=lambda p, n: f'Added {_count(n)} to {p["shelf_name"]}',
        key=lambda b: None, label=lambda k, p: f'Add to {_quote(p["shelf_name"])}',
        same_text=lambda p: f'Already in {_quote(p["shelf_name"])}',
        notes=_shelf_add_notes, prepare=_shelf_prepare),
    'shelf_remove': Action(
        _shelf_params_for(False), _shelf_remove_plan, _shelf_remove_write, _shelf_current, _shelf_remove_restore,
        describe=lambda p: f'Remove from {_quote(p["shelf_name"])}',
        summary=lambda p, n: f'Removed {_count(n)} from {p["shelf_name"]}',
        key=lambda b: None, label=lambda k, p: f'Remove from {_quote(p["shelf_name"])}',
        same_text=lambda p: f'Not in {_quote(p["shelf_name"])}'),
    'tag_add': Action(
        _tag_params, _tag_add_plan, _tag_add_write, _tag_current, _tag_add_restore,
        describe=lambda p: f'Add the tag {_quote(p["tag"])}',
        summary=lambda p, n: f'Tag {_quote(p["tag"])} added to {_count(n)}',
        key=lambda b: None, label=lambda k, p: f'Add the tag {_quote(p["tag"])}',
        same_text=lambda p: f'Already tagged {_quote(p["tag"])}'),
    'tag_remove': Action(
        _tag_params, _tag_remove_plan, _tag_remove_write, _tag_current, _tag_remove_restore,
        describe=lambda p: f'Remove the tag {_quote(p["tag"])}',
        summary=lambda p, n: f'Tag {_quote(p["tag"])} removed from {_count(n)}',
        key=lambda b: None, label=lambda k, p: f'Remove the tag {_quote(p["tag"])}',
        same_text=lambda p: f'Not tagged {_quote(p["tag"])}'),
}


# ------------------------------------------------------------------ plan

def _ids(ids):
    """Distinct ints in the order given, capped."""
    out = []
    for raw in ids or []:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            raise BulkError('That selection has an item that is not an id.')
        if value not in out:
            out.append(value)
    if len(out) > MAX_ITEMS:
        raise TooMany(f'Too many for one edit ({len(out)}). Narrow the view to {MAX_ITEMS} or fewer.')
    return out


def _action(key):
    if key not in ACTIONS:
        raise BulkError('That bulk action is not available.')
    return ACTIONS[key]


BOOK_COLUMNS = 'id, title, author, cover_image_url, media_type, genre, added_by, format, owned, removed_at, removed_note'


def plan(conn, user, action, params, ids):
    """What `action` with `params` would do to `ids` for `user`. Writes nothing."""
    act = _action(action)
    params = act.params(conn, user, params)
    ids = _ids(ids)
    if not ids:
        raise BulkError('Select something first.')

    rows = []
    for book_id in ids:
        book = conn.execute(f'SELECT {BOOK_COLUMNS} FROM books WHERE id = ?', (book_id,)).fetchone()
        if book is None or not can_view_book(conn, user, book_id):
            rows.append(PlanRow(book_id, 'skip', NOT_FOUND))
            continue
        shown = dict(title=book['title'], creator=book['author'], cover=book['cover_image_url'],
                     media_type=book['media_type'], removed=bool(book['removed_at']))
        if act.owner_only and not (user.is_admin or book['added_by'] == user.id):
            rows.append(PlanRow(book_id, 'skip', NOT_YOURS, **shown))
            continue
        outcome, reason, before, after = act.plan(conn, user, book, params)
        rows.append(PlanRow(book_id, outcome, reason, before=before, after=after, **shown))

    # Groups by before value, largest first, "no value" last
    by_key = {}
    for row in rows:
        if row.outcome == 'change':
            key = act.key(row.before)
            by_key.setdefault(key, Group(key, act.label(key, params))).ids.append(row.id)
    groups = sorted(by_key.values(), key=lambda g: (g.key is None, -g.count))

    skipped = {}
    for row in rows:
        if row.outcome == 'skip':
            skipped.setdefault(row.reason, []).append(row.id)

    digest = hashlib.sha256(json.dumps(
        [action, params, sorted((r.id, r.before, r.after, r.outcome) for r in rows)],
        sort_keys=True, default=str).encode()).hexdigest()
    return Plan(action, params, rows, groups, sum(r.outcome == 'same' for r in rows),
                act.same_text(params), skipped, act.notes(rows, params), digest)


# ------------------------------------------------------------------ apply

def _snap(value):
    return None if value is None else json.dumps(value, sort_keys=True)


def apply(conn, user, action, params, ids, fingerprint, excluded_ids=()):
    """Write the plan the user reviewed, minus `excluded_ids` (the groups and
    items they unticked). Raises StalePlan, carrying the new plan, if the
    data moved since `fingerprint` was made. Commits."""
    act = _action(action)
    current = plan(conn, user, action, params, ids)
    if current.fingerprint != fingerprint:
        raise StalePlan(current)

    excluded = {int(i) for i in excluded_ids or []}
    chosen = [r for r in current.rows if r.outcome == 'change' and r.id not in excluded]
    if not chosen:
        raise BulkError('Nothing to change.')

    # Lazy sweep of old journals; their items go by cascade. No scheduler.
    conn.execute("DELETE FROM bulk_edits WHERE created_at < datetime('now', ?)", (f'-{KEEP_DAYS} days',))

    # One transaction for the lot: without it the first SAVEPOINT would open
    # the transaction and its RELEASE would commit every item.
    if not conn.in_transaction:
        conn.execute('BEGIN')
    try:
        run = act.prepare(conn, user, current.params) if act.prepare else current.params
    except BulkError:
        conn.rollback()
        raise
    edit_id = conn.execute(
        'INSERT INTO bulk_edits (user_id, action, params, summary, item_count) VALUES (?, ?, ?, ?, 0)',
        (user.id, action, json.dumps(run, sort_keys=True), '')).lastrowid

    changed = failed = 0
    for row in chosen:
        conn.execute('SAVEPOINT bulk_item')
        try:
            # The journal row goes in the same savepoint as the change, so
            # the journal can't disagree with the data
            written, after = act.write(conn, user, row.id, row.before, row.after, run)
            if written:
                conn.execute('INSERT INTO bulk_edit_items (edit_id, book_id, before, after) VALUES (?, ?, ?, ?)',
                             (edit_id, row.id, _snap(row.before), _snap(after)))
                changed += 1
            else:
                # Moved between the plan and this write: left alone
                conn.execute('ROLLBACK TO bulk_item')
                failed += 1
            conn.execute('RELEASE bulk_item')
        except Exception:
            logger.exception('Bulk %s: item %s failed', action, row.id)
            conn.execute('ROLLBACK TO bulk_item')
            conn.execute('RELEASE bulk_item')
            failed += 1

    if changed == 0:
        conn.execute('DELETE FROM bulk_edits WHERE id = ?', (edit_id,))
        if run.get('created_shelf'):
            conn.execute('DELETE FROM user_collections WHERE collection_id = ? AND user_id = ?',
                         (run['shelf_id'], user.id))
        conn.commit()
        return Result(None, 'Nothing was changed.', 0, failed)
    summary = act.summary(run, changed)
    if failed:
        summary += f'. {failed} could not be changed'
    conn.execute('UPDATE bulk_edits SET summary = ?, item_count = ? WHERE id = ?', (summary, changed, edit_id))
    conn.commit()
    return Result(edit_id, summary, changed, failed)


# ------------------------------------------------------------------ undo

def undo(conn, user, edit_id):
    """Put an edit's items back, where they still look as the edit left them.
    Only the edit's own user. Not itself journalled: re-apply to redo."""
    edit = conn.execute('SELECT * FROM bulk_edits WHERE id = ? AND user_id = ?', (edit_id, user.id)).fetchone()
    if edit is None:
        raise BulkError('That edit was not found.')
    if edit['undone_at']:
        raise BulkError('Already undone.')
    act = _action(edit['action'])
    params = json.loads(edit['params'])

    if not conn.in_transaction:
        conn.execute('BEGIN')
    restored = left = 0
    for item in conn.execute('SELECT book_id, before, after FROM bulk_edit_items WHERE edit_id = ?',
                             (edit_id,)).fetchall():
        before = json.loads(item['before']) if item['before'] is not None else None
        after = json.loads(item['after']) if item['after'] is not None else None
        conn.execute('SAVEPOINT bulk_undo')
        try:
            # Permission now (the book may have been given away), then the
            # state now: unchanged since the edit, or someone moved it on
            ok = (can_view_book(conn, user, item['book_id'])
                  and act.current(conn, user, item['book_id'], params) == after
                  and act.restore(conn, user, item['book_id'], before, after, params))
            if not ok:
                conn.execute('ROLLBACK TO bulk_undo')
            restored += bool(ok)
            left += not ok
            conn.execute('RELEASE bulk_undo')
        except Exception:
            logger.exception('Bulk undo %s: item %s failed', edit_id, item['book_id'])
            conn.execute('ROLLBACK TO bulk_undo')
            conn.execute('RELEASE bulk_undo')
            left += 1

    # A shelf this edit created goes with it, if nothing is on it now
    if params.get('created_shelf'):
        conn.execute('DELETE FROM user_collections WHERE collection_id = ? AND user_id = ? AND NOT EXISTS '
                     '(SELECT 1 FROM collection_books WHERE collection_id = ?)',
                     (params['shelf_id'], user.id, params['shelf_id']))
    conn.execute('UPDATE bulk_edits SET undone_at = CURRENT_TIMESTAMP WHERE id = ?', (edit_id,))
    conn.commit()
    if not restored:
        # Nothing matched what the edit left: say why, not "0 restored"
        summary = f'Nothing to undo: {_count(left)} changed since, and keep the later change'
    else:
        summary = f'Undone: {restored} restored'
        if left:
            summary += f', {left} changed since and left alone'
    return Result(edit_id, summary + '.', restored, 0, left)


# ------------------------------------------------------------------ lists

def history(conn, user, limit=10):
    """The user's recent edits within the retention window, newest first."""
    return conn.execute(
        "SELECT * FROM bulk_edits WHERE user_id = ? AND created_at >= datetime('now', ?) "
        'ORDER BY created_at DESC, id DESC LIMIT ?', (user.id, f'-{KEEP_DAYS} days', limit)).fetchall()


def ago(timestamp, now=None):
    """'just now', '5 minutes ago', '3 hours ago', '2 days ago' for a
    CURRENT_TIMESTAMP value (UTC, 'YYYY-MM-DD HH:MM:SS')."""
    try:
        then = datetime.strptime(str(timestamp)[:19], '%Y-%m-%d %H:%M:%S')
    except ValueError:
        return ''
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)     # naive UTC, as SQLite stores it
    seconds = (now - then).total_seconds()
    for size, unit in ((86400, 'day'), (3600, 'hour'), (60, 'minute')):
        if seconds >= size:
            n = int(seconds // size)
            return f'{n} {unit}{"" if n == 1 else "s"} ago'
    return 'just now'


def undoable(conn, user, edit):
    """How many of an edit's items undo would put back now: the ones you can
    still see that look as the edit left them (undo's own test). Reads only."""
    if edit['undone_at']:
        return 0
    act = _action(edit['action'])
    params = json.loads(edit['params'])
    count = 0
    for item in conn.execute('SELECT book_id, after FROM bulk_edit_items WHERE edit_id = ?', (edit['id'],)):
        after = json.loads(item['after']) if item['after'] is not None else None
        if can_view_book(conn, user, item['book_id']) and act.current(conn, user, item['book_id'], params) == after:
            count += 1
    return count


def recent(conn, user, limit=10):
    """Profile -> Recent bulk edits: history() as dicts with `ago` and
    `undoable` (0: everything has changed since, so no Undo is offered)."""
    return [dict(row, ago=ago(row['created_at']), undoable=undoable(conn, user, row))
            for row in history(conn, user, limit)]


def genres(conn, user, media_type=None):
    """The user's own genres, for the picker: [{'value', 'count'}], most used
    first. Grouped by search.fold (case, accents and punctuation ignored)
    and shown with the group's most-used spelling. `media_type` is one type,
    or None for all of them. Only items the user owns (the ones they can edit)."""
    sql = "SELECT genre, COUNT(*) AS n FROM books WHERE added_by = ? AND TRIM(COALESCE(genre, '')) != ''"
    params = [user.id]
    if media_type:
        sql += ' AND media_type = ?'
        params.append(media_type)
    groups = {}
    for row in conn.execute(sql + ' GROUP BY genre', params):
        spelling = row['genre'].strip()
        groups.setdefault(search.fold(spelling), []).append((row['n'], spelling))
    out = []
    for spellings in groups.values():
        # Most used spelling; on a tie the first alphabetically (capitals sort first)
        best = min(spellings, key=lambda t: (-t[0], t[1]))[1]
        out.append({'value': best, 'count': sum(n for n, _ in spellings)})
    return sorted(out, key=lambda g: (-g['count'], g['value'].lower()))


def selection(conn, user, ids):
    """The selected items as the sheet lists them before the review: what
    each one has now (genre, format, owned, removed, and the user's own status,
    tags and shelves), so the choose step can show it. Items the user can't
    see are left out. Writes nothing."""
    out = []
    for book_id in _ids(ids):
        book = conn.execute(f'SELECT {BOOK_COLUMNS} FROM books WHERE id = ?', (book_id,)).fetchone()
        if book is None or not can_view_book(conn, user, book_id):
            continue
        kind = media.media_type_of(book)
        status = _status_row(conn, user, book_id)
        out.append({
            'id': book_id, 'title': book['title'], 'creator': book['author'],
            'cover': book['cover_image_url'], 'media_type': kind,
            'genre': book['genre'] or None,
            'format': media.format_label(book['format']) or ('Book' if kind == media.BOOK else None),
            'owned': bool(book['owned']), 'removed': bool(book['removed_at']),
            'status': _status_name(status['status']) if status else media.NO_STATUS_LABEL[kind],
            'tags': [r['tag_name'] for r in conn.execute(
                'SELECT tag_name FROM book_tags WHERE user_id = ? AND book_id = ? ORDER BY tag_name',
                (user.id, book_id))],
            'shelves': [r['name'] for r in conn.execute(
                'SELECT uc.name FROM collection_books cb JOIN user_collections uc '
                'ON uc.collection_id = cb.collection_id WHERE uc.user_id = ? AND cb.book_id = ? '
                'ORDER BY uc.name COLLATE NOCASE', (user.id, book_id))],
            'yours': bool(user.is_admin or book['added_by'] == user.id),
        })
    return out


def options(conn, user, media_type):
    """What the sheet's pickers offer for one type: its statuses (plus "no
    status", worded for the type), formats, your shelves for the section, and
    your tags with counts."""
    kind = media_type if media_type in media.MEDIA_TYPES else media.BOOK
    return {
        'statuses': [{'value': s, 'label': media.STATUS_LABELS[s]} for s in media.STATUSES[kind]]
                    + [{'value': 'untracked', 'label': media.NO_STATUS_LABEL[kind]}],
        'formats': [{'value': f, 'label': media.format_label(f)} for f in media.FORMATS[kind]],
        'shelves': [{'id': r['collection_id'], 'name': r['name'], 'count': r['n']} for r in conn.execute(
            'SELECT uc.collection_id, uc.name, COUNT(cb.book_id) AS n FROM user_collections uc '
            'LEFT JOIN collection_books cb ON cb.collection_id = uc.collection_id '
            'WHERE uc.user_id = ? AND uc.media_type = ? GROUP BY uc.collection_id '
            'ORDER BY uc.name COLLATE NOCASE', (user.id, kind))],
        'tags': [{'value': r['tag_name'], 'count': r['n']} for r in conn.execute(
            'SELECT tag_name, COUNT(*) AS n FROM book_tags WHERE user_id = ? '
            'GROUP BY tag_name ORDER BY n DESC, tag_name', (user.id,))],
        'section': SECTION_NAMES[kind], 'media_type': kind,
    }
