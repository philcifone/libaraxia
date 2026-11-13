"""Find an existing book record to attach a user's data to.

Adding data by ISBN or by title + author used to search *everyone's* books,
so a match could hang your reading status or wishlist entry on a stranger's
copy, which then never showed in your library (found in ROADMAP Phase 4).
These helpers only ever look at the user's own books and their household's
library, in that order. Anything else means a new book record.

Used by the Goodreads import (`utils/goodreads.py`) and the wishlist add
routes (`blueprints/wishlist.py`); `same_book` and `isbn_matches` are the
same rules for the Add page's duplicate check (`book_utils.find_duplicates`,
ROADMAP 14c).
"""
import re

from models import get_library_members
from utils.book_utils import _normalise, isbn_variants


NAME_SUFFIXES = {'jr', 'sr', 'ii', 'iii', 'iv'}


def _title_part(title):
    """Normalised title. Goodreads appends the series to titles ("Leviathan
    Wakes (The Expanse, #1)"), the APIs don't, so a trailing parenthetical is
    ignored on both sides."""
    return _normalise(re.sub(r'\s*\([^()]*\)\s*$', '', title or ''))


def _author_keys(author):
    """Every form of an author field a match may use: the whole name and each
    co-author's ("Nina Freudenberger, Sadie Stein"), each as its words sorted
    without Jr./Sr./III, so "Kurt Vonnegut Jr." == "Kurt Vonnegut" and
    "Liu Cixin" == "Cixin Liu" (found on Phil's prod copy, ROADMAP 14b)."""
    names = [author or ''] + re.split(r'\s*(?:,|;|&|\band\b)\s*', author or '')
    keys = []
    for name in names:
        words = [w for w in _normalise(name).split() if w not in NAME_SUFFIXES]
        key = ' '.join(sorted(words))
        if key and key not in keys:
            keys.append(key)
    return keys


def _title_keys(title, author):
    """Normalised "title|author" keys, one per form of the author."""
    title = _title_part(title)
    return [f'{title}|{a}' for a in _author_keys(author)] if title else []


def stored_title_forms(title, subtitle=None):
    """The titles a stored book answers to: under the title alone and with
    its subtitle (Goodreads puts the subtitle in the title, "Consider the
    Lobster and Other Essays", "This Is Water: Some Thoughts, ...", the
    lookups split it off), and before a colon, for a title stored with its
    subtitle in it ("Invisible Monsters: A Novel")."""
    titles = [title]
    if subtitle:
        titles.append(f"{title} {subtitle}")
    if ':' in (title or ''):
        titles.append(title.split(':', 1)[0])
    return titles


def wanted_title_forms(title):
    """The titles to look for: the whole title (which also finds a book
    stored as title + subtitle), then the part before a colon, for a book
    stored without its subtitle."""
    candidates = [title]
    if ':' in (title or ''):
        candidates.append(title.split(':', 1)[0])
    return candidates


def same_book(stored, title, author='', subtitle=''):
    """Whether a stored book (a row with title, author, subtitle) is the one
    described by title / author / subtitle, by the 14b rules above: subtitle
    and colon forms, a trailing series ignored, Jr. and name order and
    co-authors. With no author on either side the title alone decides (the
    Add page's duplicate check, which asks before a typed author exists)."""
    stored_titles = stored_title_forms(stored['title'], _get(stored, 'subtitle'))
    wanted = wanted_title_forms(title)
    if subtitle:
        wanted.insert(1, f"{title} {subtitle}")
    if not _author_keys(author) or not _author_keys(stored['author']):
        have = {_title_part(t) for t in stored_titles} - {''}
        return any(_title_part(t) in have for t in wanted)
    have = {k for t in stored_titles for k in _title_keys(t, stored['author'])}
    return any(k in have for t in wanted for k in _title_keys(t, author))


def _get(row, key):
    """row[key] for a dict or sqlite3.Row that may not have the column."""
    try:
        return row[key]
    except (KeyError, IndexError):
        return None


def isbn_matches(a, b):
    """Two ISBNs name the same book in any of their 10/13 forms."""
    return bool(set(_isbn_keys(a)) & set(_isbn_keys(b)))


def _isbn_keys(*isbns):
    """Every ISBN-10/13 form of the given ISBNs, normalised."""
    keys = []
    for isbn in isbns:
        for variant in isbn_variants(isbn or ''):
            if variant not in keys:
                keys.append(variant)
    return keys


class BookIndex:
    """The user's own books and their household's library, indexed by ISBN
    and by title + author, loaded once so a whole import is one query.

    `match()` returns `(book, whose)` where whose is 'own' or 'household',
    or `(None, None)`. Your own books win over the household's, and books
    still on the shelf win over removed ones. Call `add()` after creating a
    book so later rows in the same import find it.
    """

    # lower number = preferred
    _RANK = {('own', False): 0, ('own', True): 1, ('household', False): 2, ('household', True): 3}

    def __init__(self, conn, user_id):
        self.user_id = user_id
        self._by_isbn = {}
        self._by_title = {}
        # Every indexed book by id: the Goodreads import's Book Id memory may
        # only point at a book this index could have matched (ROADMAP 14b)
        self.by_id = {}
        # The caller's connection, so the index works outside a request too
        members = [m for m in get_library_members(user_id, conn) if m != user_id]
        marks = ','.join('?' * len(members)) or 'NULL'
        # Own books: everything you added, wishlist entries included (the
        # caller decides what a wishlist entry means). Household: only books
        # on their shelf, never their wishlist entries.
        rows = conn.execute(f'''
            SELECT b.*, 'own' AS whose,
                   EXISTS (SELECT 1 FROM wishlist w
                           WHERE w.book_id = b.id AND w.user_id = b.added_by) AS is_wishlist_entry
            FROM books b WHERE b.added_by = ? AND b.media_type = 'book'
            UNION ALL
            SELECT lb.*, 'household', 0 FROM library_books lb WHERE lb.added_by IN ({marks})
        ''', [user_id, *members]).fetchall()
        for row in rows:
            self.add(row)

    def add(self, book):
        """Index a book row (needs id, isbn, title, author, removed_at, whose,
        is_wishlist_entry; subtitle if it has one)."""
        book = dict(book)
        self.by_id[book['id']] = book
        rank = self._RANK[(book['whose'], book['removed_at'] is not None)]
        keys = [(self._by_isbn, k) for k in _isbn_keys(book['isbn'])]
        for title in stored_title_forms(book['title'], book.get('subtitle')):
            keys += [(self._by_title, k) for k in _title_keys(title, book['author'])]
        for table, key in keys:
            current = table.get(key)
            if current is None or rank < current[0]:
                table[key] = (rank, book)

    def match(self, isbns=(), title='', author=''):
        """ISBN first (any form of any ISBN given), then title + author."""
        hits = [self._by_isbn[k] for k in _isbn_keys(*isbns) if k in self._by_isbn]
        for candidate in wanted_title_forms(title):
            if hits:
                break
            hits = [self._by_title[k] for k in _title_keys(candidate, author) if k in self._by_title]
        if not hits:
            return None, None
        _, book = min(hits, key=lambda hit: hit[0])
        return book, book['whose']


def own_book_for_wishlist(conn, user_id, isbn):
    """For the wishlist add routes: the user's own book with this ISBN, if any.

    Returns `(book_id, kind)` with kind 'wishlist' (already on your wishlist),
    'library' (on your shelf: wishlisting it would hide it from your library,
    since a wishlist entry is a book you added plus a wishlist row) or
    `(None, None)`, meaning create a new book. Other people's books, even the
    household's, are never reused for a wishlist entry: "Move to library"
    would then not make the book yours.
    """
    keys = _isbn_keys(isbn)
    if not keys:
        return None, None
    rows = conn.execute('''
        SELECT b.id, b.isbn, b.removed_at, b.owned,
               EXISTS (SELECT 1 FROM wishlist w WHERE w.book_id = b.id AND w.user_id = ?) AS wished
        FROM books b WHERE b.added_by = ? AND b.media_type = 'book'
          AND b.isbn IS NOT NULL AND b.isbn != ''
    ''', (user_id, user_id)).fetchall()
    for row in rows:
        if set(_isbn_keys(row['isbn'])) & set(keys):
            if row['wished']:
                return row['id'], 'wishlist'
            if row['owned'] and row['removed_at'] is None:
                return row['id'], 'library'
    return None, None


def _book_keys(book):
    """Every key a shelf book answers to: its ISBN forms, then title + author
    for each title form (the index's rules, without its ranking)."""
    keys = {('isbn', k) for k in _isbn_keys(book['isbn'])}
    for title in stored_title_forms(book['title'], _get(book, 'subtitle')):
        keys |= {('title', k) for k in _title_keys(title, book['author'])}
    return keys


def books_in_common(conn, user_id, other_id):
    """How many books on `user_id`'s shelf are also on `other_id`'s (16.0,
    the profile's "friend at a glance"). Books only, on the shelf on both
    sides (owned, not removed: book_utils.on_shelf), never a wishlist entry;
    each user's own copies only, not their household's. Two copies are the
    same book by ISBN, or by title and author as BookIndex matches them.
    Counted on the caller's side: two of your editions of one book that
    they own count twice. The caller checks they may see each other."""
    from utils.book_utils import on_shelf

    def shelf(uid):
        # library_books leaves out the owner's wishlist entries
        return conn.execute(
            f'SELECT * FROM library_books b WHERE b.added_by = ? AND {on_shelf("b")}',
            (uid,)).fetchall()

    theirs = set()
    for book in shelf(other_id):
        theirs |= _book_keys(book)
    return sum(1 for book in shelf(user_id) if _book_keys(book) & theirs)
