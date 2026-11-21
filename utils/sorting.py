"""Sort orders for the grids (ROADMAP 11.4).

One place for what every grid can be sorted by, so the Library, Household,
search, Movies, Music and collection pages agree. The sort menu is
templates/_view_bar.html; keep its options in step with SORTS.

Every order:
  - puts items with no value last, ascending or descending (NULLS LAST,
    SQLite 3.30+), so "Date read, newest first" starts with what you read
    and the unread pile follows;
  - breaks ties by title, then id, so infinite scroll (LIMIT/OFFSET over the
    same query) never repeats or skips an item between pages.

"Date read" and "Your rating" are the viewer's own data, also on the
household and friends' pages, like the list view's status and rating.
"""
from flask import request

from utils import media

# Key -> SQL expression over `b` (a books row or one of its views). The keys
# are what the sort menu sends; the expressions are ours, never request input.
# A `?` in an expression is the viewer's id.
SORTS = {
    'title': "NULLIF(TRIM(b.title), '') COLLATE NOCASE",
    'author': "NULLIF(TRIM(b.author), '') COLLATE NOCASE",
    'publish_year': 'b.publish_year',
    'created_at': 'b.created_at',
    'runtime_minutes': 'NULLIF(b.runtime_minutes, 0)',
    # An audiobook's page count (if a lookup filled one in) isn't its length
    'page_count': f"CASE WHEN b.format = '{media.AUDIOBOOK}' THEN NULL ELSE NULLIF(b.page_count, 0) END",
    # Your latest finished session; dates are stored as YYYY-MM-DD
    'finished': ('(SELECT MAX(s.date_completed) FROM reading_sessions s'
                 ' WHERE s.book_id = b.id AND s.user_id = ?)'),
    'rating': '(SELECT r.rating FROM read_data r WHERE r.book_id = b.id AND r.user_id = ?)',
}

# What each section offers, in menu order
BY_TYPE = {
    media.BOOK: ('title', 'author', 'publish_year', 'created_at', 'finished', 'rating', 'page_count'),
    media.VIDEO: ('title', 'author', 'publish_year', 'created_at', 'finished', 'rating', 'runtime_minutes'),
    media.RECORD: ('title', 'author', 'publish_year', 'created_at', 'finished', 'rating', 'runtime_minutes'),
}


def choice(args=None, media_type=media.BOOK, default='title', default_order='asc'):
    """The (sort_by, sort_order) asked for in `args` (the query string),
    falling back to the defaults for anything this section doesn't offer."""
    args = request.args if args is None else args
    allowed = BY_TYPE.get(media_type, BY_TYPE[media.BOOK])
    sort_by = args.get('sort_by', default)
    sort_by = sort_by if sort_by in allowed else default
    order = args.get('sort_order', default_order)
    order = order if order in ('asc', 'desc') else default_order
    return sort_by, order


def remembered(conn, user_id, args=None, media_type=media.BOOK, save=True):
    """choice() for a shelf grid, with the user's last sort for this media
    type standing in for a URL that doesn't name one (migration 048; Phil,
    2026-11-21: Back or a link shouldn't undo the sort).

    A URL with ?sort_by= is a choice: it's used and, with `save`, kept as the
    new preference. Saving on a GET is deliberate: this is a view setting,
    like the shelf_section cookie, and the worst a forged link can do is
    re-sort your grid. Bulk edit's view_ids reads without saving."""
    args = request.args if args is None else args
    row = conn.execute('SELECT sort_by, sort_order FROM sort_preferences'
                       ' WHERE user_id = ? AND media_type = ?', (user_id, media_type)).fetchone()
    stored = tuple(row) if row else None
    if 'sort_by' not in args:
        # Through choice(), so a stored key this section no longer offers falls back
        return choice({'sort_by': stored[0], 'sort_order': stored[1]} if stored else {}, media_type)
    picked = choice(args, media_type)
    # Only a change is written: infinite scroll asks the same URL page after page
    if save and picked != stored:
        conn.execute(
            'INSERT INTO sort_preferences (user_id, media_type, sort_by, sort_order)'
            ' VALUES (?, ?, ?, ?) ON CONFLICT (user_id, media_type) DO UPDATE SET'
            ' sort_by = excluded.sort_by, sort_order = excluded.sort_order',
            (user_id, media_type, *picked))
        conn.commit()
    return picked


def order_by(sort_by, sort_order, viewer_id):
    """' ORDER BY ...' and its parameters for a choice() result."""
    expr = SORTS[sort_by]
    direction = 'DESC' if sort_order == 'desc' else 'ASC'
    params = [viewer_id] * expr.count('?')
    tiebreak = '' if sort_by == 'title' else f", {SORTS['title']} ASC"
    return f' ORDER BY {expr} {direction} NULLS LAST{tiebreak}, b.id ASC', params
