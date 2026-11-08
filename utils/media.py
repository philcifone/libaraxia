"""Media types: books and videos in one `books` table (Phase 8, migration 023).

A video is a `books` row with media_type = 'video' and a `format` ('VHS'
for now). The columns are shared and relabelled by type:

    column            book               video
    author            Author             Director
    publisher         Publisher          Studio
    publish_year      Publication Year   Release Year
    page_count        Page Count         (unused; runtime_minutes instead)
    isbn              ISBN               (unused; barcode instead)

The Library (and everything built on the `library_books` view) is books
only; the Videos section reads `library_videos`. Everything that differs by
type lives here, so templates (via `media_labels`) and JS (via data-
attributes) don't each keep their own copy.

The barcode helpers are the server-side twin of the check-digit code in
static/scanner.js: the scanner hands over 13 digits (UPC-A gets a leading
0), and `classify_code` decides whether that's a book or a video.
"""
import re

BOOK = 'book'
VIDEO = 'video'
MEDIA_TYPES = (BOOK, VIDEO)

# Physical formats a video row can have. Adding one needs no migration
# (books.format has no CHECK), just an entry here.
VIDEO_FORMATS = ('VHS', 'DVD')    # Phil, 2026-11-07: no LaserDisc or Betamax
DEFAULT_VIDEO_FORMAT = 'VHS'

# What the UI calls a format, where that differs from the stored value. A VHS
# tape is a "Cartridge" (Phil's name, after a novel); the DB keeps 'VHS', so
# filters, exports and the lookups don't change. Templates use the
# `format_label` filter (registered in app.py).
FORMAT_LABELS = {'VHS': 'Cartridge'}


def format_label(fmt):
    """Display name of a stored format ('VHS' -> 'Cartridge'); '' for None."""
    return FORMAT_LABELS.get(fmt, fmt or '')

# Per-user status (collections.status) by type. The CHECK in migration 023
# allows the union; routes check the status matches the item's type.
STATUSES = {
    BOOK: ('read', 'want to read', 'currently reading', 'did not finish'),
    VIDEO: ('watched', 'want to watch'),
}

# How each status is shown in menus.
STATUS_LABELS = {
    'read': 'Read', 'want to read': 'Want to Read',
    'currently reading': 'Currently Reading', 'did not finish': 'Did Not Finish',
    'watched': 'Watched', 'want to watch': 'Want to Watch',
}

# The status that sends you to the review page, and that the feed words as
# "finished" ("read" / "watched").
DONE_STATUS = {BOOK: 'read', VIDEO: 'watched'}

# Everything a template needs to word a page for one type. Keys are the same
# for both types, so a template can use m.creator without checking the type.
_LABELS = {
    BOOK: {
        'type': BOOK,
        'noun': 'book', 'Noun': 'Book', 'plural': 'books',
        'creator': 'Author', 'by': 'by',
        'publisher': 'Publisher',
        'year': 'Publication Year',
        'code': 'ISBN',
        'length': 'Page Count',
        'status_label': 'Reading Status',
        'history': 'Reading History',
        'session': 'Reading Session',
        'verb_past': 'read',            # "First time read"
        'in_progress': 'Currently Reading',
        'info_heading': 'Reading Info',
        'tags_heading': 'Book Tags',
        'about': 'About this Book',
        'shelf': 'library',             # "removed from the library"
        'section': 'Library',
    },
    VIDEO: {
        'type': VIDEO,
        'noun': 'movie', 'Noun': 'Movie', 'plural': 'movies',
        'creator': 'Director', 'by': 'directed by',
        'publisher': 'Studio',
        'year': 'Release Year',
        'code': 'Barcode',
        'length': 'Runtime',
        'status_label': 'Watch Status',
        'history': 'Viewing History',
        'session': 'Viewing',
        'verb_past': 'watched',
        'in_progress': 'Watching',
        'info_heading': 'Viewing Info',
        'tags_heading': 'Movie Tags',
        'about': 'About this Movie',
        'shelf': 'movie shelf',
        'section': 'Movies',
    },
}


def media_type_of(row):
    """The media type of a books row (or dict); 'book' when the column is
    missing, e.g. a row selected with only a few columns."""
    try:
        value = row['media_type']
    except (KeyError, IndexError, TypeError):
        return BOOK
    return value if value in MEDIA_TYPES else BOOK


def media_labels(media_type):
    """Labels and statuses for one type (see _LABELS), plus 'statuses'."""
    media_type = media_type if media_type in MEDIA_TYPES else BOOK
    return {**_LABELS[media_type], 'statuses': STATUSES[media_type],
            'status_labels': STATUS_LABELS, 'done_status': DONE_STATUS[media_type]}


def is_valid_status(media_type, status):
    return status in STATUSES.get(media_type, ())


def format_runtime(minutes):
    """120 -> '2 h 0 min', 95 -> '1 h 35 min', 45 -> '45 min', None -> ''."""
    if not minutes:
        return ''
    hours, mins = divmod(int(minutes), 60)
    return f'{hours} h {mins} min' if hours else f'{mins} min'


# ------------------------------------------------------------ barcodes

def digits_only(code):
    return re.sub(r'\D', '', code or '')


def ean13_check_digit(first12):
    """Check digit for the first 12 digits of an EAN-13 (UPC-A padded)."""
    total = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(first12))
    return (10 - total % 10) % 10


def is_valid_ean13(code):
    return (len(code) == 13 and code.isdigit()
            and ean13_check_digit(code[:12]) == int(code[12]))


def is_valid_isbn10(code):
    code = (code or '').upper()
    if not re.fullmatch(r'\d{9}[\dX]', code):
        return False
    total = sum((10 - i) * (10 if ch == 'X' else int(ch)) for i, ch in enumerate(code))
    return total % 11 == 0


def normalize_barcode(code):
    """Digits of a UPC-A or EAN-13 as 13 digits (UPC-A gets a leading 0),
    or None if it isn't a valid one. That's how barcodes are stored and
    compared, so a tape scanned as UPC-A matches one typed as EAN-13."""
    code = digits_only(code)
    if len(code) == 12:
        code = '0' + code
    return code if is_valid_ean13(code) else None


def classify_code(code):
    """What a scanned or typed code is: 'book', 'video' or None (invalid).

    An ISBN is an EAN-13 starting 978/979 (Bookland), or a valid ISBN-10.
    Any other valid EAN-13 or UPC-A is taken to be a video. ISBN-10 is
    checked first: a 10-digit code can't be a UPC/EAN anyway.
    """
    raw = re.sub(r'[\s-]', '', code or '').upper()
    if is_valid_isbn10(raw):
        return BOOK
    ean = normalize_barcode(raw)
    if not ean:
        return None
    return BOOK if ean.startswith(('978', '979')) else VIDEO


# ------------------------------------------------------------ SQL

def only(media_type, column='book_id'):
    """SQL condition: `column` (a books.id) is an item of this type.

    For queries on read_data, reading_sessions and collections, which don't
    know about media types:  f"WHERE r.user_id = ? AND {only(BOOK, 'r.book_id')}".
    The type is one of our constants, never user input, so it's inlined.
    """
    if media_type not in MEDIA_TYPES:
        raise ValueError(f'unknown media type {media_type!r}')
    return f"{column} IN (SELECT id FROM books WHERE media_type = '{media_type}')"
