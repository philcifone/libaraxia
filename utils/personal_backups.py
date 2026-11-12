"""Personal library backups: each user backs up and restores their own data.

Unlike the site backups (utils/backups.py, admins only, everyone at once),
a personal backup holds only one user's rows, and restoring it changes only
those rows. Other people's data is never touched.

What "your library" is:

    books                 the ones you added (books.added_by = you), wishlist
                          entries included
    collections, read_data, reading_sessions, wishlist, book_tags,
    reading_goals, dismissed_activities, user_collections, bulk_edits,
    goodreads_imports     your rows (user_id = you), on any book
    collection_books, bulk_edit_items, goodreads_rows
                          the children of your rows above

Left out on purpose: your account (password, email, avatar), friendships,
households, notifications and likes. They involve other people, or would
let a restore undo a password change.

A backup is a folder BACKUP_DIR/users/<user id>/<name>/ with library.json
(the rows, column names first) and uploads/ (hard links to your books'
cover files, as in the site backups).

Restore, in one transaction:
  1. Your rows in the tables above are deleted.
  2. Books you added after the backup are deleted, unless someone else has
     data on them (models.other_users_with_book_data); those are kept.
  3. Each book in the backup: still yours, it's put back as it was; gone,
     it's inserted again with its old id (books ids are AUTOINCREMENT, so
     an old id is never anyone else's); given to someone since, it's left
     with them.
  4. Your rows from the backup go back in with their old ids (every table
     here is AUTOINCREMENT or keyed by user and book, and rows never change
     user, so an old id can't belong to anyone else). A row on a book that
     no longer exists (a household book its owner deleted) is skipped and
     counted.
Before that, the current state is backed up (kind "before_restore"), so a
restore can be undone. After it, missing cover files are linked back and
the covers of books deleted in step 2 are deleted if nothing uses them.

A backup made before a migration still restores: only the columns both
sides have are copied. If the database has gained a required column the
backup doesn't have, the restore is refused.
"""
import json
import os
import shutil
from datetime import datetime

from utils import backups as site
# image_utils.STATIC_ROOT is read at call time (tests point it elsewhere)
from utils import image_utils

KINDS = {
    'manual':         'Backed up by hand',
    'goodreads':      'Before a Goodreads import',
    'before_restore': 'Before a restore',
}
MAX_MANUAL = 10        # per user; the oldest must be deleted to make another
KEEP_AUTOMATIC = 5     # per user, newest kept
DATA_FILE = 'library.json'
FORMAT = 1

# Tables with a user_id column, in the order they are put back (parents
# before children). Children of these are handled with them.
USER_TABLES = ['user_collections', 'bulk_edits', 'goodreads_imports',
               'collections', 'read_data', 'reading_sessions', 'wishlist',
               'book_tags', 'reading_goals', 'dismissed_activities']
CHILDREN = {
    'collection_books': ('collection_id', 'user_collections', 'collection_id'),
    'bulk_edit_items':  ('edit_id', 'bulk_edits', 'id'),
    'goodreads_rows':   ('import_id', 'goodreads_imports', 'id'),
}
# Child rows go in right after their parent table
AFTER = {'user_collections': 'collection_books', 'bulk_edits': 'bulk_edit_items',
         'goodreads_imports': 'goodreads_rows'}
# Columns that point at a book: a row whose book is gone can't come back,
# except where the key is SET NULL (goodreads_rows keeps its line)
BOOK_NULLABLE = {'goodreads_rows'}


class PersonalBackupError(Exception):
    """Something to tell the user, in words fit to show them."""


def user_dir(user_id):
    return os.path.join(site.backup_dir(), 'users', str(int(user_id)))


def folder(user_id, name):
    if not isinstance(name, str) or not site.NAME_RE.match(name):
        raise PersonalBackupError('No such backup.')
    path = os.path.join(user_dir(user_id), name)
    if not os.path.isfile(os.path.join(path, DATA_FILE)):
        raise PersonalBackupError('No such backup.')
    return path


# --- reading ---------------------------------------------------------------

def _columns(conn, table):
    return [r[1] for r in conn.execute(f'PRAGMA table_info({table})')]


def _rows(conn, table, where, params):
    cols = _columns(conn, table)
    rows = conn.execute(f'SELECT {", ".join(cols)} FROM {table} WHERE {where}', params).fetchall()
    return {'columns': cols, 'rows': [list(r) for r in rows]}


def snapshot(conn, user_id):
    """Every row of the user's library, as {table: {columns, rows}}."""
    u = (user_id,)
    tables = {'books': _rows(conn, 'books', 'added_by = ?', u)}
    for t in USER_TABLES:
        tables[t] = _rows(conn, t, 'user_id = ?', u)
    for child, (key, parent, parent_key) in CHILDREN.items():
        tables[child] = _rows(conn, child,
                              f'{key} IN (SELECT {parent_key} FROM {parent} WHERE user_id = ?)', u)
    return tables


def _cover_paths(tables):
    books = tables['books']
    i = books['columns'].index('cover_image_url')
    return {r[i] for r in books['rows'] if r[i] and image_utils.is_safe_upload_path(r[i])}


def _counts(tables):
    return {
        'books': len(tables['books']['rows']),
        'statuses': len(tables['collections']['rows']),
        'reviews': len(tables['read_data']['rows']),
        'sessions': len(tables['reading_sessions']['rows']),
        'wishlist': len(tables['wishlist']['rows']),
    }


# --- making and listing ----------------------------------------------------

def create(conn, user_id, username, kind='manual', prune=True):
    """Back up one user's library. Returns its info. Raises
    PersonalBackupError (the manual limit, or a failure)."""
    if kind not in KINDS:
        raise ValueError(kind)
    if kind == 'manual' and sum(b['kind'] == 'manual' for b in list_backups(user_id)) >= MAX_MANUAL:
        raise PersonalBackupError(f'You have {MAX_MANUAL} backups. Delete one to make another.')
    root = user_dir(user_id)
    os.makedirs(root, exist_ok=True)
    name = site._new_name(root)
    tmp = os.path.join(root, f'.{name}.partial')
    try:
        os.makedirs(tmp)
        tables = snapshot(conn, user_id)
        files = 0
        uploads = os.path.join(tmp, 'uploads')
        for rel in sorted(_cover_paths(tables)):
            src = os.path.join(image_utils.STATIC_ROOT, rel)
            if not os.path.isfile(src):
                continue
            dst = os.path.join(uploads, os.path.relpath(rel, 'uploads'))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            try:
                os.link(src, dst)
            except OSError:
                shutil.copy2(src, dst)
            files += 1
        data = {
            'format': FORMAT,
            'user_id': user_id,
            'username': username,
            'created_at': datetime.now().isoformat(timespec='seconds'),
            'kind': kind,
            'migrations': sorted(r[0] for r in conn.execute('SELECT name FROM schema_migrations')),
            'counts': _counts(tables),
            'files': files,
            'tables': tables,
        }
        with open(os.path.join(tmp, DATA_FILE), 'w', encoding='utf-8') as f:
            json.dump(data, f)
        os.rename(tmp, os.path.join(root, name))
    except OSError as e:
        shutil.rmtree(tmp, ignore_errors=True)
        raise PersonalBackupError(f'The backup failed: {e.__class__.__name__}.') from e
    made = info(user_id, name)
    if kind != 'manual' and prune:
        _prune(user_id, keep=name)
    return made


def _load(user_id, name):
    with open(os.path.join(folder(user_id, name), DATA_FILE), encoding='utf-8') as f:
        data = json.load(f)
    if data.get('user_id') != user_id or data.get('format') != FORMAT:
        raise PersonalBackupError("This backup can't be read.")
    return data


def info(user_id, name):
    """A backup's details without its rows: name, created_at (datetime),
    kind, kind_label, counts, files."""
    data = _load(user_id, name)
    return {
        'name': name,
        'created_at': datetime.fromisoformat(data['created_at']),
        'kind': data['kind'],
        'kind_label': KINDS.get(data['kind'], data['kind']),
        'counts': data['counts'],
        'files': data['files'],
    }


def list_backups(user_id):
    root = user_dir(user_id)
    if not os.path.isdir(root):
        return []
    found = []
    for name in os.listdir(root):
        if not site.NAME_RE.match(name):
            continue
        try:
            found.append(info(user_id, name))
        except (PersonalBackupError, OSError, ValueError, KeyError):
            continue
    return sorted(found, key=lambda b: (b['created_at'], site._serial(b['name'])), reverse=True)


def latest(user_id):
    found = list_backups(user_id)
    return found[0] if found else None


def delete(user_id, name):
    shutil.rmtree(folder(user_id, name))


def _prune(user_id, keep=None):
    automatic = [b for b in list_backups(user_id) if b['kind'] != 'manual']
    for b in automatic[KEEP_AUTOMATIC:]:
        if b['name'] != keep:
            shutil.rmtree(os.path.join(user_dir(user_id), b['name']), ignore_errors=True)


# --- restoring -------------------------------------------------------------

def _insert(conn, table, saved, live_books):
    """Put a table's saved rows back. Only columns both sides have; a row
    whose book is gone is skipped (or its book_id nulled, where the key is
    SET NULL). Returns the number skipped."""
    live = conn.execute(f'PRAGMA table_info({table})').fetchall()
    have = set(saved['columns'])
    missing = [c[1] for c in live if c[3] and c[4] is None and not c[5] and c[1] not in have]
    if missing:
        raise PersonalBackupError('This backup is from an older Libaraxia that lacks '
                                  f"{table}.{missing[0]}; it can't be restored.")
    cols = [c[1] for c in live if c[1] in have]
    idx = [saved['columns'].index(c) for c in cols]
    book_i = cols.index('book_id') if 'book_id' in cols else None
    sql = f'INSERT INTO {table} ({", ".join(cols)}) VALUES ({", ".join("?" * len(cols))})'
    skipped = 0
    for row in saved['rows']:
        values = [row[i] for i in idx]
        if book_i is not None and values[book_i] is not None and values[book_i] not in live_books:
            if table in BOOK_NULLABLE:
                values[book_i] = None
            else:
                skipped += 1
                continue
        conn.execute(sql, values)
    return skipped


def restore(conn, user_id, username, name):
    """Put a user's library back as backup `name` has it. Commits.

    Returns {'restored': info, 'safety': info, 'books_back', 'books_removed',
    'kept': [(title, [usernames])], 'given_away': [titles], 'skipped',
    'files'}. Raises PersonalBackupError, with nothing changed."""
    from models import other_users_with_book_data
    from utils.image_utils import delete_image_file

    data = _load(user_id, name)
    tables = data['tables']
    meta = info(user_id, name)
    # Not pruned yet: that could take the backup being restored
    safety = create(conn, user_id, username, 'before_restore', prune=False)

    saved_books = tables['books']
    id_i = saved_books['columns'].index('id')
    saved_ids = {r[id_i] for r in saved_books['rows']}
    result = {'restored': meta, 'safety': safety, 'books_back': 0, 'books_removed': 0,
              'kept': [], 'given_away': [], 'skipped': 0, 'files': 0}
    removed_covers = []
    try:
        # 1. Your rows go (children cascade from their parents)
        for t in reversed(USER_TABLES):
            conn.execute(f'DELETE FROM {t} WHERE user_id = ?', (user_id,))

        # 2. Books added since the backup, unless someone else has data on them
        for b in conn.execute('SELECT id, title, cover_image_url FROM books WHERE added_by = ?',
                              (user_id,)).fetchall():
            if b['id'] in saved_ids:
                continue
            others = other_users_with_book_data(conn, b['id'], user_id)
            if others:
                result['kept'].append((b['title'], others))
            else:
                conn.execute('DELETE FROM books WHERE id = ?', (b['id'],))
                result['books_removed'] += 1
                if b['cover_image_url']:
                    removed_covers.append(b['cover_image_url'])

        # 3. The backup's books: put back, inserted again, or left with their new owner
        live = conn.execute('PRAGMA table_info(books)').fetchall()
        have = set(saved_books['columns'])
        missing = [c[1] for c in live if c[3] and c[4] is None and not c[5] and c[1] not in have]
        if missing:
            raise PersonalBackupError('This backup is from an older Libaraxia that lacks '
                                      f"books.{missing[0]}; it can't be restored.")
        cols = [c[1] for c in live if c[1] in have]
        idx = [saved_books['columns'].index(c) for c in cols]
        sets = ', '.join(f'{c} = ?' for c in cols if c != 'id')
        for row in saved_books['rows']:
            values = dict(zip(cols, (row[i] for i in idx)))
            now = conn.execute('SELECT added_by, title FROM books WHERE id = ?', (values['id'],)).fetchone()
            if now is None:
                conn.execute(f'INSERT INTO books ({", ".join(cols)}) VALUES ({", ".join("?" * len(cols))})',
                             [values[c] for c in cols])
                result['books_back'] += 1
            elif now['added_by'] == user_id:
                conn.execute(f'UPDATE books SET {sets} WHERE id = ?',
                             [values[c] for c in cols if c != 'id'] + [values['id']])
            else:
                result['given_away'].append(now['title'])

        # 4. Your rows, parents before children
        live_books = {r[0] for r in conn.execute('SELECT id FROM books')}
        for t in USER_TABLES:
            result['skipped'] += _insert(conn, t, tables[t], live_books)
            if t in AFTER:
                result['skipped'] += _insert(conn, AFTER[t], tables[AFTER[t]], live_books)
        conn.commit()
    except PersonalBackupError:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise PersonalBackupError(f'The restore failed: {e.__class__.__name__}. Nothing was changed.') from e

    # Cover files: put back the missing ones, delete the unused ones
    saved_uploads = os.path.join(folder(user_id, name), 'uploads')
    for rel in sorted(_cover_paths(tables)):
        live_file = os.path.join(image_utils.STATIC_ROOT, rel)
        kept_file = os.path.join(saved_uploads, os.path.relpath(rel, 'uploads'))
        if not os.path.lexists(live_file) and os.path.isfile(kept_file):
            os.makedirs(os.path.dirname(live_file), exist_ok=True)
            try:
                os.link(kept_file, live_file)
            except OSError:
                shutil.copy2(kept_file, live_file)
            result['files'] += 1
    for path in removed_covers:
        if not conn.execute('SELECT 1 FROM books WHERE cover_image_url = ?', (path,)).fetchone():
            delete_image_file(path)
    _prune(user_id, keep=name)
    return result
