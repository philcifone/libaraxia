"""The Reviews section (ROADMAP 13): your reviews, your friends' reviews and
what you finished but haven't reviewed yet, one media type at a time, plus
the [+ Review] search over the items you may review.

A review is a `read_data` row (a rating, a written review, or both). There is
no timestamp on read_data, so "newest first" is the latest finished date of
the reviewer's sessions on the item, then the order the reviews were first
written in (rowid; an edit keeps it). Marking something finished opens the
review page with today's date filled in (ROADMAP 12.3), so a fresh review
usually has a fresh date.

Who sees what follows the access model (CLAUDE.md): friends' reviews come
from `models.friend_ids` only, so a household member who isn't also a friend
never shows up here, the same as on profiles and the feed.
"""
from flask import url_for

from models import friend_ids, get_library_members
from utils import media
from utils.search import match as search_match
from utils.shelves import COVERS_PER_ROW

# The three lists, in page order. Keys are the URL's <which>.
LISTS = ('mine', 'friends', 'unreviewed')
LIST_LABELS = {
    'mine': 'Your reviews',
    'friends': "Friends' reviews",
    'unreviewed': 'Finished, not reviewed yet',
}
LIST_EMPTY = {
    'mine': 'Nothing reviewed yet. The + button finds something to review.',
    'friends': 'No reviews from your friends yet.',
    'unreviewed': 'All caught up: everything you finished has a review.',
}

# One review row, with what the cards and the grids need. `finished` is the
# reviewer's latest finished date on the item (NULL if they logged none).
_REVIEW_SELECT = '''
    SELECT b.id, b.title, b.author, b.cover_image_url, b.media_type, b.format,
           rd.rating, rd.comment, u.username,
           (SELECT MAX(s.date_completed) FROM reading_sessions s
             WHERE s.user_id = rd.user_id AND s.book_id = rd.book_id) AS finished
    FROM read_data rd
    JOIN books b ON b.id = rd.book_id
    JOIN users u ON u.id = rd.user_id
'''
_REVIEW_ORDER = ' ORDER BY finished IS NULL, finished DESC, rd.rowid DESC'


def _limit(limit):
    return f' LIMIT {int(limit)}' if limit else ''


def reviews_by(conn, user_ids, media_type, limit=None):
    """Reviews written by any of `user_ids` on items of `media_type`, newest
    first. Callers pass ids the viewer may see (themselves, or friends)."""
    if not user_ids:
        return []
    marks = ','.join('?' * len(user_ids))
    return conn.execute(
        _REVIEW_SELECT + f' WHERE rd.user_id IN ({marks}) AND b.media_type = ?'
        + _REVIEW_ORDER + _limit(limit),
        (*user_ids, media_type)).fetchall()


def unreviewed(conn, user_id, media_type, limit=None):
    """Items you marked finished (read / watched / listened) and haven't
    rated or reviewed, most recently finished first."""
    return conn.execute('''
        SELECT b.id, b.title, b.author, b.cover_image_url, b.media_type, b.format,
               NULL AS rating, NULL AS comment, NULL AS username,
               (SELECT MAX(s.date_completed) FROM reading_sessions s
                 WHERE s.user_id = c.user_id AND s.book_id = c.book_id) AS finished
        FROM collections c JOIN books b ON b.id = c.book_id
        WHERE c.user_id = ? AND c.status = ? AND b.media_type = ?
          AND NOT EXISTS (SELECT 1 FROM read_data rd
                          WHERE rd.user_id = c.user_id AND rd.book_id = c.book_id)
        ORDER BY c.updated_at DESC, c.collection_id DESC
    ''' + _limit(limit), (user_id, media.DONE_STATUS[media_type], media_type)).fetchall()


def list_rows(conn, user_id, media_type, which, limit=None, friend_id=None):
    """The rows of one list ('mine', 'friends' or 'unreviewed'). friend_id
    narrows 'friends' to one friend (a friend's profile, "View all"); the
    caller checks they are a friend."""
    if which == 'mine':
        return reviews_by(conn, [user_id], media_type, limit)
    if which == 'friends':
        ids = [friend_id] if friend_id else friend_ids(conn, user_id)
        return reviews_by(conn, ids, media_type, limit)
    return unreviewed(conn, user_id, media_type, limit)


def _count(conn, user_id, media_type, which):
    if which == 'unreviewed':
        return conn.execute('''
            SELECT COUNT(*) FROM collections c JOIN books b ON b.id = c.book_id
            WHERE c.user_id = ? AND c.status = ? AND b.media_type = ?
              AND NOT EXISTS (SELECT 1 FROM read_data rd
                              WHERE rd.user_id = c.user_id AND rd.book_id = c.book_id)
        ''', (user_id, media.DONE_STATUS[media_type], media_type)).fetchone()[0]
    ids = [user_id] if which == 'mine' else friend_ids(conn, user_id)
    if not ids:
        return 0
    marks = ','.join('?' * len(ids))
    return conn.execute(f'''
        SELECT COUNT(*) FROM read_data rd JOIN books b ON b.id = rd.book_id
        WHERE rd.user_id IN ({marks}) AND b.media_type = ?
    ''', (*ids, media_type)).fetchone()[0]


def shelves(conn, user_id, media_type):
    """The section's three rows as `_shelf_rows.html` dicts. Covers carry
    `rating` (stars under the cover) and, on friends' row, `by`."""
    out = []
    for which in LISTS:
        rows = list_rows(conn, user_id, media_type, which, COVERS_PER_ROW)
        out.append({
            'key': which,
            'label': LIST_LABELS[which],
            'url': url_for('reviews.see_all', which=which, type=media_type),
            'more': 'See all',
            'empty': LIST_EMPTY[which],
            'count': _count(conn, user_id, media_type, which),
            'covers': [{
                'cover_image_url': r['cover_image_url'], 'title': r['title'], 'named': True,
                'rating': r['rating'] if which != 'unreviewed' else None,
                'stars': which != 'unreviewed',
                'by': r['username'] if which == 'friends' else None,
            } for r in rows],
        })
    return out


def section_counts(conn, user_id):
    """{media_type: reviews you wrote + friends' + waiting} for the tabs."""
    return {t: sum(_count(conn, user_id, t, w) for w in LISTS) for t in media.MEDIA_TYPES}


# --- [+ Review]: what you may review --------------------------------------

FIND_LIMIT = 50


def find(conn, user_id, media_type, term):
    """Items of `media_type` matching `term` that the [+ Review] search
    offers: everything of yours in the section's view (on the shelf, not
    owned or removed; never your wishlist entries, which `library_*` leave
    out) and your household's. Never anyone else's rows, as in
    utils/book_matching.py. Your own come first, then by title.

    An empty term finds nothing: the page asks for a search first."""
    if not (term or '').strip():
        return []
    view = media.VIEWS[media_type]     # one of ours, never request input
    members = get_library_members(user_id)
    marks = ','.join('?' * len(members))
    cond, params = search_match(term, ('title', 'author', 'subtitle', 'isbn', 'barcode'),
                                user_id, alias='b')
    return conn.execute(f'''
        SELECT b.id, b.title, b.author, b.cover_image_url, b.media_type, b.format,
               b.owned, b.removed_at, b.added_by, u.username AS owner,
               rd.rating AS my_rating, (rd.user_id IS NOT NULL) AS reviewed
        FROM {view} b
        LEFT JOIN users u ON u.id = b.added_by
        LEFT JOIN read_data rd ON rd.book_id = b.id AND rd.user_id = ?
        WHERE b.added_by IN ({marks}) AND {cond}
        ORDER BY (b.added_by = ?) DESC, b.title COLLATE NOCASE, b.id
        LIMIT {FIND_LIMIT}
    ''', (user_id, *members, *params, user_id)).fetchall()


def then_review_values(args):
    """The add page's pre-fill from Reviews' "Add it as not owned" link
    (?not_owned=1&then=review&title=...): "I don't own this" ticked, the
    search as the title, and `then` carried in the form so saving lands on
    the review page. Any other request gets nothing extra."""
    if args.get('then') != 'review':
        return {}
    return {'then': 'review',
            'not_owned': args.get('not_owned') == '1',
            'title': (args.get('title') or '').strip()[:200]}
