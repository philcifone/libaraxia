"""The ids a grid shows (ROADMAP 14a step 1).

Bulk edit's "select all 57 in this view" must name exactly the items the grid
page renders, in the same order, so the grids and the selection share one
query rather than two that drift apart.

  books_query    the Books grid's WHERE (base.library_page builds the page from it)
  term_match     the search box's condition, shared with the grid's search hints
  view_ids       every id of a whitelisted grid view, all pages, for a selection

The Books search used to be its own page (/books/search) with a slightly
different query; since 16.0 every grid searches itself, so a search covers
exactly the shelf in view (the loose end "search should match the grid").

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

# What the Books search box looks in (as well as the viewer's tags)
BOOK_SEARCH_COLUMNS = ['title', 'subtitle', 'author', 'publisher', 'isbn', 'publish_year']


def term_match(term, data_user):
    """(SQL condition on alias b, params) for the Books search box: every
    word, folded, in one of BOOK_SEARCH_COLUMNS or `data_user`'s tags."""
    return search.match(term, BOOK_SEARCH_COLUMNS, viewer_id=data_user)


def from_goodreads(args, viewer_id):
    """SQL fragment and params for ?from=goodreads (ROADMAP 14b): books an
    import of the viewer's matched or wrote, not undone; ?gr_shelf= narrows
    it to one Goodreads shelf (14c). Always the viewer's
    own provenance, never the shelf owner's, so a friend's grid can't show
    what their import touched."""
    shelf = (args.get('gr_shelf') or '').strip().lower()
    if (args.get('from') != 'goodreads' and not shelf) or viewer_id is None:
        return '', []
    sql = (' AND EXISTS (SELECT 1 FROM goodreads_rows gr JOIN goodreads_imports gi ON gi.id = gr.import_id'
           ' WHERE gr.book_id = b.id AND gi.user_id = ? AND gi.undone_at IS NULL')
    params = [viewer_id]
    if shelf:
        # ?gr_shelf=audiobook (14c, the Collections page's Goodreads shelves
        # card): one shelf of the row's comma-joined list. instr, not LIKE,
        # so a "_" in a shelf name is not a wildcard.
        sql += " AND instr(',' || gr.shelves || ',', ',' || ? || ',') > 0"
        params.append(shelf)
    return sql + ')', params


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
        match_sql, match_params = term_match(term, data_user)
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

    if kind == media.BOOK:
        query, params = books_query(owner_ids, args, user.id, user.id)
        sort_by, sort_order = sorting.choice(args, media.BOOK)
        order_sql, order_params = sorting.order_by(sort_by, sort_order, user.id)
        rows = conn.execute(query + order_sql, [*params, *order_params]).fetchall()
    else:
        rows, _, _ = _section(kind).filtered(conn, owner_ids, args, user.id)
    return [row['id'] for row in rows]
