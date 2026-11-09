"""The Reviews section (ROADMAP 13): a sidebar entry of its own.

    /reviews/                 one section's rows (?type=book|video|record)
    /reviews/all/<which>      "See all": every review in one list
    /reviews/find             the [+ Review] search (?type=, ?q=)

Nothing is written here. A review is written and edited on its item's review
page (`read.rate_review`), which every link on these pages leads to; the
queries are in utils/reviews.py.
"""
from flask import Blueprint, abort, render_template, request, url_for
from flask_login import current_user, login_required

from models import friend_ids
from utils import media, reviews
from utils.database import get_db

reviews_blueprint = Blueprint('reviews', __name__, template_folder='templates')

# The floating [+ Review] menu: one entry per type, each opening the search
FAB_LABELS = {media.BOOK: 'Book', media.VIDEO: 'Movie', media.RECORD: 'Album'}


def _type(value):
    return value if value in media.MEDIA_TYPES else media.BOOK


def _fab_items():
    return [(label, url_for('reviews.find', type=t)) for t, label in FAB_LABELS.items()]


def _section_urls(endpoint, **args):
    """The Books | Movies | Music switch's links for one of these pages."""
    return {t: url_for(endpoint, type=t, **args) for t in media.MEDIA_TYPES}


@reviews_blueprint.route('/')
@login_required
def index():
    conn = get_db()
    media_type = _type(request.args.get('type'))
    return render_template(
        'reviews.html',
        media_type=media_type,
        m=media.media_labels(media_type),
        section_urls=_section_urls('reviews.index'),
        shelves=reviews.shelves(conn, current_user.id, media_type),
        fab_items=_fab_items(),
    )


@reviews_blueprint.route('/all/<which>')
@login_required
def see_all(which):
    """One row in full. ?by=<username> on the friends' list: that friend's
    reviews only (their profile's "View all"); 404 unless you're friends."""
    if which not in reviews.LISTS:
        abort(404)
    conn = get_db()
    media_type = _type(request.args.get('type'))
    heading, friend, by = reviews.LIST_LABELS[which], None, None
    if which == 'friends' and request.args.get('by'):
        friend = conn.execute('SELECT id, username FROM users WHERE username = ?',
                              (request.args['by'],)).fetchone()
        if not friend or friend['id'] not in friend_ids(conn, current_user.id):
            abort(404)
        heading, by = f"{friend['username']}'s reviews", friend['username']
    return render_template(
        'reviews_list.html',
        which=which,
        heading=heading,
        media_type=media_type,
        m=media.media_labels(media_type),
        section_urls=_section_urls('reviews.see_all', which=which, by=by),
        rows=reviews.list_rows(conn, current_user.id, media_type, which,
                               friend_id=friend['id'] if friend else None),
        fab_items=_fab_items(),
    )


@reviews_blueprint.route('/find')
@login_required
def find():
    """[+ Review] -> Book | Movie | Album -> this search. A result opens its
    review page; nothing found offers to add it as not owned, and saving
    that lands on the review page (?then=review on the add page)."""
    conn = get_db()
    media_type = _type(request.args.get('type'))
    term = (request.args.get('q') or '').strip()[:200]
    results = reviews.find(conn, current_user.id, media_type, term)
    add_url = url_for(media.item_endpoint(media_type, 'add'),
                      not_owned=1, then='review', title=term or None)
    return render_template(
        'reviews_find.html',
        media_type=media_type,
        m=media.media_labels(media_type),
        section_urls=_section_urls('reviews.find', q=term or None),
        term=term,
        results=results,
        limit=reviews.FIND_LIMIT,
        add_url=add_url,
        noun=FAB_LABELS[media_type].lower(),
    )
