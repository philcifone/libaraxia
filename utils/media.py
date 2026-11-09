"""Media types: books, videos and records in one `books` table (Phase 8,
migrations 023 and 024).

A video is a `books` row with media_type = 'video', a record one with
media_type = 'record'; both have a `format` ('VHS', 'DVD'; 'LP', '7in', ...).
The columns are shared and relabelled by type:

    column            book               video            record
    author            Author             Director         Artist
    publisher         Publisher          Studio           Label
    publish_year      Publication Year   Release Year     Year
    page_count        Page Count         (unused)         (unused)
    runtime_minutes   (unused)           Runtime          Length
    isbn              ISBN               (unused)         (unused)
    barcode           (unused)           Barcode          (unused for now)
    catalog_number    (unused)           Catalogue No.    Cat. No.
    description       Description        Synopsis         Tracklist and notes

The Library (and everything built on the `library_books` view) is books
only; the Movies section reads `library_videos` and Vinyls reads
`library_records`. Everything that differs by type lives here, so templates
(via `media_labels`) and JS (via data- attributes) don't each keep their own
copy. The database has the same lists of types and statuses in its
`media_types` and `statuses` tables (migration 024); a test checks they
agree with MEDIA_TYPES and STATUSES.

The barcode helpers are the server-side twin of the check-digit code in
static/scanner.js: the scanner hands over 13 digits (UPC-A gets a leading
0), and `classify_code` decides whether that's a book or a video. Records
aren't scanned (Phil, 2026-11-07): Add Vinyl is title search only.
"""
import re
from urllib.parse import quote_plus, urlencode

BOOK = 'book'
VIDEO = 'video'
RECORD = 'record'
MEDIA_TYPES = (BOOK, VIDEO, RECORD)

# Formats by type. Adding one needs no migration (books.format has no
# CHECK), just an entry here. Books (8B.2): a plain book is stored as NULL
# (every book from before 8B.2, and new ones), an audiobook as 'Audiobook';
# book_format() turns the form's choice into that. Audiobooks never count
# toward page totals (blueprints/user.py), owned or not.
FORMATS = {
    BOOK: ('Book', 'Audiobook'),
    VIDEO: ('VHS', 'DVD'),        # Phil, 2026-11-07: no LaserDisc or Betamax
    # Speed isn't stored: it follows from the format (LP 33, 7" 45); the odd
    # exception goes in the notes. CD and Cassette since the section became
    # Music (Phil, 2026-11-08); the type stays 'record' in code and the DB.
    RECORD: ('LP', 'EP', '7in', '10in', '12in', 'CD', 'Cassette'),
}
DEFAULT_FORMAT = {BOOK: 'Book', VIDEO: 'VHS', RECORD: 'LP'}
AUDIOBOOK = 'Audiobook'
VIDEO_FORMATS = FORMATS[VIDEO]
DEFAULT_VIDEO_FORMAT = DEFAULT_FORMAT[VIDEO]

# What the UI calls a format, where that differs from the stored value. A VHS
# tape is a "Cartridge" (Phil's name, after a novel); the DB keeps 'VHS', so
# filters, exports and the lookups don't change. Record sizes are stored
# without the inch mark, which would need quoting in URLs and CSV. Templates
# use the `format_label` filter (registered in app.py).
FORMAT_LABELS = {
    'VHS': 'Cartridge',
    '7in': '7" single', '10in': '10"', '12in': '12" single',
}


def book_format(value):
    """What to store for a book form's Format choice: 'Audiobook', or None
    for a plain book (so old rows and new ones read the same)."""
    return AUDIOBOOK if (value or '').strip() == AUDIOBOOK else None


def format_label(fmt):
    """Display name of a stored format ('VHS' -> 'Cartridge'); '' for None."""
    return FORMAT_LABELS.get(fmt, fmt or '')

# Per-user status (collections.status) by type. The CHECK in migration 023
# allows the union; routes check the status matches the item's type.
STATUSES = {
    BOOK: ('read', 'want to read', 'currently reading', 'did not finish'),
    VIDEO: ('watched', 'want to watch'),
    RECORD: ('listened', 'want to listen'),
}

# How each status is shown in menus.
STATUS_LABELS = {
    'read': 'Read', 'want to read': 'Want to Read',
    'currently reading': 'Currently Reading', 'did not finish': 'Did Not Finish',
    'watched': 'Watched', 'want to watch': 'Want to Watch',
    'listened': 'Listened', 'want to listen': 'Want to Listen',
}

# What no status means, shown where you'd pick one (the item page's menu,
# the export). The stored value stays "no row"; the menu's value is
# 'untracked' (collections.add_to_status_collection clears the status).
NO_STATUS_LABEL = {BOOK: 'Unread', VIDEO: 'Unwatched', RECORD: 'Not listened to'}

# The status that sends you to the review page, and that the feed words as
# "finished" ("read" / "watched" / "listened to").
DONE_STATUS = {BOOK: 'read', VIDEO: 'watched', RECORD: 'listened'}

# The status an item gets when it moves from your wishlist onto your shelf.
WANT_STATUS = {BOOK: 'want to read', VIDEO: 'want to watch', RECORD: 'want to listen'}

# Everything a template needs to word a page for one type. Keys are the same
# for every type, so a template can use m.creator without checking the type.
_LABELS = {
    BOOK: {
        'type': BOOK,
        'noun': 'book', 'Noun': 'Book', 'plural': 'books', 'a': 'a',   # a: the article ('an album')
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
        'search_hint': 'Title, author, ISBN or tag',
        'title_search_placeholder': 'Title or author...',
        'no_sessions': 'No reading sessions yet. Click "Add Session" to record when you read this book.',
        'not_owned': 'Read but not owned',
        'description': 'Description',
    },
    VIDEO: {
        'type': VIDEO,
        'noun': 'movie', 'Noun': 'Movie', 'plural': 'movies', 'a': 'a',
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
        'search_hint': 'Title, director or barcode',
        'title_search_placeholder': 'Film title...',
        'no_sessions': 'No viewings yet. Click "Add Session" to record when you watched it.',
        'not_owned': 'Watched but not owned',
        'description': 'Description',
    },
    RECORD: {
        'type': RECORD,
        # The section is "Music" (Phil, 2026-11-08: vinyl, CDs and tapes);
        # one item is an album. Code, URLs and the DB keep "record".
        'noun': 'album', 'Noun': 'Album', 'plural': 'albums', 'a': 'an',
        'creator': 'Artist', 'by': 'by',
        'publisher': 'Label',
        'year': 'Year',
        'code': 'Barcode',
        'length': 'Length',
        'status_label': 'Listen Status',
        'history': 'Listening History',
        'session': 'Listening Session',
        'verb_past': 'listened to',     # "First time listened to"
        'in_progress': 'Listening',
        'info_heading': 'Listening Info',
        'tags_heading': 'Album Tags',
        'about': 'About this Album',
        'shelf': 'music shelf',
        'section': 'Music',
        'search_hint': 'Artist, title, label or cat. no.',
        'title_search_placeholder': 'Artist and title...',
        'no_sessions': 'No listens yet. Click "Add Session" to record when you listened to it.',
        'not_owned': 'Listened to but not owned',
        'description': 'Tracklist and notes',
    },
}


# Blueprint and endpoint suffix per type: the item pages are
# f'{blueprint}.{action}_{item}' (books.show_book, videos.edit_video,
# records.add_record). The tabs ('index', 'shared', 'friends') of the Movies
# and Vinyls sections are in their own blueprints; the Library's are in base.
BLUEPRINTS = {BOOK: 'books', VIDEO: 'videos', RECORD: 'records'}
# The view each section's pages read (migrations 018, 023, 024)
VIEWS = {BOOK: 'library_books', VIDEO: 'library_videos', RECORD: 'library_records'}
ITEMS = {BOOK: 'book', VIDEO: 'video', RECORD: 'record'}
# Each section's own grid (the first crumb on its item pages)
HOMES = {BOOK: 'base.index', VIDEO: 'videos.index', RECORD: 'records.index'}

# The Shelves pages (ROADMAP 11.1): every section in every scope. One
# sidebar entry, then a Books | Movies | Music switch that keeps the scope
# (_shelves.html). 'friend' is one friend's shelf (takes a username); the
# list of friends is the Friends page (friends.index, ROADMAP 11.3).
SHELF_ENDPOINTS = {
    BOOK: {'mine': 'base.index', 'shared': 'base.shared_library', 'friend': 'base.friend_library'},
    VIDEO: {'mine': 'videos.index', 'shared': 'videos.shared', 'friend': 'videos.user_videos'},
    RECORD: {'mine': 'records.index', 'shared': 'records.shared', 'friend': 'records.user_records'},
}
# The switch's labels, in order
SECTION_NAMES = {BOOK: 'Books', VIDEO: 'Movies', RECORD: 'Music'}
# The endpoint -> section map the "last section used" cookie is set from
SHELF_SECTION_OF = {endpoint: kind for kind, scopes in SHELF_ENDPOINTS.items()
                    for endpoint in scopes.values()}

# Code (barcode/ISBN) handling per type. Music got barcodes back on
# 2026-11-08 (ROADMAP 8B.12, Phil) once Discogs could look them up;
# 2026-11-07 to -08 it had none.
HAS_BARCODE = {BOOK: True, VIDEO: True, RECORD: True}


def item_endpoint(media_type, action='show'):
    """'books.show_book', 'videos.edit_video', 'records.add_record', ..."""
    media_type = media_type if media_type in MEDIA_TYPES else BOOK
    return f'{BLUEPRINTS[media_type]}.{action}_{ITEMS[media_type]}'


# Where to buy something on a wishlist: shop searches, opened in a new tab
# from the item page (_buy_links.html). Plain links, nothing fetched.
# Movies: eBay, with the format so a VHS wish doesn't list Blu-rays.
# Music: the Discogs Marketplace, filtered to the album's format.
_DISCOGS_FORMAT = {'LP': 'Vinyl', 'EP': 'Vinyl', '7in': 'Vinyl', '10in': 'Vinyl', '12in': 'Vinyl',
                   'CD': 'CD', 'Cassette': 'Cassette'}


def buy_links(row):
    """[(shop name, url)] for a books row of any type."""
    kind = media_type_of(row)
    title = (row['title'] or '').strip()
    creator = (row['author'] or '').strip()
    fmt = row['format'] if 'format' in row.keys() else None
    if kind == VIDEO:
        words = f"{title} {fmt or ''}".strip()          # 'Heat VHS', 'Heat DVD'
        return [('eBay', 'https://www.ebay.com/sch/i.html?' + urlencode({'_nkw': words}))]
    if kind == RECORD:
        params = {'q': f'{creator} {title}'.strip()}
        if _DISCOGS_FORMAT.get(fmt):
            params['format'] = _DISCOGS_FORMAT[fmt]
        return [('Discogs', 'https://www.discogs.com/sell/list?' + urlencode(params))]
    words = quote_plus(f'{title} {creator}'.strip())
    return [('ThriftBooks', f'https://www.thriftbooks.com/browse/?b.search={words}'),
            ('Bookshop.org', f'https://bookshop.org/search?keywords={words}')]


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
            'status_labels': STATUS_LABELS, 'done_status': DONE_STATUS[media_type],
            'want_status': WANT_STATUS[media_type],
            'no_status': NO_STATUS_LABEL[media_type],
            'bp': BLUEPRINTS[media_type], 'item': ITEMS[media_type], 'home': HOMES[media_type],
            'formats': FORMATS.get(media_type, ()),
            'has_barcode': HAS_BARCODE[media_type]}


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


def add_prefill(args):
    """An add page's ?title= and ?author= (a miss on Do I have this?, ROADMAP
    13b): the form starts with them filled in. Empty ones are left out."""
    values = {}
    for key in ('title', 'author'):
        value = (args.get(key) or '').strip()[:200]
        if value:
            values[key] = value
    return values
