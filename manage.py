#!/usr/bin/env python3
"""Database management for Libaraxia.

    python3 manage.py status                 # which migrations are applied / pending
    python3 manage.py migrate                # back up, then apply pending migrations
    python3 manage.py migrate --dry-run      # show what would run, change nothing
    python3 manage.py migrate --baseline     # existing pre-runner DB: mark 001-013 applied
    python3 manage.py backup                 # just take a backup

Every command takes --db PATH. Without it, the same path the app uses is
picked (DATABASE_PATH from the environment or .env, default library.db in
the project directory). The resolved absolute path is always printed, so
check it before saying yes.

Migrations are the files migrations/NNN_name.sql, applied in name order.
Each one runs in its own transaction together with its schema_migrations
row, so it either applies completely or not at all. Migration files must
not contain BEGIN/COMMIT themselves.

Foreign keys are switched off while a migration runs (SQLite's recommended
way to rebuild tables), and the migration is rolled back if it leaves any
foreign_key_check violations that weren't there before.
"""
import argparse
import os
import re
import sqlite3
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
MIGRATIONS_DIR = os.path.join(ROOT, 'migrations')
SCHEMA_FILE = os.path.join(ROOT, 'create_database.sql')
MIGRATION_RE = re.compile(r'^\d{3}_[A-Za-z0-9_]+\.sql$')

# Last migration that existed before this runner. Databases created by hand
# (prod) are at this point when they get baselined.
BASELINE = '013'


def default_db_path():
    # Same resolution as the app: .env, then utils/database.py.
    sys.path.insert(0, ROOT)
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, '.env'))
    from utils.database import database_path
    return database_path()


def migration_files():
    names = sorted(f for f in os.listdir(MIGRATIONS_DIR) if MIGRATION_RE.match(f))
    prefixes = [n[:3] for n in names]
    dupes = {p for p in prefixes if prefixes.count(p) > 1}
    if dupes:
        sys.exit(f"error: more than one migration numbered {', '.join(sorted(dupes))}")
    return names


def connect(path):
    conn = sqlite3.connect(path, isolation_level=None)  # we manage transactions
    conn.row_factory = sqlite3.Row
    return conn


def has_table(conn, name):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    ).fetchone() is not None


def user_tables(conn):
    return [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")]


def ensure_ledger(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            name TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")


def applied(conn):
    if not has_table(conn, 'schema_migrations'):
        return set()
    return {r[0] for r in conn.execute('SELECT name FROM schema_migrations')}


def fk_violations(conn):
    """All foreign key violations, table by table. A table whose declared keys
    point at a column that isn't a key ("foreign key mismatch", e.g. the old
    collections -> books(book_id)) can't be checked; it's skipped until a
    migration rebuilds it, after which its violations count as new."""
    found = set()
    for (table,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall():
        try:
            found |= {tuple(r) for r in conn.execute('SELECT * FROM pragma_foreign_key_check(?)', (table,))}
        except sqlite3.OperationalError as e:
            if 'foreign key mismatch' not in str(e):
                raise
    return found


def backup(path):
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    dest, n = f'{path}.backup-{stamp}', 1
    while os.path.exists(dest):  # never overwrite an earlier backup
        n += 1
        dest = f'{path}.backup-{stamp}-{n}'
    src = sqlite3.connect(path)
    dst = sqlite3.connect(dest)
    try:
        src.backup(dst)  # online backup: consistent even while the app is running
    finally:
        dst.close()
        src.close()
    check = sqlite3.connect(dest)
    try:
        ok = check.execute('PRAGMA integrity_check').fetchone()[0]
    finally:
        check.close()
    if ok != 'ok':
        sys.exit(f'error: backup {dest} failed integrity_check: {ok}')
    print(f'Backup: {dest}')
    return dest


def confirm(prompt, assume_yes):
    if assume_yes:
        return True
    try:
        return input(f'{prompt} [y/N] ').strip().lower() in ('y', 'yes')
    except EOFError:
        return False


def apply_migration(conn, name):
    with open(os.path.join(MIGRATIONS_DIR, name), encoding='utf-8') as f:
        statements = split_statements(f.read())
    for stmt in statements:
        first = (re.match(r'\w*', re.sub(r'(--[^\n]*|\s)+', ' ', stmt).strip()).group(0)).upper()
        if first in ('BEGIN', 'COMMIT', 'END', 'ROLLBACK', 'SAVEPOINT', 'RELEASE'):
            raise RuntimeError(f'{name} contains {first}; the runner wraps each file in its own transaction')

    before = fk_violations(conn)
    conn.execute('PRAGMA foreign_keys = OFF')  # no-op inside a transaction, so set it first
    conn.execute('BEGIN')
    try:
        # executescript() would COMMIT first, so split on complete statements instead.
        for stmt in statements:
            conn.execute(stmt)
        new = fk_violations(conn) - before
        if new:
            raise RuntimeError(f'{name} leaves {len(new)} new foreign key violation(s), e.g. {sorted(new)[:3]}')
        conn.execute('INSERT INTO schema_migrations (name) VALUES (?)', (name,))
        conn.execute('COMMIT')
    except Exception:
        conn.execute('ROLLBACK')
        raise


def split_statements(sql):
    """Split a script into complete statements (handles ; inside strings, triggers)."""
    stmts, buf = [], ''
    for line in sql.splitlines(keepends=True):
        buf += line
        if sqlite3.complete_statement(buf):
            if buf.strip():
                stmts.append(buf)
            buf = ''
    if buf.strip() and re.sub(r'--[^\n]*', '', buf).strip():
        raise RuntimeError(f'incomplete SQL statement at end of file: {buf.strip()[:80]}')
    return stmts


def cmd_status(args):
    path = args.db
    print(f'Database: {path}')
    if not os.path.exists(path):
        print('  (does not exist; `migrate` will create it)')
        return
    conn = connect(path)
    done = applied(conn)
    if not has_table(conn, 'schema_migrations') and user_tables(conn):
        print('  No schema_migrations ledger. If this DB predates the runner, run `migrate --baseline`.')
    for name in migration_files():
        print(f"  [{'x' if name in done else ' '}] {name}")
    unknown = done - set(migration_files())
    for name in sorted(unknown):
        print(f'  [?] {name} (in ledger, file missing)')
    conn.close()


def cmd_backup(args):
    if not os.path.exists(args.db):
        sys.exit(f'error: {args.db} does not exist')
    backup(args.db)


def cmd_migrate(args):
    path = args.db
    files = migration_files()
    print(f'Database: {path}')

    fresh = not os.path.exists(path) or os.path.getsize(path) == 0
    if not fresh:
        conn = connect(path)
        if not user_tables(conn):
            fresh = True
        conn.close()

    if fresh:
        if args.baseline:
            sys.exit('error: --baseline is for existing databases; this one is empty')
        print('Empty database: creating it from create_database.sql')
        if args.dry_run:
            return
        conn = connect(path)
        with open(SCHEMA_FILE, encoding='utf-8') as f:
            conn.executescript(f.read())
        conn.close()

    conn = connect(path)

    if args.baseline:
        if has_table(conn, 'schema_migrations') and applied(conn):
            sys.exit('error: this database already has a migration ledger; --baseline is only for the first run')
        cols = {r['name'] for r in conn.execute("PRAGMA table_info('users')")}
        if 'theme_style' not in cols:
            sys.exit(f'error: users.theme_style is missing, so this DB is not at migration {BASELINE}. '
                     'Bring it up to date by hand first (see migrations/README.md).')
        marks = [f for f in files if f[:3] <= BASELINE]
        print(f'Baseline: mark {marks[0]} .. {marks[-1]} as applied (nothing is executed).')
        if args.dry_run:
            return
        if not confirm('Continue?', args.yes):
            sys.exit('aborted')
        backup(path)
        conn.execute('BEGIN')
        ensure_ledger(conn)
        conn.executemany('INSERT INTO schema_migrations (name) VALUES (?)', [(m,) for m in marks])
        conn.execute('COMMIT')
        print('Baseline recorded. Run `manage.py migrate` to apply the rest.')
        conn.close()
        return

    if not has_table(conn, 'schema_migrations'):
        sys.exit('error: this database has tables but no schema_migrations ledger.\n'
                 f'If it was set up by hand and is at migration {BASELINE}, run `manage.py migrate --baseline` once.')

    pending = [f for f in files if f not in applied(conn)]
    if not pending:
        print('Up to date.')
        return
    print('Pending:')
    for name in pending:
        print(f'  {name}')
    if args.dry_run:
        return
    if not fresh:
        if not confirm(f'Apply {len(pending)} migration(s)?', args.yes):
            sys.exit('aborted')
        backup(path)
    for name in pending:
        try:
            apply_migration(conn, name)
        except Exception as e:
            conn.close()
            sys.exit(f'FAILED {name}: {e}\n{name} was not applied; earlier migrations in this run stay applied.')
        print(f'Applied {name}')
    conn.close()
    print('Done.')


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--db', help='SQLite file (default: DATABASE_PATH or library.db)')
    sub = p.add_subparsers(dest='cmd', required=True)
    sub.add_parser('status', help='list applied and pending migrations')
    sub.add_parser('backup', help='back up the database next to itself')
    m = sub.add_parser('migrate', help='apply pending migrations (backs up first)')
    m.add_argument('--baseline', action='store_true', help=f'mark 001-{BASELINE} as applied on a pre-runner DB')
    m.add_argument('--dry-run', action='store_true', help='show what would happen, change nothing')
    m.add_argument('-y', '--yes', action='store_true', help="don't ask for confirmation")
    args = p.parse_args()
    args.db = os.path.abspath(args.db or default_db_path())
    {'status': cmd_status, 'backup': cmd_backup, 'migrate': cmd_migrate}[args.cmd](args)


if __name__ == '__main__':
    main()
