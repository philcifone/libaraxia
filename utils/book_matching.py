"""Find an existing book record to attach a user's data to.

Adding data by ISBN or by title + author used to search *everyone's* books,
so a match could hang your reading status or wishlist entry on a stranger's
copy, which then never showed in your library (found in ROADMAP Phase 4).
These helpers only ever look at the user's own books and their household's
library, in that order. Anything else means a new book record.

Used by the Goodreads import (`utils/goodreads.py`) and the wishlist add
routes (`blueprints/wishlist.py`).
"""
import re

from models import get_library_members
from utils.book_utils import _normalise, isbn_variants


def _title_key(title, author):
    """Normalised "title|author" key. Goodreads appends the series to titles
    ("Leviathan Wakes (The Expanse, #1)"), the APIs don't, so a trailing
    parenthetical is ignored on both sides."""
    title = re.sub(r'\s*\([^()]*\)\s*$', '', title or '')
    title, author = _normalise(title), _normalise(author)
    return f'{title}|{author}' if title and author else None


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
        members = [m for m in get_library_members(user_id) if m != user_id]
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
        is_wishlist_entry)."""
        book = dict(book)
        rank = self._RANK[(book['whose'], book['removed_at'] is not None)]
        keys = [(self._by_isbn, k) for k in _isbn_keys(book['isbn'])]
        title_key = _title_key(book['title'], book['author'])
        if title_key:
            keys.append((self._by_title, title_key))
        for table, key in keys:
            current = table.get(key)
            if current is None or rank < current[0]:
                table[key] = (rank, book)

    def match(self, isbns=(), title='', author=''):
        """ISBN first (any form of any ISBN given), then title + author."""
        hits = [self._by_isbn[k] for k in _isbn_keys(*isbns) if k in self._by_isbn]
        if not hits:
            key = _title_key(title, author)
            if key and key in self._by_title:
                hits = [self._by_title[key]]
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
