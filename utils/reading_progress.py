"""Manual reading progress (ROADMAP 16.0f, docs/PROGRESS-MERGE-SPEC.md part A).

For books Audiobookshelf doesn't track (paper, ebooks read elsewhere): you
type the page you're on and the app works out the percent from the book's
page count; a book without one (and any ebook or audiobook, where page
counts mean little) takes a percent instead.

Progress lives on your **open** reading session: started, not finished.
An undated session (no start, no finish: a book read long ago) is not
open. A re-read is a new session, so it starts again at 0 and the first
read's history is left alone. Only the session's own user ever sees it.

  set_progress(conn, user_id, book_id, page=, percent=)  write; caller commits
  open_session(conn, user_id, book_id)                   the row progress goes on
  rings(conn, user_id)                                   {book_id: (0..1, progress_at)}
"""
from datetime import date

from utils import media

# Formats whose page count isn't the reader's page: these take a percent.
PERCENT_FORMATS = ('Audiobook', 'Ebook')
CURRENTLY_READING = 'currently reading'


class ProgressError(ValueError):
    """Input that can't be stored; the message is safe to show."""


def takes_page(book):
    """True when progress on this book is typed as a page: it has a page
    count and isn't an ebook or audiobook. `book` is a row or dict with
    `page_count` and `format`."""
    return bool(book['page_count']) and book['page_count'] > 0 \
        and book['format'] not in PERCENT_FORMATS


def open_session(conn, user_id, book_id):
    """Your open session on a book (the latest, if somehow more than one),
    or None."""
    return conn.execute(
        'SELECT * FROM reading_sessions '
        'WHERE user_id = ? AND book_id = ? AND date_started IS NOT NULL AND date_completed IS NULL '
        'ORDER BY date_started DESC, session_id DESC LIMIT 1',
        (user_id, book_id)).fetchone()


def _number(value, kind):
    """A form value as a non-negative number, or ProgressError."""
    try:
        n = float(str(value).strip().rstrip('%'))
    except (TypeError, ValueError):
        raise ProgressError(f'Enter the {kind} as a number.')
    if n != n or n < 0:                                     # NaN or negative
        raise ProgressError(f'Enter the {kind} as a number, 0 or more.')
    return n


def compute(book, page=None, percent=None):
    """(progress 0..1, page or None) from what was typed. A page past the
    end is kept as typed and counts as 100 % (a page count is often a few
    pages off the edition in hand). Raises ProgressError."""
    if page not in (None, ''):
        if not takes_page(book):
            raise ProgressError('This book has no page count, so enter a percent instead.')
        n = _number(page, 'page')
        if n != int(n):
            raise ProgressError('Enter a whole page number.')
        n = int(n)
        return min(n / book['page_count'], 1.0), n
    if percent not in (None, ''):
        n = _number(percent, 'percent')
        if n > 100:
            raise ProgressError('A percent goes up to 100.')
        return n / 100, None
    raise ProgressError('Enter the page you are on.' if takes_page(book) else 'Enter how far along you are.')


def set_progress(conn, user_id, book_id, page=None, percent=None):
    """Store how far you are in a book. With no open session, one is opened
    today, and the status becomes Currently Reading (as setting it by hand
    does: announced, not quiet). Returns {'progress', 'page', 'opened',
    'status_set'}. Raises ProgressError. Caller checks access and commits."""
    book = conn.execute('SELECT id, media_type, page_count, format FROM books WHERE id = ?',
                        (book_id,)).fetchone()
    if not book or media.media_type_of(book) != media.BOOK:
        raise ProgressError('Progress is for books only.')
    progress, page_no = compute(book, page, percent)

    session = open_session(conn, user_id, book_id)
    opened = session is None
    if opened:
        cur = conn.execute('INSERT INTO reading_sessions (user_id, book_id, date_started) VALUES (?, ?, ?)',
                           (user_id, book_id, date.today().isoformat()))
        session_id = cur.lastrowid
    else:
        session_id = session['session_id']
    conn.execute('UPDATE reading_sessions SET progress = ?, progress_page = ?, progress_at = CURRENT_TIMESTAMP '
                 'WHERE session_id = ? AND user_id = ?', (progress, page_no, session_id, user_id))

    status = conn.execute('SELECT status FROM collections WHERE user_id = ? AND book_id = ?',
                          (user_id, book_id)).fetchone()
    status_set = not status or status['status'] != CURRENTLY_READING
    if status:
        if status_set:
            conn.execute('UPDATE collections SET status = ?, quiet = 0, updated_at = CURRENT_TIMESTAMP '
                         'WHERE user_id = ? AND book_id = ?', (CURRENTLY_READING, user_id, book_id))
    else:
        conn.execute('INSERT INTO collections (user_id, book_id, status) VALUES (?, ?, ?)',
                     (user_id, book_id, CURRENTLY_READING))
    return {'progress': progress, 'page': page_no, 'opened': opened, 'status_set': status_set}


def rings(conn, user_id):
    """{book_id: (progress 0..1, progress_at)} for your open sessions with
    progress above 0: the manual side of the cover's ring. Yours only."""
    found = {}
    for r in conn.execute(
            'SELECT book_id, progress, progress_at FROM reading_sessions '
            'WHERE user_id = ? AND date_started IS NOT NULL AND date_completed IS NULL AND progress > 0 '
            'ORDER BY date_started, session_id', (user_id,)):
        found[r['book_id']] = (r['progress'], r['progress_at'])   # the latest open session wins
    return found
