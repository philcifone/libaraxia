"""Goodreads CSV import.

`import_goodreads(conn, user_id, text)` turns a Goodreads "Export Library"
CSV into books, reading status, reviews, reading sessions, wishlist entries
and custom collections for one user, and returns a report in which every
row of the file has exactly one outcome (see OUTCOMES).

What goes where:
- Exclusive Shelf `read` / `currently-reading` / a DNF-style shelf: a
  reading status on the book (in your library, or your household's copy).
- `to-read`: your wishlist, unless you or your household already own the
  book, in which case it gets the *Want to Read* status instead.
- Every other shelf in `Bookshelves` (audiobook, re-read, ...) becomes a
  custom collection of the same name.
- Audiobooks (ROADMAP 8B.2): a row on an audiobook shelf, or with an audio
  Binding (Audible Audio, Audio CD, ...), that creates a new book creates it
  with format Audiobook and not owned (8B.3): read, reviewed, counted in
  reading stats, never on the shelf or in page totals. A to-read audiobook
  still goes to the wishlist (format Audiobook). A row that matches a book
  you already have leaves that book as it is.
- My Rating / My Review: a review, with or without a rating, on any shelf.
- Read Count: that many reading sessions; the last one is dated Date Read.
- Private Notes: the wishlist note for to-read books. Library books have
  nowhere to keep them, so the report counts them as not imported.

Not imported, on purpose: Additional Authors (mostly translators, editors
and illustrators, not co-authors), Binding (beyond telling audiobooks
apart), Owned
Copies (Goodreads rarely has it set; read books go to your library as
before), Spoiler, Average Rating, Original Publication Year when Year
Published is present.

Matching an existing book only looks at your own books and your
household's library (utils/book_matching.py), never anyone else's.

Each row runs inside a SAVEPOINT, so a row that fails leaves nothing behind
and the rest of the import carries on. The caller commits.
"""
import csv
import html
import logging
import re
from io import StringIO

from utils.book_matching import BookIndex

logger = logging.getLogger(__name__)

# Outcome of a row, in the order the result screen lists them. The counts
# of these always add up to the number of rows in the file.
OUTCOMES = {
    'added':    'New book added to your library',
    'matched':  'Matched a book you or your household already have',
    'wishlist': 'Added to your wishlist',
    'already':  'Already imported, left as it was',
    'skipped':  'Skipped (no title)',
    'error':    'Failed, nothing saved for this row',
}

READ_SHELVES = {'read': 'read', 'currently-reading': 'currently reading'}
WISHLIST_SHELVES = {'to-read', 'want-to-read'}
# Goodreads has no built-in DNF shelf; these are the names people use
DNF_SHELVES = {'dnf', 'did-not-finish', 'didnt-finish', 'did-not-finish-reading',
               'abandoned', 'gave-up', 'unfinished', 'not-finished', 'stopped-reading'}
REQUIRED_COLUMNS = {'Title', 'Author', 'Exclusive Shelf'}
# Audiobooks: by shelf name, or by Goodreads' Binding column
AUDIOBOOK_SHELVES = {'audiobook', 'audiobooks', 'audio-book', 'audio-books', 'audio', 'audible',
                     'listened', 'listened-to'}
AUDIO_BINDINGS = {'audible audio', 'audiobook', 'audio cd', 'audio cassette', 'mp3 cd',
                  'audio', 'audio play', 'preloaded digital audio player'}


class ImportFileError(ValueError):
    """The upload isn't something we can import. The message is for the user."""


# ------------------------------------------------------------------ parsing

def decode_csv(raw):
    """Bytes to text: UTF-8 (with or without BOM), else Windows-1252, else
    Latin-1 (which never fails). Returns (text, encoding)."""
    for encoding in ('utf-8-sig', 'cp1252'):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return raw.decode('latin-1'), 'latin-1'


def clean_text(value):
    """Trim and collapse runs of whitespace: Goodreads exports names like
    'Stephen        King'."""
    return re.sub(r'\s+', ' ', value or '').strip()


def clean_isbn(value):
    """Goodreads wraps ISBNs as ="0143129554" so spreadsheets keep the zeros."""
    return re.sub(r'[^0-9Xx]', '', value or '').upper()


def goodreads_date(value):
    """'2025/09/26' -> '2025-09-26'. Anything else (empty, malformed) -> None."""
    m = re.fullmatch(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})', (value or '').strip())
    if not m:
        return None
    return f'{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}'


def goodreads_int(value):
    """Whole number, or None for empty / non-numeric (stored as NULL, not '')."""
    value = (value or '').strip()
    return int(value) if value.isdigit() else None


def review_text(review):
    """Goodreads exports reviews as HTML. Store plain text: <br> becomes a
    newline (so <br/><br/> is a paragraph break), other tags are dropped and
    entities like &amp; are decoded. Reviews are shown with pre-wrap."""
    text = (review or '').replace('\r\n', '\n')
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    text = html.unescape(text)
    return re.sub(r'\n{3,}', '\n\n', text).strip()


def parse_row(row):
    """One CSV row as a dict of clean values, plus the decided status:
    'read', 'currently reading', 'did not finish', 'wishlist' or None
    (an unknown custom exclusive shelf and no sign of having read it).
    `collections` is the shelves today's importer turns into collections;
    `shelves` is every shelf, raw, and `goodreads_id` the export's Book Id
    (both for the granular import, ROADMAP 14b)."""
    get = lambda key: row.get(key) or ''
    exclusive = clean_text(get('Exclusive Shelf')).lower()
    shelves = [s.strip().lower() for s in get('Bookshelves').split(',') if s.strip()]
    read_count = goodreads_int(get('Read Count')) or 0
    date_read = goodreads_date(get('Date Read'))

    if exclusive in DNF_SHELVES:
        status = 'did not finish'
    elif exclusive in READ_SHELVES:
        status = READ_SHELVES[exclusive]
    elif exclusive in WISHLIST_SHELVES:
        status = 'wishlist'
    elif any(s in DNF_SHELVES for s in shelves):
        status = 'did not finish'
    elif read_count or date_read:
        status = 'read'
    else:
        status = None

    # Shelves that become custom collections: everything except the shelf
    # that set the status. An unknown exclusive shelf is kept as one too.
    status_shelves = set(READ_SHELVES) | WISHLIST_SHELVES
    if status == 'did not finish':
        status_shelves |= DNF_SHELVES
    custom = []
    for shelf in shelves + ([exclusive] if exclusive else []):
        if shelf not in status_shelves and shelf not in custom:
            custom.append(shelf)

    # Every shelf the row is on, status shelves included (ROADMAP 14b): the
    # review page filters by them and goodreads_rows keeps them, so a later
    # shelf filter or mapping needs no re-import. Order kept, duplicates
    # dropped; the exclusive shelf last when Bookshelves didn't list it.
    all_shelves = []
    for shelf in shelves + ([exclusive] if exclusive else []):
        if shelf not in all_shelves:
            all_shelves.append(shelf)

    rating = goodreads_int(get('My Rating'))
    return {
        'title': clean_text(get('Title')),
        'author': clean_text(get('Author')),
        'isbns': [i for i in (clean_isbn(get('ISBN13')), clean_isbn(get('ISBN'))) if i],
        'publisher': clean_text(get('Publisher')) or None,
        'year': goodreads_int(get('Year Published')) or goodreads_int(get('Original Publication Year')),
        'pages': goodreads_int(get('Number of Pages')) or None,
        'rating': rating if rating and 1 <= rating <= 5 else None,
        'review': review_text(get('My Review')),
        'private_notes': (get('Private Notes')).strip(),
        'date_read': date_read,
        'date_added': goodreads_date(get('Date Added')),
        'read_count': read_count,
        'status': status,
        'collections': custom,
        'audiobook': (any(s in AUDIOBOOK_SHELVES for s in shelves)
                      or clean_text(get('Binding')).lower() in AUDIO_BINDINGS),
        # Goodreads' stable id for the book (the export's Book Id), so a
        # re-import can match a book that was retitled or re-ISBN'd here.
        'goodreads_id': clean_text(get('Book Id')) or None,
        'shelves': all_shelves,
    }


# ------------------------------------------------------------------ writers
# Plain functions on (conn, user_id), shared by the granular import
# (utils/goodreads_plan.py), which decides what to write; these only write.

def create_book(conn, user_id, r, owned):
    """A new book from parsed row `r`, added by the user. Format Audiobook
    for an audiobook row. Returns its id.

    created_at is the Goodreads Date Added, so 300 imported books don't flood
    friends' feeds as "added today". The column default covers rows without
    one (never write NULL into it: it breaks feed order)."""
    cols = ['title', 'author', 'isbn', 'publisher', 'publish_year', 'page_count', 'added_by', 'owned']
    vals = [r['title'], r['author'] or 'Unknown', r['isbns'][0] if r['isbns'] else None,
            r['publisher'], r['year'], r['pages'], user_id, int(bool(owned))]
    if r['audiobook']:
        cols.append('format')
        vals.append('Audiobook')
    if r['date_added']:
        cols.append('created_at')
        vals.append(r['date_added'])
    return conn.execute(f"INSERT INTO books ({', '.join(cols)}) VALUES ({', '.join('?' * len(vals))})",
                        vals).lastrowid


def set_status(conn, user_id, book_id, status, date_added, quiet=0):
    """A new reading status, dated Date Added when there is one. `quiet` keeps
    it out of friends' feed (migration 031)."""
    if date_added:
        conn.execute('INSERT INTO collections (user_id, book_id, status, created_at, updated_at, quiet) '
                     'VALUES (?, ?, ?, ?, ?, ?)', (user_id, book_id, status, date_added, date_added, quiet))
    else:
        conn.execute('INSERT INTO collections (user_id, book_id, status, quiet) VALUES (?, ?, ?, ?)',
                     (user_id, book_id, status, quiet))


def add_sessions(conn, user_id, book_id, dates):
    """One reading session per date_completed in `dates` (None = undated).
    Returns the new session ids."""
    return [conn.execute('INSERT INTO reading_sessions (user_id, book_id, date_completed) VALUES (?, ?, ?)',
                         (user_id, book_id, date)).lastrowid for date in dates]


def add_wishlist(conn, user_id, book_id, notes, added_at):
    conn.execute('INSERT INTO wishlist (user_id, book_id, notes, added_at) '
                 'VALUES (?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))', (user_id, book_id, notes or None, added_at))


# ------------------------------------------------------------------ import

class _Importer:
    def __init__(self, conn, user_id):
        self.conn = conn
        self.user_id = user_id
        self.index = BookIndex(conn, user_id)
        self._collection_ids = {}
        self._pending_new_collections = []
        self.report = {
            'rows': [],
            'outcomes': {key: 0 for key in OUTCOMES},
            'totals': {'books_created': 0, 'statuses': 0, 'reviews': 0, 'ratings': 0,
                       'sessions': 0, 'collection_entries': 0, 'wishlist': 0,
                       'private_notes_not_imported': 0},
            'collections_created': [],
        }

    # --- helpers that write -------------------------------------------------

    def create_book(self, r):
        # Audiobooks not owned, unless it's a wishlist entry (those aren't
        # "owned" either way; buying one is "Move to library")
        owned = not r['audiobook'] or r['status'] == 'wishlist'
        self.report['totals']['books_created'] += 1
        return create_book(self.conn, self.user_id, r, owned)

    def has_status(self, book_id):
        return self.conn.execute('SELECT 1 FROM collections WHERE user_id = ? AND book_id = ?',
                                 (self.user_id, book_id)).fetchone() is not None

    def set_status(self, book_id, status, date_added):
        set_status(self.conn, self.user_id, book_id, status, date_added)
        self.report['totals']['statuses'] += 1

    def add_review(self, book_id, r):
        """Rating and/or review, unless you already have one on this book."""
        if not (r['rating'] or r['review']):
            return
        cur = self.conn.execute('INSERT OR IGNORE INTO read_data (user_id, book_id, rating, comment) '
                                'VALUES (?, ?, ?, ?)',
                                (self.user_id, book_id, r['rating'], r['review'] or None))
        if cur.rowcount:
            self.report['totals']['ratings'] += bool(r['rating'])
            self.report['totals']['reviews'] += bool(r['review'])

    def add_sessions(self, book_id, r):
        """Read Count sessions for a read book (at least one). Goodreads only
        keeps the date of the last read, so earlier reads are undated."""
        count = max(r['read_count'], 1)
        add_sessions(self.conn, self.user_id, book_id, [None] * (count - 1) + [r['date_read']])
        self.report['totals']['sessions'] += count

    def add_to_collections(self, book_id, names):
        for name in names:
            cid = self._collection_ids.get(name)
            if cid is None:
                # Goodreads is books only, so its shelves are Books shelves (8C)
                row = self.conn.execute('SELECT collection_id FROM user_collections '
                                        "WHERE user_id = ? AND name = ? AND media_type = 'book'",
                                        (self.user_id, name)).fetchone()
                if row:
                    cid = row['collection_id']
                else:
                    cid = self.conn.execute("INSERT INTO user_collections (user_id, name, media_type) "
                                            "VALUES (?, ?, 'book')", (self.user_id, name)).lastrowid
                    self._pending_new_collections.append(name)
                self._collection_ids[name] = cid
            cur = self.conn.execute('INSERT OR IGNORE INTO collection_books (collection_id, book_id) '
                                    'VALUES (?, ?)', (cid, book_id))
            self.report['totals']['collection_entries'] += cur.rowcount

    # --- one row --------------------------------------------------------------

    def row(self, r):
        """Write one parsed row. Returns (outcome, detail, new_book_row or None)."""
        status = r['status']
        book, whose = self.index.match(r['isbns'], r['title'], r['author'])
        new_book = None
        where = {'own': 'your library', 'household': "your household's library"}.get(whose)

        if status == 'wishlist':
            if book and book['is_wishlist_entry']:
                return 'already', 'already on your wishlist', None
            if book:
                # You (or your household) own it: Want to Read, not the wishlist
                if self.has_status(book['id']):
                    return 'already', f'already in {where} with a reading status', None
                book_id = book['id']
                self.set_status(book_id, 'want to read', r['date_added'])
                outcome, detail = 'matched', f'in {where}: marked Want to Read instead of wishlisted'
            else:
                book_id = self.create_book(r)
                new_book = {'id': book_id, 'isbn': r['isbns'][0] if r['isbns'] else None,
                            'title': r['title'], 'author': r['author'], 'removed_at': None,
                            'whose': 'own', 'is_wishlist_entry': 1}
                add_wishlist(self.conn, self.user_id, book_id, r['private_notes'], r['date_added'])
                self.report['totals']['wishlist'] += 1
                outcome, detail = 'wishlist', None
        else:
            if book:
                book_id = book['id']
                if self.has_status(book_id):
                    return 'already', f'already in {where} with a reading status', None
                outcome, detail = 'matched', f'in {where}'
                if book['is_wishlist_entry']:
                    # Read since it was imported as to-read: move it to the library
                    self.conn.execute('DELETE FROM wishlist WHERE user_id = ? AND book_id = ?',
                                      (self.user_id, book_id))
                    detail = 'moved from your wishlist to your library'
            else:
                book_id = self.create_book(r)
                new_book = {'id': book_id, 'isbn': r['isbns'][0] if r['isbns'] else None,
                            'title': r['title'], 'author': r['author'], 'removed_at': None,
                            'whose': 'own', 'is_wishlist_entry': 0}
                outcome, detail = 'added', ('audiobook, not owned: off your shelf, in your reading stats'
                                            if r['audiobook'] else None)
            if status:
                self.set_status(book_id, status, r['date_added'])
            else:
                detail = (detail + '; ' if detail else '') + 'unknown shelf, no reading status set'
            if status == 'read':
                self.add_sessions(book_id, r)
            if r['private_notes']:
                self.report['totals']['private_notes_not_imported'] += 1

        self.add_review(book_id, r)
        self.add_to_collections(book_id, r['collections'])
        return outcome, detail, new_book

    def run(self, reader):
        for line_no, raw in enumerate(reader, start=2):  # line 1 is the header
            r = parse_row(raw)
            entry = {'line': line_no, 'title': r['title'], 'author': r['author']}
            if not r['title']:
                entry.update(outcome='skipped', detail=None)
            else:
                self._pending_new_collections = []
                self.conn.execute('SAVEPOINT goodreads_row')
                try:
                    outcome, detail, new_book = self.row(r)
                    self.conn.execute('RELEASE goodreads_row')
                except Exception:
                    logger.exception('Goodreads import: line %s (%r) failed', line_no, r['title'])
                    self.conn.execute('ROLLBACK TO goodreads_row')
                    self.conn.execute('RELEASE goodreads_row')
                    # Collections created inside the failed row are gone too
                    for name in self._pending_new_collections:
                        self._collection_ids.pop(name, None)
                    outcome, detail, new_book = 'error', "couldn't import this row", None
                else:
                    if new_book:
                        self.index.add(new_book)
                    self.report['collections_created'] += self._pending_new_collections
                entry.update(outcome=outcome, detail=detail)
            self.report['outcomes'][entry['outcome']] += 1
            self.report['rows'].append(entry)
        return self.report


def import_goodreads(conn, user_id, text):
    """Import a Goodreads CSV (already decoded) for user_id. Doesn't commit.

    Raises ImportFileError if the text isn't a Goodreads export.
    """
    reader = csv.DictReader(StringIO(text))
    missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
    if missing:
        raise ImportFileError("This doesn't look like a Goodreads library export "
                              f"(missing column{'s' if len(missing) > 1 else ''}: {', '.join(sorted(missing))}).")
    # One transaction for the whole file. Without it the first SAVEPOINT
    # would open the transaction and its RELEASE would commit every row.
    if not conn.in_transaction:
        conn.execute('BEGIN')
    report = _Importer(conn, user_id).run(reader)
    report['total_rows'] = len(report['rows'])
    return report
