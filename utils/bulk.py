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
from ACTIONS, never from the request. Step 3 has one action, `genre`.
"""
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field

from models import can_view_book
from utils import search

logger = logging.getLogger(__name__)

MAX_ITEMS = 500           # per operation: a bounded edit is a bounded mistake
KEEP_DAYS = 30            # how long the journal can undo
MAX_GENRE = 80

# Skip reasons, worded for the review sheet
NOT_FOUND = 'Not found'
NOT_YOURS = 'Not yours'


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
    before: dict = None           # snapshot of what the action touches, now
    after: dict = None            # ...and what it would be


@dataclass
class Group:
    """Changes that share a before value, so 44 changes read as three lines."""
    before: object
    after: object
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
    skipped: dict                 # reason -> [ids]
    notes: list
    fingerprint: str

    @property
    def changes(self):
        return sum(g.count for g in self.groups)


@dataclass
class Result:
    edit_id: int                  # None when nothing was written
    summary: str
    changed: int = 0
    failed: int = 0
    skipped: int = 0              # undo: items changed since, left alone


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


def _genre_params(params):
    """{'genre': text} sets it, {'genre': None} clears it ("(no genre)")."""
    if not isinstance(params, dict) or 'genre' not in params:
        raise BulkError('Pick a genre first.')
    return {'genre': None if params['genre'] is None else clean_genre(params['genre'])}


def _genre_plan(row, params, user):
    before = {'genre': row['genre']}
    after = {'genre': params['genre']}
    # "" and NULL both mean no genre
    if (row['genre'] or None) == params['genre']:
        return 'same', '', before, after
    return 'change', '', before, after


def _genre_write(conn, user, book_id, before, after):
    """True if the row was written. The WHERE repeats the permission and the
    value the plan saw, so a change in between is skipped, not overwritten."""
    cur = conn.execute('UPDATE books SET genre = ? WHERE id = ? AND genre IS ? AND (added_by = ? OR ? = 1)',
                       (after['genre'], book_id, before['genre'], user.id, int(user.is_admin)))
    return cur.rowcount == 1


def _genre_current(conn, book_id):
    row = conn.execute('SELECT genre FROM books WHERE id = ?', (book_id,)).fetchone()
    return None if row is None else {'genre': row['genre']}


def _genre_restore(conn, user, book_id, before):
    cur = conn.execute('UPDATE books SET genre = ? WHERE id = ? AND (added_by = ? OR ? = 1)',
                       (before['genre'], book_id, user.id, int(user.is_admin)))
    return cur.rowcount == 1


def _genre_summary(params, count):
    what = f'Genre set to {params["genre"]}' if params['genre'] else 'Genre cleared'
    return f'{what} on {count} item{"" if count == 1 else "s"}'


@dataclass(frozen=True)
class Action:
    """One whitelist entry. Item edits (the `books` row) need owner or admin."""
    params: callable       # validate and normalise the request's params
    plan: callable         # (row, params, user) -> (outcome, reason, before, after)
    write: callable        # (conn, user, book_id, before, after) -> bool
    current: callable      # (conn, book_id) -> snapshot now, for undo's check
    restore: callable      # (conn, user, book_id, before) -> bool
    summary: callable      # (params, count) -> text
    owner_only: bool = True


ACTIONS = {
    'genre': Action(_genre_params, _genre_plan, _genre_write, _genre_current, _genre_restore, _genre_summary),
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


def plan(conn, user, action, params, ids):
    """What `action` with `params` would do to `ids` for `user`. Writes nothing."""
    act = _action(action)
    params = act.params(params)
    ids = _ids(ids)
    if not ids:
        raise BulkError('Select something first.')

    rows = []
    for book_id in ids:
        book = conn.execute('SELECT id, title, author, cover_image_url, media_type, genre, added_by '
                            'FROM books WHERE id = ?', (book_id,)).fetchone()
        if book is None or not can_view_book(conn, user, book_id):
            rows.append(PlanRow(book_id, 'skip', NOT_FOUND))
            continue
        shown = dict(title=book['title'], creator=book['author'], cover=book['cover_image_url'],
                     media_type=book['media_type'])
        if act.owner_only and not (user.is_admin or book['added_by'] == user.id):
            rows.append(PlanRow(book_id, 'skip', NOT_YOURS, **shown))
            continue
        outcome, reason, before, after = act.plan(book, params, user)
        rows.append(PlanRow(book_id, outcome, reason, before=before, after=after, **shown))

    # Groups by before value, largest first, "no value" last
    by_before = {}
    for row in rows:
        if row.outcome == 'change':
            # genre's snapshot has one value; step 5's actions will say how they group
            key = next(iter(row.before.values())) or None
            by_before.setdefault(key, Group(key, next(iter(row.after.values())))).ids.append(row.id)
    groups = sorted(by_before.values(), key=lambda g: (g.before is None, -g.count))

    skipped = {}
    for row in rows:
        if row.outcome == 'skip':
            skipped.setdefault(row.reason, []).append(row.id)

    digest = hashlib.sha256(json.dumps(
        [action, params, sorted((r.id, r.before, r.after, r.outcome) for r in rows)],
        sort_keys=True, default=str).encode()).hexdigest()
    return Plan(action, params, rows, groups, sum(r.outcome == 'same' for r in rows), skipped, [], digest)


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
    edit_id = conn.execute(
        'INSERT INTO bulk_edits (user_id, action, params, summary, item_count) VALUES (?, ?, ?, ?, 0)',
        (user.id, action, json.dumps(current.params, sort_keys=True), '')).lastrowid

    changed = failed = 0
    for row in chosen:
        conn.execute('SAVEPOINT bulk_item')
        try:
            # The journal row goes in the same savepoint as the change, so
            # the journal can't disagree with the data
            if act.write(conn, user, row.id, row.before, row.after):
                conn.execute('INSERT INTO bulk_edit_items (edit_id, book_id, before, after) VALUES (?, ?, ?, ?)',
                             (edit_id, row.id, _snap(row.before), _snap(row.after)))
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
        conn.commit()
        return Result(None, 'Nothing was changed.', 0, failed)
    summary = act.summary(current.params, changed)
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

    if not conn.in_transaction:
        conn.execute('BEGIN')
    restored = left = 0
    for item in conn.execute('SELECT book_id, before, after FROM bulk_edit_items WHERE edit_id = ?',
                             (edit_id,)).fetchall():
        before, after = json.loads(item['before']), json.loads(item['after'])
        conn.execute('SAVEPOINT bulk_undo')
        try:
            # Permission now (the book may have been given away), then the
            # state now: unchanged since the edit, or someone moved it on
            ok = (can_view_book(conn, user, item['book_id'])
                  and act.current(conn, item['book_id']) == after
                  and act.restore(conn, user, item['book_id'], before))
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

    conn.execute('UPDATE bulk_edits SET undone_at = CURRENT_TIMESTAMP WHERE id = ?', (edit_id,))
    conn.commit()
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
        out.append({'value': max(spellings)[1], 'count': sum(n for n, _ in spellings)})
    return sorted(out, key=lambda g: (-g['count'], g['value'].lower()))
