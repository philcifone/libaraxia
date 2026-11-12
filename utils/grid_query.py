"""The ids a grid shows (ROADMAP 14a step 1).

Bulk edit's "select all 57 in this view" must name exactly the items the grid
page renders, in the same order, so the grids and the selection share one
query rather than two that drift apart.

  books_query    the Books grid's WHERE (base.library_page builds the page from it)
  search_query   Search's WHERE (books.search), which differs a little: see there
  view_ids       every id of a whitelisted grid view, all pages, for a selection

Movies and Music already have one implementation, Section.filtered, so
view_ids calls that instead of copying it.

Takes the caller's connection and needs no app context, so tests and scripts
can call it. The connection must have fold() registered (get_db() and
get_db_connection() both do).
"""
from urllib.parse import parse_qsl

from werkzeug.datastructures import MultiDict

from utils import households, media, search, sorting
from utils.book_utils import shelf_filter, format_filter

# The views a selection may name: section, then whose shelf. Friends' grids
# are read-only, so they are deliberately not here.
SCOPES = ('mine', 'household')
VIEWS = {f'{kind}:{scope}': (kind, scope) for kind in (media.BOOK, media.VIDEO, media.RECORD)
         for scope in SCOPES}
VIEWS['book:search'] = (media.BOOK, 'search')     # Search pages too (step 7)


def from_goodreads(args, viewer_id):
    """SQL fragment and params for ?from=goodreads (ROADMAP 14b): books an
    import of the viewer's matched or wrote, not undone. Always the viewer's
    own provenance, never the shelf owner's, so a friend's grid can't show
    what their import touched."""
    if args.get('from') != 'goodreads' or viewer_id is None:
        return '', []
    return (' AND EXISTS (SELECT 1 FROM goodreads_rows gr JOIN goodreads_imports gi ON gi.id = gr.import_id'
            ' WHERE gr.book_id = b.id AND gi.user_id = ? AND gi.undone_at IS NULL)'), [viewer_id]


def books_query(owner_ids, args, data_user, viewer_id=None):
    """(SQL, params) for the Books grid: books on the shelves of `owner_ids`,
    narrowed by the search and filters in `args` (the query string).

    No ORDER BY or paging: the caller adds the sort (utils/sorting.py) and
    its LIMIT. `data_user` is whose statuses, ratings and tags the status,
    rating and tag filters and the search's tag matching use (the entries in
    view: you on your own and the household's shelves, the friend on theirs).
    `viewer_id` is who is looking (From Goodreads is always theirs); it
    defaults to `data_user`.
    """
    marks = ','.join('?' * len(owner_ids))
    query = f'SELECT b.* FROM library_books b WHERE b.added_by IN ({marks})'
    params = list(owner_ids)

    # Only what's on the shelf unless Show asks for not-owned or removed ones
    query += shelf_filter(args)

    term = (args.get('search_term') or '').strip()
    if term:
        match_sql, match_params = search.match(term, ['title', 'subtitle', 'author', 'publisher', 'isbn',
                                                      'publish_year'], viewer_id=data_user)
        query += f' AND ({match_sql})'
        params += match_params
    if args.get('genre'):
        query += " AND LOWER(b.genre) = LOWER(?)"
        params.append(args.get('genre'))
    # Book / Audiobook (8B.2)
    fmt_sql, fmt_params = format_filter(args.get('format'))
    query += fmt_sql
    params.extend(fmt_params)
    if args.get('read_status'):
        query += " AND EXISTS (SELECT 1 FROM collections c WHERE c.book_id = b.id AND c.user_id = ? AND c.status = ?)"
        params.extend([data_user, args.get('read_status')])
    rating = args.get('rating', type=int)
    if rating:
        query += " AND EXISTS (SELECT 1 FROM read_data r WHERE r.book_id = b.id AND r.user_id = ? AND r.rating >= ?)"
        params.extend([data_user, rating])
    tags = [t for t in args.getlist('tags[]') if t]
    if tags:
        tag_marks = ','.join('?' * len(tags))
        query += (" AND EXISTS (SELECT 1 FROM book_tags t WHERE t.book_id = b.id"
                  f" AND t.user_id = ? AND t.tag_name IN ({tag_marks}))")
        params += [data_user, *tags]
    gr_sql, gr_params = from_goodreads(args, data_user if viewer_id is None else viewer_id)
    return query + gr_sql, params + gr_params


def search_query(conn, member_ids, args, viewer_id):
    """(SQL, params) for Search (books.search): your household's books
    matching ?search_term=, narrowed by the filters. No ORDER BY or paging.

    Kept as Search has always behaved, which is not quite books_query: the
    term doesn't look at the publisher, and tags you don't have are dropped
    from the tag filter (so only unknown tags means no tag filter). Making
    Search match the grid it came from is a ROADMAP loose end."""
    term = (args.get('search_term') or '').strip()
    # Every word, accents and punctuation ignored, in any of these or your
    # tags on the book (utils/search.py, ROADMAP 7.2b)
    match_sql, match_params = search.match(term, ['title', 'subtitle', 'author', 'isbn', 'publish_year'],
                                           viewer_id=viewer_id)
    marks = ','.join('?' * len(member_ids))
    query = f'SELECT b.* FROM library_books b WHERE b.added_by IN ({marks}) AND ({match_sql})'
    params = [*member_ids, *match_params]

    # Removed (deaccessioned) books are hidden unless asked for
    query += shelf_filter(args)
    if args.get('genre'):
        query += ' AND LOWER(b.genre) = LOWER(?)'
        params.append(args.get('genre'))
    # Book / Audiobook (8B.2)
    fmt_sql, fmt_params = format_filter(args.get('format'))
    query += fmt_sql
    params.extend(fmt_params)
    if args.get('read_status'):
        query += ' AND EXISTS (SELECT 1 FROM collections c WHERE c.book_id = b.id AND c.user_id = ? AND c.status = ?)'
        params.extend([viewer_id, args.get('read_status')])
    rating = args.get('rating', type=int)
    if rating:
        query += ' AND EXISTS (SELECT 1 FROM read_data r WHERE r.book_id = b.id AND r.user_id = ? AND r.rating >= ?)'
        params.extend([viewer_id, rating])
    tags = args.getlist('tags[]')
    if tags:
        known = {row['tag_name'] for row in conn.execute(
            'SELECT DISTINCT tag_name FROM book_tags WHERE user_id = ?', (viewer_id,))}
        wanted = [tag for tag in tags if tag in known]
        if wanted:
            tag_marks = ','.join('?' * len(wanted))
            query += (' AND EXISTS (SELECT 1 FROM book_tags t WHERE t.book_id = b.id'
                      f' AND t.user_id = ? AND t.tag_name IN ({tag_marks}))')
            params += [viewer_id, *wanted]
    gr_sql, gr_params = from_goodreads(args, viewer_id)
    return query + gr_sql, params + gr_params, match_sql, match_params


def _args(args):
    """The query string as the MultiDict request.args is: the browser sends
    it as text, tests and the grids pass the MultiDict itself."""
    if isinstance(args, MultiDict):
        return args
    return MultiDict(parse_qsl(args or '', keep_blank_values=True))


def _section(kind):
    # Imported here: the blueprints import utils, not the other way round
    if kind == media.VIDEO:
        from blueprints.videos import VIDEOS
        return VIDEOS
    from blueprints.records import RECORDS
    return RECORDS


def view_ids(conn, user, view, args):
    """The ids a grid shows for `user`, in grid order and across every page.

    `view` is a key of VIEWS ('book:mine', 'video:household', ...); anything
    else raises ValueError. `args` is the grid's query string (text or a
    MultiDict; page and per_page are ignored). `user` needs an `id`. The
    household views honour ?member= as the pages do. Statuses, ratings and
    tags are the user's own, as on those pages.
    """
    if view not in VIEWS:
        raise ValueError(f'Unknown view: {view!r}')
    kind, scope = VIEWS[view]
    args = _args(args)

    if scope == 'household':
        _, owner_ids, _ = households.member_choice(conn, user.id, args.getlist('member', type=int))
    else:
        owner_ids = [user.id]

    if scope == 'search':
        from models import get_library_members        # models imports utils; keep this one-way at import
        query, params, _, _ = search_query(conn, get_library_members(user.id, conn), args, user.id)
        sort_by, sort_order = sorting.choice(args, media.BOOK)
        order_sql, order_params = sorting.order_by(sort_by, sort_order, user.id)
        rows = conn.execute(query + order_sql, [*params, *order_params]).fetchall()
    elif kind == media.BOOK:
        query, params = books_query(owner_ids, args, user.id, user.id)
        sort_by, sort_order = sorting.choice(args, media.BOOK)
        order_sql, order_params = sorting.order_by(sort_by, sort_order, user.id)
        rows = conn.execute(query + order_sql, [*params, *order_params]).fetchall()
    else:
        rows, _, _ = _section(kind).filtered(conn, owner_ids, args, user.id)
    return [row['id'] for row in rows]
