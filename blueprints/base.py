from flask import render_template, redirect, url_for, request, Blueprint, jsonify, abort, flash
from flask_login import login_required, current_user
from utils.database import get_db
from utils import grid_query, households, media, sorting
from datetime import datetime
from models import get_library_members, is_friends_with
from utils.book_utils import get_filter_options, card_json

base_blueprint = Blueprint('base', __name__, template_folder='templates')

@base_blueprint.route("/")
def home():
    if current_user.is_authenticated:
        return redirect(url_for('base.index'))
    return redirect(url_for('auth.login'))

@base_blueprint.route("/shelves")
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
    # Sort (utils/sorting.py: the menu's choices, unknown ones fall back to title)
    sort_by, sort_order = sorting.choice(request.args, media.BOOK)

    conn = get_db()
    # The filters live in utils/grid_query.py, shared with bulk edit's selection of a view
    query, params = grid_query.books_query(owner_ids, request.args, data_user, current_user.id)

    total_count = conn.execute(query.replace("SELECT b.*", "SELECT COUNT(b.id)", 1), params).fetchone()[0]
    order_sql, order_params = sorting.order_by(sort_by, sort_order, data_user)
    offset = (page - 1) * per_page
    books = conn.execute(query + order_sql + " LIMIT ? OFFSET ?",
                         [*params, *order_params, per_page, offset]).fetchall()
    has_more = (offset + len(books)) < total_count

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'books': card_json(conn, data_user, books),   # list view's columns too
                        'total_count': total_count, 'has_more': has_more, 'current_page': page})

    return render_template(template, books=books,
                           filter_options=get_filter_options(owner_ids, data_user=data_user),
                           sort_by=sort_by, sort_order=sort_order, total_count=total_count,
                           has_more=has_more, current_page=page, marks_user=data_user, **extra)


@base_blueprint.route("/index")
@login_required
def index():
    """Your Library: the books you own"""
    return library_page("index.html", [current_user.id], current_user.id)


@base_blueprint.route("/shared-library")
@login_required
def shared_library():
    """The household's books (everyone in your library group), or chosen
    members' and yours with ?member= (utils/households.member_choice)."""
    others, owner_ids, member_filter = households.member_choice(
        get_db(), current_user.id, request.args.getlist("member", type=int))
    return library_page("shared_library.html", owner_ids, current_user.id,
                        household_members=others, member_filter=member_filter)


@base_blueprint.route("/friends-libraries")
@login_required
def friends_libraries():
    """Old Friends' Libraries tab: friends are their own page now (11.3)."""
    return redirect(url_for('friends.index'))


@base_blueprint.route("/library/<username>")
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
