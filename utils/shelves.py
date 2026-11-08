"""Shelf rows: a titled card with a count and a side-scrolling row of covers
(ROADMAP 8C/8D). The Collections page, the profile's status shelves and the
profile's wishlist all draw them with `_shelf_rows.html`, from the dicts
built here:

    {'label': 'Want to Watch', 'url': '/collections/status/want to watch',
     'count': 12, 'covers': [{'cover_image_url': ..., 'title': ...}, ...]}

Every query is for one user and one media type. Status shelves include
not-owned items on purpose (a status is about reading, not owning); the
wishlist rows are wishlist entries only.
"""
from flask import url_for

from utils import media

COVERS_PER_ROW = 12
# Tab and row names: the sections' own names, except the Library's books
SECTION_NAMES = {media.BOOK: 'Books', media.VIDEO: 'Movies', media.RECORD: 'Music'}


def _covers(conn, sql, params):
    return [dict(r) for r in conn.execute(sql + f' LIMIT {COVERS_PER_ROW}', params).fetchall()]


def status_shelves(conn, user_id, media_type, username=None, keep_empty=True):
    """One shelf per status of `media_type` (media.STATUSES order).
    `username` goes on the links when it's someone else's profile."""
    counts = dict(conn.execute('''
        SELECT c.status, COUNT(*) FROM collections c JOIN books b ON b.id = c.book_id
        WHERE c.user_id = ? AND b.media_type = ? GROUP BY c.status
    ''', (user_id, media_type)).fetchall())
    shelves = []
    for status in media.STATUSES[media_type]:
        count = counts.get(status, 0)
        if not count and not keep_empty:
            continue
        shelves.append({
            'label': media.STATUS_LABELS[status],
            'url': url_for('collections.view_by_status', status=status,
                           **({'username': username} if username else {})),
            'count': count,
            'covers': _covers(conn, '''
                SELECT b.cover_image_url, b.title FROM collections c JOIN books b ON b.id = c.book_id
                WHERE c.user_id = ? AND c.status = ? AND b.media_type = ?
                ORDER BY c.updated_at DESC, c.collection_id DESC
            ''', (user_id, status, media_type)) if count else [],
        })
    return shelves


def custom_shelves(conn, user_id, media_type):
    """The user's custom shelves of one section, oldest first, each with
    'id' and 'name' as well (for the delete button)."""
    rows = conn.execute('''
        SELECT uc.collection_id, uc.name, COUNT(cb.book_id) AS n
        FROM user_collections uc LEFT JOIN collection_books cb ON cb.collection_id = uc.collection_id
        WHERE uc.user_id = ? AND uc.media_type = ?
        GROUP BY uc.collection_id ORDER BY uc.created_at, uc.collection_id
    ''', (user_id, media_type)).fetchall()
    return [{
        'id': r['collection_id'], 'name': r['name'], 'label': r['name'], 'count': r['n'],
        'url': url_for('collections.view_custom_collection', collection_id=r['collection_id']),
        'covers': _covers(conn, '''
            SELECT b.cover_image_url, b.title FROM collection_books cb JOIN books b ON b.id = cb.book_id
            WHERE cb.collection_id = ? ORDER BY cb.added_at DESC
        ''', (r['collection_id'],)) if r['n'] else [],
    } for r in rows]


def section_counts(conn, user_id):
    """{media_type: number of statuses + custom shelf items} for the tabs."""
    counts = {t: 0 for t in media.MEDIA_TYPES}
    for t, n in conn.execute('''
        SELECT b.media_type, COUNT(*) FROM collections c JOIN books b ON b.id = c.book_id
        WHERE c.user_id = ? GROUP BY b.media_type
    ''', (user_id,)).fetchall():
        counts[t] = counts.get(t, 0) + n
    return counts


def wishlist_shelves(conn, user_id, username=None):
    """One row per section that has wishlist entries (8D), linked to the
    wishlist page on that section's tab (yours) or to the friend's wishlist."""
    shelves = []
    from blueprints.wishlist import WISHLIST_TABS         # ?show= per type
    for media_type, show in WISHLIST_TABS.items():
        count = conn.execute('''
            SELECT COUNT(*) FROM wishlist w JOIN books b ON b.id = w.book_id
            WHERE w.user_id = ? AND b.media_type = ?
        ''', (user_id, media_type)).fetchone()[0]
        if not count:
            continue
        if username:
            url = url_for('wishlist.view_user_wishlist', username=username)
        else:
            url = url_for('wishlist.view_wishlist', show=show)
        shelves.append({
            'label': SECTION_NAMES[media_type],
            'url': url, 'count': count,
            'covers': _covers(conn, '''
                SELECT b.cover_image_url, b.title FROM wishlist w JOIN books b ON b.id = w.book_id
                WHERE w.user_id = ? AND b.media_type = ? ORDER BY w.added_at DESC
            ''', (user_id, media_type)),
        })
    return shelves
