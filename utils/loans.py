"""Loans: who has a physical copy (ROADMAP 16.0d, docs/LENDING-SPEC.md).

A loan is a record, not a lock. Nothing is enforced and nobody accepts it;
it says "bob has alice's Dune since March" until someone marks it returned.

Rules:
- The shelf's people lend: the item's owner or a member of the owner's
  household, or an admin. The same people mark it returned or delete a
  loan made by mistake (`can_lend`).
- Only an item on the shelf can be lent: owned, not removed, not a wishlist
  entry (`lendable`). After that the loan doesn't follow the item: removing,
  unowning or transferring it leaves the loan as it is, so no other write
  path has to know about loans.
- The borrower is a user in the lender's circle (household or friend), or
  anyone else as a typed name. `borrower_name` is always stored, so a loan
  still reads right after the borrower's account is deleted.
- One open loan per item (a partial unique index in migration 042).
- Who sees loans: the shelf's people and admins see every loan of the item;
  a borrower sees only their own (`history`).
- Notifications: the borrower (a user) when it's lent to them; the owner when
  someone else lends their item or marks it returned. Never the person who
  acted, never the borrower on a return.

Functions take the caller's connection and leave committing to the caller.
A refused action raises LoanError with a message that is safe to show.
"""
import sqlite3
from datetime import date

from models import circle_ids, get_library_members

# Notification types written here (notifications.type).
TO_BORROWER = 'loan'
TO_OWNER = 'loan_owner'

MAX_NAME = 100
MAX_NOTE = 500


class LoanError(Exception):
    """A refused loan action; the message is safe to show."""


# --- dates -----------------------------------------------------------------

def today():
    return date.today().isoformat()


def parse_date(value, label, required=False):
    """A form's date ('YYYY-MM-DD') as that string, None when empty and
    optional. Anything else is a LoanError naming the field."""
    value = (value or '').strip()
    if not value:
        if required:
            raise LoanError(f'{label} is required.')
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise LoanError(f'{label} is not a date.') from None


# --- who may do what -------------------------------------------------------

def shelf_people(conn, book):
    """Ids of the people whose shelf the item is on: its owner and their
    household. Empty for an item nobody owns."""
    if book['added_by'] is None:
        return []
    return get_library_members(book['added_by'], conn)


def can_lend(conn, user, book):
    """Whether `user` may lend this item, mark it returned or delete its
    loans: an admin, or someone whose shelf it is on."""
    return bool(user.is_admin or user.id in shelf_people(conn, book))


def lendable(conn, book):
    """Whether the item is on its owner's shelf, so it can be lent now."""
    if book['added_by'] is None or not book['owned'] or book['removed_at']:
        return False
    wish = conn.execute('SELECT 1 FROM wishlist WHERE book_id = ? AND user_id = ?',
                        (book['id'], book['added_by'])).fetchone()
    return wish is None


def borrower_choices(conn, user_id):
    """Users the lender can pick as borrower: their circle (household first,
    then friends) without themselves or deactivated accounts. Each a dict of
    id, username and household (bool)."""
    others = [i for i in circle_ids(conn, user_id) if i != user_id]
    if not others:
        return []
    household = set(get_library_members(user_id, conn))
    marks = ','.join('?' * len(others))
    rows = conn.execute(f'''
        SELECT id, username FROM users
        WHERE id IN ({marks}) AND COALESCE(is_active, 1) = 1
    ''', others).fetchall()
    choices = [{'id': r['id'], 'username': r['username'], 'household': r['id'] in household}
               for r in rows]
    choices.sort(key=lambda c: (not c['household'], c['username'].lower()))
    return choices


# --- reading ---------------------------------------------------------------

# Every loan query selects these, so pages can show the live usernames
# (`borrower` falls back on the stored name, `lender` may be None when the
# lender's account is gone).
_COLUMNS = '''
    l.*, COALESCE(bu.username, l.borrower_name) AS borrower,
    lu.username AS lender, ou.username AS owner
'''
_JOINS = '''
    JOIN books b ON b.id = l.book_id
    LEFT JOIN users bu ON bu.id = l.borrower_id
    LEFT JOIN users lu ON lu.id = l.lent_by
    LEFT JOIN users ou ON ou.id = b.added_by
'''


def get(conn, loan_id):
    return conn.execute(f'SELECT {_COLUMNS} FROM loans l {_JOINS} WHERE l.id = ?',
                        (loan_id,)).fetchone()


def open_loan(conn, book_id):
    """The item's open loan, or None."""
    return conn.execute(f'''
        SELECT {_COLUMNS} FROM loans l {_JOINS}
        WHERE l.book_id = ? AND l.returned_at IS NULL
    ''', (book_id,)).fetchone()


def history(conn, user, book):
    """The loans of an item that `user` may see, newest first: all of them
    for the shelf's people and admins, only their own for a borrower."""
    sql = f'SELECT {_COLUMNS} FROM loans l {_JOINS} WHERE l.book_id = ?'
    params = [book['id']]
    if not can_lend(conn, user, book):
        sql += ' AND l.borrower_id = ?'
        params.append(user.id)
    sql += ' ORDER BY l.lent_at DESC, l.id DESC'
    return conn.execute(sql, params).fetchall()


def lent_map(conn, user_id, book_ids):
    """{book_id: borrower} for the open loans among `book_ids` on the user's
    or their household's shelf: the grids' Lent badge. Items on anyone
    else's shelf are left out, so a friend's grid never shows a borrower."""
    book_ids = [i for i in book_ids if i is not None]
    if not book_ids:
        return {}
    members = get_library_members(user_id, conn)
    marks = ','.join('?' * len(book_ids))
    owners = ','.join('?' * len(members))
    rows = conn.execute(f'''
        SELECT l.book_id, COALESCE(bu.username, l.borrower_name) AS borrower
        FROM loans l JOIN books b ON b.id = l.book_id
        LEFT JOIN users bu ON bu.id = l.borrower_id
        WHERE l.returned_at IS NULL AND l.book_id IN ({marks}) AND b.added_by IN ({owners})
    ''', [*book_ids, *members]).fetchall()
    return {r['book_id']: r['borrower'] for r in rows}


def borrowed_by(conn, user_id):
    """What the user has borrowed and not returned, newest first, with the
    item's columns a shelf row needs."""
    return conn.execute(f'''
        SELECT {_COLUMNS}, b.title, b.cover_image_url, b.media_type
        FROM loans l {_JOINS}
        WHERE l.borrower_id = ? AND l.returned_at IS NULL
        ORDER BY l.lent_at DESC, l.id DESC
    ''', (user_id,)).fetchall()


def lent_out(conn, user_id, media_type=None):
    """Open loans of items on the user's or their household's shelf, newest
    first, optionally of one media type."""
    members = get_library_members(user_id, conn)
    owners = ','.join('?' * len(members))
    sql = f'''
        SELECT {_COLUMNS}, b.title, b.cover_image_url, b.media_type
        FROM loans l {_JOINS}
        WHERE l.returned_at IS NULL AND b.added_by IN ({owners})
    '''
    params = list(members)
    if media_type:
        sql += ' AND b.media_type = ?'
        params.append(media_type)
    sql += ' ORDER BY l.lent_at DESC, l.id DESC'
    return conn.execute(sql, params).fetchall()


# --- writing ---------------------------------------------------------------

def _notify(conn, recipient_id, kind, message, book_id, actor_id):
    """One notification, skipped when it would go to the person who acted
    (or to nobody: a borrower who isn't a user, an item without an owner)."""
    if recipient_id is None or recipient_id == actor_id:
        return
    conn.execute('''
        INSERT INTO notifications (user_id, type, message, related_activity_type,
                                   related_book_id, from_user_id)
        VALUES (?, ?, ?, 'loan', ?, ?)
    ''', (recipient_id, kind, message, book_id, actor_id))


def lend(conn, user, book, borrower_id=None, borrower_name='', lent_at=None,
         due_at=None, note=''):
    """Record that `user` lent the item. `borrower_id` (a user in the
    lender's circle) or `borrower_name` (anyone else). Dates are strings
    from a form; `lent_at` defaults to today. Returns the new loan's id."""
    if not can_lend(conn, user, book):
        raise LoanError("Only the item's owner or their household can lend it.")
    if not lendable(conn, book):
        raise LoanError('Only something on the shelf can be lent.')
    current = open_loan(conn, book['id'])
    if current:
        raise LoanError(f"It's already lent to {current['borrower']}.")

    if borrower_id:
        choices = {c['id']: c['username'] for c in borrower_choices(conn, user.id)}
        try:
            borrower_id = int(borrower_id)
        except (TypeError, ValueError):
            borrower_id = None
        if borrower_id not in choices:
            raise LoanError('You can lend to your household or friends, or type a name.')
        borrower_name = choices[borrower_id]
    else:
        borrower_id = None
        borrower_name = ' '.join((borrower_name or '').split())
        if not borrower_name:
            raise LoanError('Who has it? Pick someone or type a name.')
        if len(borrower_name) > MAX_NAME:
            raise LoanError(f'A name can be at most {MAX_NAME} characters.')

    lent_at = parse_date(lent_at, 'Lent on') or today()
    due_at = parse_date(due_at, 'Due')
    if lent_at > today():
        raise LoanError("The lent date can't be in the future.")
    if due_at and due_at < lent_at:
        raise LoanError("The due date can't be before the lent date.")
    note = (note or '').strip()[:MAX_NOTE] or None

    try:
        cur = conn.execute('''
            INSERT INTO loans (book_id, lent_by, borrower_id, borrower_name, lent_at, due_at, note)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (book['id'], user.id, borrower_id, borrower_name, lent_at, due_at, note))
    except sqlite3.IntegrityError:
        # Someone lent it in the moment since open_loan() looked.
        raise LoanError("It's already lent.") from None

    title = book['title']
    _notify(conn, borrower_id, TO_BORROWER, f'{user.username} lent you {title}', book['id'], user.id)
    if borrower_id != book['added_by']:
        _notify(conn, book['added_by'], TO_OWNER,
                f'{user.username} lent your {title} to {borrower_name}', book['id'], user.id)
    return cur.lastrowid


def _loan_and_book(conn, user, loan_id):
    """The loan and its item, if `user` may manage it; LoanError otherwise
    (the same message whether it doesn't exist or isn't theirs)."""
    loan = get(conn, loan_id)
    book = loan and conn.execute('SELECT * FROM books WHERE id = ?', (loan['book_id'],)).fetchone()
    if not loan or not can_lend(conn, user, book):
        raise LoanError('That loan was not found.')
    return loan, book


def mark_returned(conn, user, loan_id, returned_at=None):
    """Close an open loan on `returned_at` (default today)."""
    loan, book = _loan_and_book(conn, user, loan_id)
    if loan['returned_at']:
        raise LoanError('That loan was already returned.')
    returned_at = parse_date(returned_at, 'Returned on') or today()
    if returned_at < loan['lent_at']:
        raise LoanError("It can't come back before it was lent.")
    if returned_at > today():
        raise LoanError("The return date can't be in the future.")
    conn.execute('UPDATE loans SET returned_at = ? WHERE id = ? AND returned_at IS NULL',
                 (returned_at, loan_id))
    _notify(conn, book['added_by'], TO_OWNER,
            f"{user.username} marked your {book['title']} returned", book['id'], user.id)
    return loan['book_id']


def delete(conn, user, loan_id):
    """Delete a loan recorded by mistake, with its unread notifications.
    (Notifications carry the item, not the loan; an item has one open loan
    at a time, so an unread one about this item is about this loan or an
    older one, which is stale either way.)"""
    loan, book = _loan_and_book(conn, user, loan_id)
    conn.execute('DELETE FROM loans WHERE id = ?', (loan_id,))
    conn.execute('''
        DELETE FROM notifications
        WHERE related_book_id = ? AND type IN (?, ?) AND COALESCE(is_read, 0) = 0
    ''', (book['id'], TO_BORROWER, TO_OWNER))
    return loan['book_id']
