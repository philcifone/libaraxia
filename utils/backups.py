"""Site backups from the admin pages: back up, restore, download, delete.

One backup is a folder in the backup directory, named by when it was made
(20261112-143005), holding

    library.db   a consistent copy of the database (SQLite's online backup)
    uploads/     the covers and avatars as they were, as hard links
    meta.json    who made it, why, the migrations it has, a few counts

Hard links cost almost no disk: a cover file is never rewritten in place
(every upload or crop gets a new name), so a link keeps that cover exactly
as it was for as long as the backup exists, even after the app deletes its
own copy (an undone import, the orphaned images cleanup). Where linking
fails (the backup directory is on another filesystem), the file is copied.

The backup directory is BACKUP_DIR, default "backups" next to the database
file. It must not be inside static/, which is served to the browser.

A backup is of the whole site, every user, so restoring one is an admin's
call: everything anyone did after it is replaced, and that can't be
undone. Site backups are only made by hand and stay until deleted. Each
user's own library backups, which the Goodreads import takes, are
utils/personal_backups.py.

A backup made before a migration is restored and then brought up to date
with the same runner as `manage.py migrate`. One made by newer code (it has
migrations this code doesn't know) is refused.
"""
import json
import os
import re
import shutil
import sqlite3
from datetime import datetime

from utils import image_utils
from utils.database import database_path

KINDS = {
    'manual': 'Backed up by hand',
}
NAME_RE = re.compile(r'^\d{8}-\d{6}(-\d+)?$')
DB_FILE = 'library.db'
META_FILE = 'meta.json'
# Not covers: crop previews waiting to be saved (utils/cover_crop.py)
SKIP_UPLOADS = {'crop'}


class BackupError(Exception):
    """Something the admin should be told, in words fit to show them."""


def backup_dir():
    """Where backups live: BACKUP_DIR, or "backups" beside the database.
    Read on every call, like DATABASE_PATH, so tests can point it elsewhere."""
    path = os.getenv('BACKUP_DIR')
    if path:
        return os.path.abspath(path)
    return os.path.join(os.path.dirname(database_path()), 'backups')


def uploads_dir():
    return os.path.realpath(os.path.join(image_utils.STATIC_ROOT, 'uploads'))


def folder(name):
    """The folder of backup `name`, refusing anything that isn't one of ours
    (the name comes from a URL)."""
    if not isinstance(name, str) or not NAME_RE.match(name):
        raise BackupError('No such backup.')
    path = os.path.join(backup_dir(), name)
    if not os.path.isfile(os.path.join(path, META_FILE)):
        raise BackupError('No such backup.')
    return path


def _migrations(db_file):
    conn = sqlite3.connect(db_file)
    try:
        return sorted(r[0] for r in conn.execute('SELECT name FROM schema_migrations'))
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def _integrity(db_file):
    conn = sqlite3.connect(db_file)
    try:
        return conn.execute('PRAGMA integrity_check').fetchone()[0]
    finally:
        conn.close()


def _copy_db(src_file, dst_file):
    """SQLite's online backup: a consistent copy even while others write."""
    src, dst = sqlite3.connect(src_file), sqlite3.connect(dst_file)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def _link_tree(src_root, dst_root, only_missing=False):
    """Hard-link (or copy) every file under src_root to the same place under
    dst_root. only_missing: leave files already there alone. Returns the
    number of files placed."""
    placed = 0
    for here, dirs, files in os.walk(src_root):
        rel = os.path.relpath(here, src_root)
        if rel == '.':
            dirs[:] = [d for d in dirs if d not in SKIP_UPLOADS]
        target = os.path.normpath(os.path.join(dst_root, rel))
        os.makedirs(target, exist_ok=True)
        for f in files:
            src, dst = os.path.join(here, f), os.path.join(target, f)
            if os.path.islink(src) or not os.path.isfile(src):
                continue
            if only_missing and os.path.lexists(dst):
                continue
            try:
                os.link(src, dst)
            except OSError:
                shutil.copy2(src, dst)
            placed += 1
    return placed


def _new_name(root):
    """Now, plus -2, -3 ... for more in the same second, always above any
    serial already used that second (even one since pruned would be fine,
    but a reused one would sort as older than it is)."""
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    used = [_serial(n) for n in os.listdir(root)
            if n.lstrip('.').startswith(stamp)] if os.path.isdir(root) else []
    if not used:
        return stamp
    return f'{stamp}-{max(used) + 1}'


def create(kind='manual', username=None):
    """Back up the database and the uploads. Returns the new backup's info
    (as list_backups() gives it). Raises BackupError if it can't."""
    if kind not in KINDS:
        raise ValueError(kind)
    root = backup_dir()
    os.makedirs(root, exist_ok=True)
    name = _new_name(root)
    # Built under a dot-name and renamed at the end, so a half-made backup
    # never shows in the list (list_backups skips dot-names)
    tmp = os.path.join(root, f'.{name}.partial')
    try:
        os.makedirs(tmp)
        db_file = os.path.join(tmp, DB_FILE)
        _copy_db(database_path(), db_file)
        ok = _integrity(db_file)
        if ok != 'ok':
            raise BackupError(f'The copy failed its integrity check ({ok}).')
        files = 0
        if os.path.isdir(uploads_dir()):
            files = _link_tree(uploads_dir(), os.path.join(tmp, 'uploads'))
        conn = sqlite3.connect(db_file)
        try:
            counts = {t: conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
                      for t in ('users', 'books', 'read_data')}
        finally:
            conn.close()
        meta = {
            'created_at': datetime.now().isoformat(timespec='seconds'),
            'kind': kind,
            'by': username,
            'migrations': _migrations(db_file),
            'counts': counts,
            'files': files,
            'db_bytes': os.path.getsize(db_file),
        }
        with open(os.path.join(tmp, META_FILE), 'w', encoding='utf-8') as f:
            json.dump(meta, f, indent=2)
        os.rename(tmp, os.path.join(root, name))
    except BackupError:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    except (OSError, sqlite3.Error) as e:
        shutil.rmtree(tmp, ignore_errors=True)
        raise BackupError(f'The backup failed: {e.__class__.__name__}.') from e
    made = info(name)
    return made


def info(name):
    """One backup's details: name, created_at (datetime), kind, kind_label,
    by, counts, files, db_bytes, migrations."""
    path = folder(name)
    with open(os.path.join(path, META_FILE), encoding='utf-8') as f:
        meta = json.load(f)
    meta['name'] = name
    meta['created_at'] = datetime.fromisoformat(meta['created_at'])
    meta['kind_label'] = KINDS.get(meta.get('kind'), meta.get('kind'))
    return meta


def list_backups():
    """Every backup, newest first. A folder without a readable meta.json is
    left out (and left alone)."""
    root = backup_dir()
    if not os.path.isdir(root):
        return []
    found = []
    for name in os.listdir(root):
        if not NAME_RE.match(name):
            continue
        try:
            found.append(info(name))
        except (BackupError, OSError, ValueError, KeyError):
            continue
    # Same second: 20261112-143005, -2, -3 ... in the order they were made
    return sorted(found, key=lambda b: (b['created_at'], _serial(b['name'])), reverse=True)


def _serial(name):
    """20261112-143005 -> 1, 20261112-143005-3 -> 3 (also for the
    .partial folder names)."""
    parts = name.lstrip('.').split('.')[0].split('-')
    return int(parts[2]) if len(parts) == 3 and parts[2].isdigit() else 1


def latest():
    backups = list_backups()
    return backups[0] if backups else None


def delete(name):
    shutil.rmtree(folder(name))



def restore(name):
    """Replace the live database with backup `name`, and put back any of
    its upload files that are gone.

    The caller must not hold a read or write open on the database (close
    the request's connection first): the copy needs every lock.

    Returns {'restored': info, 'files': upload files put back,
    'migrated': migrations applied}."""
    import manage  # the migration runner, shared with `manage.py migrate`

    path = folder(name)
    meta = info(name)
    src_db = os.path.join(path, DB_FILE)
    if _integrity(src_db) != 'ok':
        raise BackupError("This backup's database is damaged; it can't be restored.")
    known = manage.migration_files()
    has = set(_migrations(src_db))
    newer = sorted(has - set(known))
    if newer:
        raise BackupError(f'This backup was made by a newer Libaraxia (it has {newer[-1]}); '
                          'update the app before restoring it.')
    pending = [m for m in known if m not in has]

    # Bring a scratch copy up to date first, so the live DB is only touched
    # once everything that can fail has succeeded
    scratch = os.path.join(backup_dir(), f'.restore-{name}.db')
    try:
        _copy_db(src_db, scratch)
        conn = manage.connect(scratch)
        try:
            for m in pending:
                manage.apply_migration(conn, m)
        finally:
            conn.close()

        _copy_db(scratch, database_path())
    except BackupError:
        raise
    except Exception as e:
        raise BackupError(f'The restore failed: {e.__class__.__name__}. Nothing was changed.') from e
    finally:
        if os.path.exists(scratch):
            os.remove(scratch)

    files = 0
    backed_up = os.path.join(path, 'uploads')
    if os.path.isdir(backed_up):
        files = _link_tree(backed_up, uploads_dir(), only_missing=True)
    return {'restored': meta, 'files': files, 'migrated': pending}
