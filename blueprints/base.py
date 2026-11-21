import random

from flask import render_template, redirect, url_for, request, Blueprint, jsonify, abort, flash, session
from flask_login import login_required, current_user
from utils.database import get_db
from utils import grid_query, households, item3d, media, sorting
from datetime import datetime
from models import get_library_members, is_friends_with
from utils.book_utils import get_filter_options, card_json, show_choice, off_shelf_matches, wishlist_matches

# No url_prefix (app.py): the Books shelves live under /books/ like Movies'
# under /videos/ and Music's under /records/ (ROADMAP 16.0g step 7), while
# home and the Shelves hub stay at /base/. Endpoint names didn't change.
base_blueprint = Blueprint('base', __name__, template_folder='templates')


def moved(endpoint, **values):
    """A 301 to where a page lives now, query string kept: old bookmarks
    and the links in notifications sent before the move."""
    url = url_for(endpoint, **values)
    query = request.query_string.decode()
    return redirect(f'{url}?{query}' if query else url, code=301)


@base_blueprint.route("/base/index")
def old_index():
    return moved('base.index')


@base_blueprint.route("/base/shared-library")
def old_shared_library():
    return moved('base.shared_library')


@base_blueprint.route("/base/library/<username>")
def old_friend_library(username):
    return moved('base.friend_library', username=username)

@base_blueprint.route("/base/")
def home():
    if current_user.is_authenticated:
        return redirect(url_for('base.index'))
    return redirect(url_for('auth.login'))

@base_blueprint.route("/base/shelves")
@login_required
def shelves():
    """The sidebar's Shelves link (ROADMAP 11.1): your shelf in the section
    you used last (the shelf_section cookie, set by every Shelves page in
    app.py), books the first time."""
    kind = request.cookies.get('shelf_section')
    endpoint = media.SHELF_ENDPOINTS.get(kind, media.SHELF_ENDPOINTS[media.BOOK])['mine']
    return redirect(url_for(endpoint))


def library_page(template, owner_ids, data_user, **extra):
    """A Library grid (books): the shelves of `owner_ids`, with the search,
    filters, sort and paging from the query string. Shared by your Library,
    the household's and a friend's.

    `data_user` is whose statuses, ratings and tags the status / rating /
    tag filters, the search's tag matching, the sorts by date read and
    rating, and list view's columns use: the entries in view (Phil,
    2026-11-08). That's you on your own and the household's shelves, the
    friend on theirs. Infinite scroll asks the same URL with
    X-Requested-With and gets JSON."""
    page = request.args.get("page", 1, type=int)
    per_page = max(12, min(request.args.get("per_page", 30, type=int), 100))
    conn = get_db()
    # Sort (utils/sorting.py: the menu's choices, unknown ones fall back to
    # title); none in the URL means your last one on a Books grid
    sort_by, sort_order = sorting.remembered(conn, current_user.id, request.args, media.BOOK)
    # The filters live in utils/grid_query.py, shared with bulk edit's selection of a view
    query, params = grid_query.books_query(owner_ids, request.args, data_user, current_user.id,
                                           lent_ok='friend' not in extra)

    total_count = conn.execute(query.replace("SELECT b.*", "SELECT COUNT(b.id)", 1), params).fetchone()[0]
    order_sql, order_params = sorting.order_by(sort_by, sort_order, data_user)
    offset = (page - 1) * per_page
    books = conn.execute(query + order_sql + " LIMIT ? OFFSET ?",
                         [*params, *order_params, per_page, offset]).fetchall()
    has_more = (offset + len(books)) < total_count

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'books': card_json(conn, data_user, books, current_user.id),   # list view's columns too
                        'total_count': total_count, 'has_more': has_more, 'current_page': page})

    # A search on your own or the household's shelf also says what matches
    # off the shelf ("not on your shelf, but you read it", 8B.3) and on your
    # wishlist (7.2b); a friend's shelf shows only their shelf
    term = (request.args.get("search_term") or "").strip()
    if term and 'friend' not in extra:
        match_sql, match_params = grid_query.term_match(term, current_user.id)
        if not show_choice(request.args):
            extra['off_shelf'] = off_shelf_matches(conn, 'library_books', owner_ids, match_sql,
                                                   match_params, current_user.id)
        extra['on_wishlist'] = wishlist_matches(conn, current_user.id, media.BOOK, match_sql, match_params)

    return render_template(template, books=books,
                           filter_options=get_filter_options(owner_ids, data_user=data_user),
                           sort_by=sort_by, sort_order=sort_order, total_count=total_count,
                           has_more=has_more, current_page=page, marks_user=data_user, **extra)


@base_blueprint.route("/books/")
@login_required
def index():
    """Your Library: the books you own. In the Shelf style a few of your
    books that turn in 3D stand on the heading's shelf (ROADMAP 16.0a):
    chosen by a number drawn at login, or here for a remembered sign-in."""
    return library_page("index.html", [current_user.id], current_user.id,
                        heading_books=_standing_books())


def _standing_books():
    """The 3D books on the Shelves heading (Shelf style, not for the
    infinite-scroll fetches). Your own, on Mine and Household alike, so
    toggling the house leaves the same books standing (Phil, 2026-11-16)."""
    if current_user.theme_style != 'shelf' or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return []
    seed = session.setdefault('heading_seed', random.randrange(2 ** 31))
    return item3d.heading_books(get_db(), current_user.id, seed)


@base_blueprint.route("/books/shared")
@login_required
def shared_library():
    """The household's books (everyone in your library group), or chosen
    members' and yours with ?member= (utils/households.member_choice)."""
    others, owner_ids, member_filter = households.member_choice(
        get_db(), current_user.id, request.args.getlist("member", type=int))
    return library_page("shared_library.html", owner_ids, current_user.id,
                        household_members=others, member_filter=member_filter,
                        heading_books=_standing_books())


@base_blueprint.route("/base/friends-libraries")
@login_required
def friends_libraries():
    """Old Friends' Libraries tab: friends are their own page now (11.3)."""
    return redirect(url_for('friends.index'))


@base_blueprint.route("/books/user/<username>")
@login_required
def friend_library(username):
    """A friend's books (11.3): the same grid as yours, filtered and sorted
    by their statuses, ratings and tags (library_page's data_user)."""
    friend = get_db().execute('SELECT id, username FROM users WHERE username = ?', (username,)).fetchone()
    if not friend:
        abort(404)
    if friend['id'] != current_user.id and not is_friends_with(current_user.id, friend['id']):
        flash('You must be friends to view this library', 'warning')
        abort(403)
    return library_page('friend_library.html', [friend['id']], friend['id'], friend=friend)
