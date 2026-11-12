"""Goodreads CSV parsing and the writers the import uses.

The import itself (stage, review, apply, undo) is utils/goodreads_plan.py,
ROADMAP 14b. This module turns a "Export Library" CSV row into clean values
(`parse_row`) and holds the plain writers the import calls once it has
decided what to write (`create_book`, `set_status`, `add_sessions`,
`add_wishlist`).

What parse_row decides:
- Exclusive Shelf `read` / `currently-reading` / a DNF-style shelf: that
  reading status. `to-read`: 'wishlist'. Another shelf with no sign of
  reading: None ("Not sure" on the review).
- Audiobooks (ROADMAP 8B.2): a row on an audiobook shelf, or with an audio
  Binding (Audible Audio, Audio CD, ...). A new book from one has format
  Audiobook.
- My Rating / My Review: plain-text review (Goodreads exports HTML).
- Read Count and Date Read: the reading sessions; Goodreads only keeps the
  date of the last read.
- `goodreads_id` (Book Id) and every shelf, raw, for the import's matching
  and provenance.

Not imported, on purpose: Additional Authors (mostly translators, editors
and illustrators, not co-authors), Binding (beyond telling audiobooks
apart), Owned Copies (Goodreads rarely has it set), Spoiler, Average Rating,
Original Publication Year when Year Published is present.
"""
import html
import re

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
    `collections` is the custom shelves (not the one that set the status;
    no longer made into collections, ROADMAP 14b decision 2); `shelves` is
    every shelf, raw, and `goodreads_id` the export's Book Id."""
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
