"""Merge two records into one (ROADMAP 16.0f part B, docs/PROGRESS-MERGE-SPEC.md).

Two `books` rows for one work, one of them holding the history: a record
from before ownership with Phil's reviews beside his later owned copy, or
an Audiobookshelf listen imported as its own Audiobook beside the paper
copy. Everything that hangs on the **folded** record moves onto the
**kept** one, and the folded record is deleted.

  may_merge(conn, user, keep, fold)        None, or why not (a sentence)
  plan(conn, keep_id, fold_id)             what would happen; reads only
  apply(conn, user, keep_id, fold_id, choices, fills)   do it, journalled
  suggestions(conn, user)                  likely pairs (step 6)

No Flask; callers commit (apply commits itself, since it journals).
A refusal is MergeError, whose message is safe to show.

How each table moves is MOVERS below; a test fails if a table with a
foreign key to `books` isn't in it, so a new table can't be forgotten.
Where both records hold something that exists once per user (a review,
a status, a wishlist entry) or once per kind (a front photo, a face),
that's a **clash**: the person merging always picks (Phil, 2026-11-20).

Undo goes through the bulk journal (`bulk_edits.action = 'merge'`): the
journal holds the folded book's row, every moved row's old book id, every
changed value and every deleted row, and `_restore` puts them back,
re-inserting the folded book under its old id (`books.id` is
AUTOINCREMENT, so an id is never reused). Files are never deleted here,
so an undo finds the folded record's cover and photos where they were.
"""
import json

from models import other_users_with_book_data
from utils import media


class MergeError(ValueError):
    """A merge that can't go ahead; the message is safe to show."""


# Book fields the kept record takes from the folded one where its own is
# blank (each ticked in the preview by default). Ownership, format, value,
# condition and removal stay the kept record's: it's normally the copy on
# the shelf.
FILLABLE = ('subtitle', 'publisher', 'publish_year', 'isbn', 'page_count', 'description', 'genre',
            'narrator', 'runtime_minutes', 'barcode', 'catalog_number', 'cover_image_url')

FIELD_LABELS = {'subtitle': 'Subtitle', 'publisher': 'Publisher', 'publish_year': 'Year', 'isbn': 'ISBN',
                'page_count': 'Page count', 'description': 'Description', 'genre': 'Genre',
                'narrator': 'Narrator', 'runtime_minutes': 'Length', 'barcode': 'Barcode',
                'catalog_number': 'Catalogue number', 'cover_image_url': 'Cover'}

# Every table with a foreign key to books: (column, how it moves, key).
#   move    the rows take the kept record's id
#   dedupe  move, but a row whose key already exists on the kept record is
#           dropped (a tag both records had)
#   drop    deleted (journalled): older bulk edits' rows for the folded record
#   clash   per-user or per-kind rules in apply(); the key says per what
MOVERS = {
    'reading_sessions':     ('book_id', 'move', None),
    'loans':                ('book_id', 'move', None),
    'goodreads_rows':       ('book_id', 'move', None),
    'abs_links':            ('book_id', 'move', None),
    'notifications':        ('related_book_id', 'move', None),
    'book_tags':            ('book_id', 'dedupe', ('user_id', 'tag_name')),
    'collection_books':     ('book_id', 'dedupe', ('collection_id',)),
    'activity_likes':       ('book_id', 'dedupe', ('activity_type', 'activity_user_id', 'liker_user_id')),
    'dismissed_activities': ('book_id', 'dedupe', ('activity_type', 'user_id')),
    'bulk_edit_items':      ('book_id', 'drop', None),
    'read_data':            ('book_id', 'clash', ('user_id',)),
    'collections':          ('book_id', 'clash', ('user_id',)),
    'wishlist':             ('book_id', 'clash', ('user_id',)),
    'item_photos':          ('book_id', 'clash', ('kind',)),
    'item_faces':           ('book_id', 'clash', ('kind',)),
}

# (one, many) for the preview's counts
TABLE_LABELS = {'reading_sessions': ('reading session', 'reading sessions'), 'loans': ('loan', 'loans'),
                'goodreads_rows': ('Goodreads import line', 'Goodreads import lines'),
                'abs_links': ('Audiobookshelf link', 'Audiobookshelf links'),
                'notifications': ('notification', 'notifications'), 'book_tags': ('tag', 'tags'),
                'collection_books': ('collection entry', 'collection entries'), 'activity_likes': ('like', 'likes'),
                'dismissed_activities': ('dismissed feed entry', 'dismissed feed entries'),
                'bulk_edit_items': ('entry in an older bulk edit (that edit can no longer undo this record)',
                                    'entries in older bulk edits (those edits can no longer undo this record)'),
                'read_data': ('review or rating', 'reviews or ratings'), 'collections': ('status', 'statuses'),
                'wishlist': ('wishlist entry', 'wishlist entries'), 'item_photos': ('photo', 'photos'),
                'item_faces': ('face', 'faces')}


def _words(table, n, suffix=''):
    one, many = TABLE_LABELS[table]
    return f'{one if n == 1 else many}{suffix}'

ACTION_KEY = 'merge'
STATUS_WORDS = {'read': 'Read', 'currently reading': 'Currently Reading', 'want to read': 'Want to Read',
                'did not finish': 'Did Not Finish', 'watched': 'Watched', 'want to watch': 'Want to Watch',
                'listened': 'Listened', 'want to listen': 'Want to Listen'}


# ------------------------------------------------------------------ who may

def _book(conn, book_id):
    return conn.execute('SELECT * FROM books WHERE id = ?', (book_id,)).fetchone()


def may_merge(conn, user, keep, fold):
    """None if `user` may fold `fold` into `keep` (both books rows), else a
    sentence saying why not. Admins: any two records of one type. Anyone
    else: both records theirs or unowned, and nobody else has data on the
    folded one (the rule hard delete already uses)."""
    if keep is None or fold is None:
        return 'That record was not found.'
    if keep['id'] == fold['id']:
        return 'Pick two different records.'
    if media.media_type_of(keep) != media.media_type_of(fold):
        return 'Only two records of the same kind can be merged (two books, two movies, two albums).'
    if user.is_admin:
        return None
    if keep['added_by'] not in (user.id, None) or fold['added_by'] not in (user.id, None):
        return 'You can only merge records that are yours or have no owner.'
    if other_users_with_book_data(conn, fold['id'], user.id):
        return 'Someone else has data on this record; ask an admin to merge it.'
    return None


# ------------------------------------------------------------------ the plan

def _rows(conn, table, book_id):
    column = MOVERS[table][0]
    return [dict(r) for r in conn.execute(
        f'SELECT rowid AS _rowid, * FROM {table} WHERE {column} = ? ORDER BY rowid', (book_id,))]


def _usernames(conn, ids):
    ids = [i for i in ids if i is not None]
    if not ids:
        return {}
    marks = ','.join('?' * len(ids))
    return {r['id']: r['username'] for r in conn.execute(
        f'SELECT id, username FROM users WHERE id IN ({marks})', ids)}


def _by(rows, key):
    out = {}
    for r in rows:
        out.setdefault(r[key], []).append(r)
    return out


def _clashes(conn, keep_id, fold_id):
    """The choices the person merging must make: [{'id', 'table', 'what',
    'who', 'keep', 'fold', 'join'}], values as words to show."""
    out = []
    # Reviews and ratings: per user, per field, only where both have one and they differ
    keep_rd, fold_rd = _by(_rows(conn, 'read_data', keep_id), 'user_id'), _by(_rows(conn, 'read_data', fold_id), 'user_id')
    for uid in sorted(set(keep_rd) & set(fold_rd)):
        k, f = keep_rd[uid][0], fold_rd[uid][0]
        for field, what in (('rating', 'Rating'), ('comment', 'Review')):
            if k[field] is not None and f[field] is not None and k[field] != f[field]:
                out.append({'id': f'read_data:{uid}:{field}', 'table': 'read_data', 'what': what, 'user_id': uid,
                            'keep': k[field], 'fold': f[field], 'join': False})
    # Statuses: per user, where they differ
    keep_c, fold_c = _by(_rows(conn, 'collections', keep_id), 'user_id'), _by(_rows(conn, 'collections', fold_id), 'user_id')
    for uid in sorted(set(keep_c) & set(fold_c)):
        k, f = keep_c[uid][0]['status'], fold_c[uid][0]['status']
        if k != f:
            out.append({'id': f'collections:{uid}', 'table': 'collections', 'what': 'Status', 'user_id': uid,
                        'keep': STATUS_WORDS.get(k, k), 'fold': STATUS_WORDS.get(f, f), 'join': False})
    # Wishlist: per user, where both have notes and they differ (else the kept entry takes the blanks)
    keep_w, fold_w = _by(_rows(conn, 'wishlist', keep_id), 'user_id'), _by(_rows(conn, 'wishlist', fold_id), 'user_id')
    for uid in sorted(set(keep_w) & set(fold_w)):
        k, f = keep_w[uid][0], fold_w[uid][0]
        if (k['notes'] or '').strip() and (f['notes'] or '').strip() and k['notes'] != f['notes']:
            out.append({'id': f'wishlist:{uid}', 'table': 'wishlist', 'what': 'Wishlist note', 'user_id': uid,
                        'keep': k['notes'], 'fold': f['notes'], 'join': True})
    # Photos (one of each kind but gallery) and faces: per kind
    for table, what in (('item_photos', 'photo'), ('item_faces', 'face')):
        keep_k = _by([r for r in _rows(conn, table, keep_id) if r['kind'] != 'gallery'], 'kind')
        fold_k = _by([r for r in _rows(conn, table, fold_id) if r['kind'] != 'gallery'], 'kind')
        for kind in sorted(set(keep_k) & set(fold_k)):
            out.append({'id': f'{table}:{kind}', 'table': table, 'what': f'{kind.capitalize()} {what}',
                        'user_id': None, 'keep': keep_k[kind][0].get('path') or kind,
                        'fold': fold_k[kind][0].get('path') or kind, 'join': False})
    names = _usernames(conn, {c['user_id'] for c in out})
    for c in out:
        c['who'] = names.get(c['user_id'], '')
    return out


def plan(conn, keep_id, fold_id):
    """What merging `fold_id` into `keep_id` would do, for the preview:
    {'keep', 'fold' (rows as dicts), 'fills' [{'field', 'label', 'value'}],
    'counts' [(words, n)], 'drops' [(words, n)], 'clashes', 'people'
    (usernames with data on the folded record)}. Reads only."""
    keep, fold = _book(conn, keep_id), _book(conn, fold_id)
    if keep is None or fold is None:
        raise MergeError('That record was not found.')
    fills = [{'field': f, 'label': FIELD_LABELS[f], 'value': fold[f]} for f in FILLABLE
             if _blank(keep[f]) and not _blank(fold[f])]
    counts, drops = [], []
    for table, (_col, how, key) in MOVERS.items():
        rows = _rows(conn, table, fold_id)
        if not rows:
            continue
        if how == 'drop':
            drops.append((_words(table, len(rows)), len(rows)))
            continue
        if how == 'dedupe':
            kept = {tuple(r[k] for k in key) for r in _rows(conn, table, keep_id)}
            dupes = sum(1 for r in rows if tuple(r[k] for k in key) in kept)
            if dupes:
                drops.append((_words(table, dupes, ' both records had'), dupes))
            if len(rows) - dupes:
                counts.append((_words(table, len(rows) - dupes), len(rows) - dupes))
            continue
        counts.append((_words(table, len(rows)), len(rows)))
    people_ids = {r['user_id'] for t in ('read_data', 'collections', 'reading_sessions', 'wishlist', 'book_tags')
                  for r in _rows(conn, t, fold_id)}
    return {'keep': dict(keep), 'fold': dict(fold), 'fills': fills, 'counts': counts, 'drops': drops,
            'clashes': _clashes(conn, keep_id, fold_id),
            'people': sorted(_usernames(conn, people_ids).values(), key=str.lower)}


def _blank(value):
    return value is None or (isinstance(value, str) and not value.strip()) or value == 0


# ------------------------------------------------------------------ apply

class _Journal:
    """What apply did, in the order it did it, for _restore."""

    def __init__(self, book):
        self.data = {'book': book, 'moved': [], 'updated': [], 'deleted': []}

    def move(self, conn, table, row, new_id):
        column = MOVERS[table][0]
        conn.execute(f'UPDATE {table} SET {column} = ? WHERE rowid = ?', (new_id, row['_rowid']))
        self.data['moved'].append([table, row['_rowid'], column, row[column]])

    def update(self, conn, table, rowid, values, old):
        sets = ', '.join(f'{k} = ?' for k in values)
        conn.execute(f'UPDATE {table} SET {sets} WHERE rowid = ?', (*values.values(), rowid))
        self.data['updated'].append([table, rowid, {k: old[k] for k in values}])

    def delete(self, conn, table, row):
        conn.execute(f'DELETE FROM {table} WHERE rowid = ?', (row['_rowid'],))
        self.data['deleted'].append([table, {k: v for k, v in row.items() if k != '_rowid'}])


def apply(conn, user, keep_id, fold_id, choices, fills):
    """Fold `fold_id` into `keep_id`. `choices` is {clash id: 'keep' |
    'fold' | 'join'} for every clash in the plan; `fills` the FILLABLE
    fields to take from the folded record. One transaction, checked with
    foreign_key_check, journalled for undo; commits. Returns the bulk edit
    id. Raises MergeError (nothing written). The caller checks may_merge
    and takes the backup first."""
    keep, fold = _book(conn, keep_id), _book(conn, fold_id)
    reason = may_merge(conn, user, keep, fold)
    if reason:
        raise MergeError(reason)
    clashes = {c['id']: c for c in _clashes(conn, keep_id, fold_id)}
    for cid, clash in clashes.items():
        if choices.get(cid) not in (('keep', 'fold', 'join') if clash['join'] else ('keep', 'fold')):
            raise MergeError('Choose which to keep for every item both records have.')
    fills = [f for f in fills if f in FILLABLE]

    if not conn.in_transaction:
        conn.execute('BEGIN')
    try:
        j = _Journal({k: fold[k] for k in fold.keys()})
        _apply(conn, j, keep, fold, choices, fills)
        # Nothing may still point at the folded record, or the delete would
        # cascade into it (or set it NULL): MOVERS covers every table
        for table, (column, _how, _key) in MOVERS.items():
            if conn.execute(f'SELECT 1 FROM {table} WHERE {column} = ? LIMIT 1', (fold_id,)).fetchone():
                raise MergeError('Something still points at the folded record; nothing was changed.')
        conn.execute('DELETE FROM books WHERE id = ?', (fold_id,))
        if conn.execute('PRAGMA foreign_key_check').fetchall():
            raise MergeError('The merge would leave broken links; nothing was changed.')
        edit_id = _journal(conn, user, keep, fold, j)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return edit_id


def _apply(conn, j, keep, fold, choices, fills):
    keep_id, fold_id = keep['id'], fold['id']
    if fills:
        j.update(conn, 'books', keep_id, {f: fold[f] for f in fills}, keep)

    for table, (_column, how, key) in MOVERS.items():
        if how == 'move':
            for row in _rows(conn, table, fold_id):
                j.move(conn, table, row, keep_id)
        elif how == 'drop':
            for row in _rows(conn, table, fold_id):
                j.delete(conn, table, row)
        elif how == 'dedupe':
            kept = {tuple(r[k] for k in key) for r in _rows(conn, table, keep_id)}
            for row in _rows(conn, table, fold_id):
                if tuple(row[k] for k in key) in kept:
                    j.delete(conn, table, row)
                else:
                    j.move(conn, table, row, keep_id)

    _merge_read_data(conn, j, keep_id, fold_id, choices)
    _merge_one_each(conn, j, 'collections', keep_id, fold_id, choices, same=lambda k, f: k['status'] == f['status'])
    _merge_wishlist(conn, j, keep_id, fold_id, choices)
    _merge_kinds(conn, j, 'item_photos', keep_id, fold_id, choices, loser_to_gallery=True)
    _merge_kinds(conn, j, 'item_faces', keep_id, fold_id, choices, loser_to_gallery=False)


def _merge_read_data(conn, j, keep_id, fold_id, choices):
    keep_rd = _by(_rows(conn, 'read_data', keep_id), 'user_id')
    for row in _rows(conn, 'read_data', fold_id):
        uid = row['user_id']
        if uid not in keep_rd:
            j.move(conn, 'read_data', row, keep_id)
            continue
        k = keep_rd[uid][0]
        values = {}
        for field in ('rating', 'comment'):
            if row[field] is None or row[field] == k[field]:
                continue
            if k[field] is None or choices.get(f'read_data:{uid}:{field}') == 'fold':
                values[field] = row[field]
        if values:
            j.update(conn, 'read_data', k['_rowid'], values, k)
        j.delete(conn, 'read_data', row)


def _merge_one_each(conn, j, table, keep_id, fold_id, choices, same):
    """One row per user (a status): the folded row moves if the kept record
    has none; if both and they're the same, the folded one goes; else the
    choice says which survives."""
    keep_rows = _by(_rows(conn, table, keep_id), 'user_id')
    for row in _rows(conn, table, fold_id):
        uid = row['user_id']
        if uid not in keep_rows:
            j.move(conn, table, row, keep_id)
        elif same(keep_rows[uid][0], row) or choices.get(f'{table}:{uid}') != 'fold':
            j.delete(conn, table, row)
        else:
            for k in keep_rows[uid]:
                j.delete(conn, table, k)
            j.move(conn, table, row, keep_id)


def _merge_wishlist(conn, j, keep_id, fold_id, choices):
    keep_w = _by(_rows(conn, 'wishlist', keep_id), 'user_id')
    for row in _rows(conn, 'wishlist', fold_id):
        uid = row['user_id']
        if uid not in keep_w:
            j.move(conn, 'wishlist', row, keep_id)
            continue
        k = keep_w[uid][0]
        choice = choices.get(f'wishlist:{uid}')
        if choice == 'fold':
            j.delete(conn, 'wishlist', k)
            j.move(conn, 'wishlist', row, keep_id)
            continue
        values = {}
        if choice == 'join':
            values['notes'] = f"{k['notes'].rstrip()}\n\n{row['notes'].strip()}"
        elif choice is None and not (k['notes'] or '').strip() and (row['notes'] or '').strip():
            values['notes'] = row['notes']            # no clash: the kept entry takes the blank
        if not k['purchase_link'] and row['purchase_link']:
            values['purchase_link'] = row['purchase_link']
        if values:
            j.update(conn, 'wishlist', k['_rowid'], values, k)
        j.delete(conn, 'wishlist', row)


def _merge_kinds(conn, j, table, keep_id, fold_id, choices, loser_to_gallery):
    """One per kind (a front photo, a spine face). Gallery photos just
    move. The losing photo of a clash joins the gallery; a losing face goes.
    A kind is changed before the row moves, so the one-per-kind index never
    sees two at once."""
    keep_k = _by([r for r in _rows(conn, table, keep_id) if r['kind'] != 'gallery'], 'kind')
    for row in _rows(conn, table, fold_id):
        kind = row['kind']
        if kind == 'gallery' or kind not in keep_k:
            j.move(conn, table, row, keep_id)
        elif choices.get(f'{table}:{kind}') == 'fold':
            for k in keep_k[kind]:
                if loser_to_gallery:
                    j.update(conn, table, k['_rowid'], {'kind': 'gallery'}, k)
                else:
                    j.delete(conn, table, k)
            j.move(conn, table, row, keep_id)
        elif loser_to_gallery:
            j.update(conn, table, row['_rowid'], {'kind': 'gallery'}, row)
            j.move(conn, table, row, keep_id)
        else:
            j.delete(conn, table, row)


def _journal(conn, user, keep, fold, j):
    """The bulk_edits row undo works from, and one item on the kept record."""
    j.data.update(keep=keep['id'], fold=fold['id'], title=fold['title'])
    summary = f"Merged {fold['title']} (#{fold['id']}) into {keep['title']} (#{keep['id']})"
    cur = conn.execute('INSERT INTO bulk_edits (user_id, action, params, summary, item_count) VALUES (?, ?, ?, ?, 1)',
                       (user.id, ACTION_KEY, json.dumps(j.data), summary))
    conn.execute('INSERT INTO bulk_edit_items (edit_id, book_id, before, after) VALUES (?, ?, ?, ?)',
                 (cur.lastrowid, keep['id'], json.dumps({'merged': None}), json.dumps({'merged': fold['id']})))
    return cur.lastrowid


# ------------------------------------------------------------------ undo (bulk.undo)

def _current(conn, user, book_id, params):
    """As the merge left it: the kept record there, the folded one gone."""
    gone = conn.execute('SELECT 1 FROM books WHERE id = ?', (params['fold'],)).fetchone() is None
    return {'merged': params['fold']} if gone else {'merged': None}


def _safe(table, columns):
    """Only tables and columns this module writes (the journal is ours, but
    names go into SQL text, so check anyway)."""
    if table != 'books' and table not in MOVERS:
        raise MergeError('That merge record is damaged.')
    for c in columns:
        if not c.replace('_', '').isalnum():
            raise MergeError('That merge record is damaged.')


def _insert(conn, table, row):
    _safe(table, row)
    cols = list(row)
    conn.execute(f'INSERT INTO {table} ({", ".join(cols)}) VALUES ({", ".join("?" * len(cols))})',
                 [row[c] for c in cols])


def _restore(conn, user, book_id, before, after, params):
    """Put a merge back: the folded book under its old id, then every moved
    row back onto it, every changed value back, every deleted row back.
    False (nothing done) if the folded id is somehow in use."""
    if conn.execute('SELECT 1 FROM books WHERE id = ?', (params['fold'],)).fetchone():
        return False
    _insert(conn, 'books', params['book'])
    for table, rowid, column, old in reversed(params['moved']):
        _safe(table, [column])
        conn.execute(f'UPDATE {table} SET {column} = ? WHERE rowid = ?', (old, rowid))
    for table, rowid, olds in reversed(params['updated']):
        _safe(table, olds)
        sets = ', '.join(f'{k} = ?' for k in olds)
        conn.execute(f'UPDATE {table} SET {sets} WHERE rowid = ?', (*olds.values(), rowid))
    for table, row in params['deleted']:
        _insert(conn, table, row)
    return True


def _not_a_bulk_edit(*_args, **_kwargs):
    raise MergeError('A merge is made on its own page, not as a bulk edit.')


def make_action():
    """bulk.Action for undo, as the importers do (bulk._action)."""
    from utils.bulk import Action
    return Action(
        params=_not_a_bulk_edit, plan=_not_a_bulk_edit, write=_not_a_bulk_edit,
        current=_current, restore=_restore,
        describe=lambda p: 'Merge', summary=lambda p, n: f"Merged {p.get('title', 'a record')}",
        key=lambda b: None, label=lambda k, p: '', same_text=lambda p: '',
        after_undo=None)


# ------------------------------------------------------------------ the page's lists

def candidates(conn, user, keep, query, limit=20):
    """Records `user` might fold into `keep`, matching `query` in the title
    or author: the same type, not `keep`. An admin sees every record; anyone
    else their own and the unowned ones they have data on (what Show:
    Everything lists for them), so the search never reveals a record they
    can't open. may_merge still decides on the preview."""
    query = (query or '').strip()
    if not query:
        return []
    like = f'%{query}%'
    sql = ('SELECT b.*, u.username AS owner FROM books b LEFT JOIN users u ON u.id = b.added_by '
           'WHERE b.media_type = ? AND b.id != ? AND (b.title LIKE ? OR b.author LIKE ?)')
    params = [media.media_type_of(keep), keep['id'], like, like]
    if not user.is_admin:
        sql += ''' AND (b.added_by = ? OR (b.added_by IS NULL AND b.id IN (
                     SELECT book_id FROM read_data WHERE user_id = ?
                     UNION SELECT book_id FROM collections WHERE user_id = ?
                     UNION SELECT book_id FROM reading_sessions WHERE user_id = ?
                     UNION SELECT book_id FROM wishlist WHERE user_id = ?)))'''
        params += [user.id] * 5
    sql += ' ORDER BY LOWER(b.title), b.id LIMIT ?'
    return conn.execute(sql, [*params, limit]).fetchall()


def recent(conn, user, limit=10):
    """Your merges, newest first, for undo."""
    return conn.execute("SELECT * FROM bulk_edits WHERE user_id = ? AND action = ? ORDER BY id DESC LIMIT ?",
                        (user.id, ACTION_KEY, limit)).fetchall()
