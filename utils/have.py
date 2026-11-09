"""Do I have this? (ROADMAP 8E): the bookstore and record-store check.

Scan or type a barcode / ISBN, or type a title, and get every item that
answers "do I already have this?" for you:

  - yours, on the shelf;
  - your household's (someone else in your library group owns it);
  - on your wishlist;
  - yours but not owned (read / watched / listened to, never bought);
  - removed from your shelf (had it, it left);
  - someone else's copy you have your own data on (a friend's book you
    reviewed): you've read it, even if no one here owns it.

Each match carries your status and rating, so "no, but you read it and
gave it 4/5" is one look. Same scope rule as book_matching: only your own
items, your household's and things you have data on, never the whole
`books` table.
"""
import re

from models import get_library_members
from utils import media, search
from utils.book_utils import isbn_variants, normalize_isbn

MAX_RESULTS = 20

# The verdict per match, most reassuring first: the page sorts by it and
# the headline uses the best one.
VERDICTS = ('yours', 'household', 'wishlist', 'not_owned', 'removed', 'their_wishlist', 'data_only')


def parse_query(q):
    """('isbn', [variants]) for an ISBN, ('barcode', ean13) for another
    valid UPC/EAN, ('bad_code', digits) for digits that are neither, or
    ('text', q) for anything else."""
    q = (q or '').strip()
    raw = re.sub(r'[\s-]', '', q).upper()
    if re.fullmatch(r'\d{8,14}|\d{9}X', raw):
        kind = media.classify_code(raw)
        if kind == media.BOOK:
            return 'isbn', isbn_variants(_isbn13(raw))
        if kind:
            return 'barcode', media.normalize_barcode(raw)
        return 'bad_code', raw
    return 'text', q


def _isbn13(raw):
    """An ISBN-13 from an ISBN-10 or EAN-13 Bookland code."""
    variants = isbn_variants(raw)
    return next((v for v in variants if len(v) == 13), raw)


def _verdict(row, user_id, members):
    mine = row['added_by'] == user_id
    if row['on_wishlist']:
        return 'wishlist'
    if row['owner_wishlist']:
        return 'their_wishlist'     # a household member wants it: nobody has it
    if row['owned'] and row['removed_at'] is None and row['added_by'] in members:
        return 'yours' if mine else 'household'
    if mine and not row['owned']:
        return 'not_owned'
    if mine and row['removed_at'] is not None:
        return 'removed'
    return 'data_only'          # a household member's off-shelf copy, or a friend's you have data on


def find(conn, user_id, q):
    """{'kind', 'query', 'matches': [row dicts with 'verdict'], 'best'}."""
    kind, value = parse_query(q)
    result = {'kind': kind, 'value': value, 'query': (q or '').strip(), 'matches': [], 'best': None}
    if kind == 'bad_code' or not result['query']:
        return result
    if kind == 'text' and len(value) < 2:
        return result

    members = get_library_members(user_id)
    marks = ','.join('?' * len(members))
    if kind == 'isbn':
        vmarks = ','.join('?' * len(value))
        match_sql = f"REPLACE(REPLACE(UPPER(b.isbn), '-', ''), ' ', '') IN ({vmarks})"
        match_params = [normalize_isbn(v) for v in value]
    elif kind == 'barcode':
        match_sql, match_params = "b.barcode = ?", [value]
    else:
        # Every word, accents and punctuation ignored (utils/search.py)
        match_sql, match_params = search.match(value, ['title', 'subtitle', 'author'])
        match_sql = f"({match_sql})"

    rows = conn.execute(f"""
        SELECT b.id, b.title, b.author, b.media_type, b.format, b.cover_image_url,
               b.owned, b.removed_at, b.added_by, b.isbn, b.barcode,
               u.username AS owner,
               EXISTS (SELECT 1 FROM wishlist w WHERE w.book_id = b.id AND w.user_id = ?) AS on_wishlist,
               EXISTS (SELECT 1 FROM wishlist w WHERE w.book_id = b.id AND w.user_id = b.added_by) AS owner_wishlist,
               (SELECT status FROM collections c WHERE c.book_id = b.id AND c.user_id = ?) AS status,
               (SELECT rating FROM read_data r WHERE r.book_id = b.id AND r.user_id = ?) AS rating,
               (SELECT COUNT(*) FROM reading_sessions s
                 WHERE s.book_id = b.id AND s.user_id = ? AND s.date_completed IS NOT NULL) AS times_done
        FROM books b LEFT JOIN users u ON u.id = b.added_by
        WHERE ({match_sql})
          AND (b.added_by IN ({marks})
               OR EXISTS (SELECT 1 FROM wishlist w WHERE w.book_id = b.id AND w.user_id = ?)
               OR EXISTS (SELECT 1 FROM collections c WHERE c.book_id = b.id AND c.user_id = ?)
               OR EXISTS (SELECT 1 FROM read_data r WHERE r.book_id = b.id AND r.user_id = ?))
        LIMIT {MAX_RESULTS * 3}
    """, [user_id] * 4 + match_params + members + [user_id] * 3).fetchall()

    matches = []
    for r in rows:
        row = dict(r)
        row['verdict'] = _verdict(row, user_id, members)
        matches.append(row)
    matches.sort(key=lambda r: (VERDICTS.index(r['verdict']), (r['title'] or '').lower()))
    result['matches'] = matches[:MAX_RESULTS]
    result['best'] = matches[0]['verdict'] if matches else None
    return result


def add_links(kind, value):
    """Where to add an item that wasn't found: [(label, url)], the code
    carried along. An ISBN is a book; another barcode could be a movie or
    an album, and only you know which."""
    from flask import url_for
    if kind == 'isbn':
        isbn = next((v for v in value if len(v) == 13), value[0])
        return [('Add to wishlist', url_for('wishlist.add_to_wishlist', type=media.BOOK, isbn=isbn)),
                ('Add to library', url_for('books.add_book', isbn=isbn))]
    if kind == 'barcode':
        return [('Wishlist it as a movie', url_for('wishlist.add_to_wishlist', type=media.VIDEO, barcode=value)),
                ('Wishlist it as an album', url_for('wishlist.add_to_wishlist', type=media.RECORD, barcode=value)),
                ('Add a movie', url_for('videos.add_video', barcode=value)),
                ('Add an album', url_for('records.add_record', barcode=value))]
    return [('Add to wishlist', url_for('wishlist.add_to_wishlist', type=media.BOOK)),
            ('Add to library', url_for('books.add_book'))]
