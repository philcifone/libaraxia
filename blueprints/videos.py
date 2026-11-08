"""Videos section (Phase 8): VHS tapes and other video formats.

A video is a `books` row with media_type = 'video' (migration 023), so
reviews, watch status, viewings (reading_sessions), tags and custom
collections all work as they do for books. Everything here reads the
`library_videos` view; the Library pages read `library_books`, so the two
never mix. Wording and statuses come from utils/media.py.

Access is the same as for books (CLAUDE.md, Access Model): your own videos,
your household's (shared view), a friend's (by username), and the detail
page goes through models.can_view_book.
"""
from flask import (Blueprint, render_template, request, redirect, url_for, flash,
                   abort, jsonify, current_app)
from flask_login import login_required, current_user

from models import can_view_book, get_library_members, is_friends_with
from utils import media
from utils.book_utils import process_image, removed_filter, _normalise, get_filter_options
from utils.database import get_db
from utils.image_utils import delete_image_file, is_safe_upload_path
from utils import media_lookup
from utils.rate_limiting import limiter

videos_blueprint = Blueprint('videos', __name__, template_folder='templates')

SORT_COLUMNS = {'title', 'author', 'publish_year', 'created_at', 'runtime_minutes'}


# ------------------------------------------------------------ queries

def _filtered_videos(conn, owner_ids, args, viewer_id):
    """Videos owned by `owner_ids` (library_videos), with the search,
    filters and sort from the query string. The parameter names are the
    Library's (search_term, genre, read_status, rating, tags[], show_removed),
    so the shared header search and filter panel (_search_sort_filter.html)
    work here too; `format` is the Movies-only one. Status, rating and tag
    filters are the viewer's own, as on the Library pages."""
    marks = ','.join('?' * len(owner_ids))
    sql = f"SELECT b.* FROM library_videos b WHERE b.added_by IN ({marks})"
    params = list(owner_ids)
    sql += removed_filter(args.get('show_removed'))

    term = (args.get('search_term') or '').strip()
    if term:
        like = f'%{term}%'
        sql += (" AND (b.title LIKE ? OR b.author LIKE ? OR b.publisher LIKE ?"
                " OR b.barcode LIKE ? OR b.catalog_number LIKE ? OR CAST(b.publish_year AS TEXT) LIKE ?)")
        params += [like] * 6
    if args.get('genre'):
        sql += " AND LOWER(b.genre) = LOWER(?)"
        params.append(args.get('genre'))
    if args.get('format'):
        sql += " AND b.format = ?"
        params.append(args.get('format'))
    if args.get('read_status'):
        sql += " AND EXISTS (SELECT 1 FROM collections c WHERE c.book_id = b.id AND c.user_id = ? AND c.status = ?)"
        params += [viewer_id, args.get('read_status')]
    rating = args.get('rating', type=int)
    if rating:
        sql += " AND EXISTS (SELECT 1 FROM read_data r WHERE r.book_id = b.id AND r.user_id = ? AND r.rating >= ?)"
        params += [viewer_id, rating]
    tags = [t for t in args.getlist('tags[]') if t]
    if tags:
        tag_marks = ','.join('?' * len(tags))
        sql += (" AND EXISTS (SELECT 1 FROM book_tags t WHERE t.book_id = b.id"
                f" AND t.user_id = ? AND t.tag_name IN ({tag_marks}))")
        params += [viewer_id, *tags]

    sort_by = args.get('sort_by', 'title')
    sort_by = sort_by if sort_by in SORT_COLUMNS else 'title'
    sort_order = 'desc' if args.get('sort_order') == 'desc' else 'asc'
    # Column names come from the whitelist above, never from the request
    sql += f" ORDER BY b.{sort_by} IS NULL, b.{sort_by} COLLATE NOCASE {sort_order}, b.title COLLATE NOCASE"
    return conn.execute(sql, params).fetchall(), sort_by, sort_order


def _grid_page(owner_ids, tab, **extra):
    conn = get_db()
    videos, sort_by, sort_order = _filtered_videos(conn, owner_ids, request.args, current_user.id)
    return render_template(
        'videos.html', books=videos, tab=tab,
        total_count=len(videos), has_more=False, current_page=1,
        sort_by=sort_by, sort_order=sort_order,
        filter_options=get_filter_options(owner_ids, media.VIDEO),
        m=media.media_labels(media.VIDEO), **extra)


# ------------------------------------------------------------ grids

@videos_blueprint.route('/')
@login_required
def index():
    """Your own videos."""
    return _grid_page([current_user.id], 'mine')


@videos_blueprint.route('/shared')
@login_required
def shared():
    """Your household's videos (everyone in your library group, you included)."""
    return _grid_page(get_library_members(current_user.id), 'shared')


@videos_blueprint.route('/friends')
@login_required
def friends():
    """Your friends, with how many videos each has."""
    conn = get_db()
    rows = conn.execute('''
        SELECT u.id, u.username, u.avatar_url, COUNT(v.id) AS video_count
        FROM users u
        JOIN friendships f ON (f.user_id_1 = :me AND f.user_id_2 = u.id)
                           OR (f.user_id_2 = :me AND f.user_id_1 = u.id)
        LEFT JOIN library_videos v ON v.added_by = u.id AND v.removed_at IS NULL
        GROUP BY u.id
        ORDER BY u.username
    ''', {'me': current_user.id}).fetchall()
    return render_template('videos_friends.html', friends=rows, tab='friends',
                           m=media.media_labels(media.VIDEO))


@videos_blueprint.route('/user/<username>')
@login_required
def user_videos(username):
    """A friend's videos (or your own)."""
    conn = get_db()
    owner = conn.execute('SELECT id, username FROM users WHERE username = ?', (username,)).fetchone()
    if not owner:
        abort(404)
    if owner['id'] != current_user.id and not is_friends_with(current_user.id, owner['id']):
        abort(404)
    return _grid_page([owner['id']], 'friend', owner=owner)


# ------------------------------------------------------------ one video

@videos_blueprint.route('/<int:id>')
@login_required
def show_video(id):
    conn = get_db()
    video = conn.execute('SELECT * FROM books WHERE id = ?', (id,)).fetchone()
    if not video or not can_view_book(conn, current_user, id):
        abort(404)
    if media.media_type_of(video) != media.VIDEO:
        return redirect(url_for('books.show_book', id=id))
    from blueprints.books import render_item_page
    return render_item_page(conn, video)


def _form_values(form):
    """Cleaned form fields, plus a list of problems to show."""
    errors = []
    raw_barcode = (form.get('barcode') or '').strip()
    barcode = None
    if raw_barcode:
        barcode = media.normalize_barcode(raw_barcode)
        if not barcode:
            errors.append("The barcode isn't a valid UPC or EAN (check the digits).")
        elif media.classify_code(barcode) == media.BOOK:
            errors.append('That barcode is an ISBN: add it as a book under Library.')

    def as_int(name, low, high, label):
        value = (form.get(name) or '').strip()
        if not value:
            return None
        if not value.isdigit() or not (low <= int(value) <= high):
            errors.append(f'{label} should be a number between {low} and {high}.')
            return None
        return int(value)

    fmt = form.get('format') or media.DEFAULT_VIDEO_FORMAT
    if fmt not in media.VIDEO_FORMATS:
        fmt = media.DEFAULT_VIDEO_FORMAT
    values = {
        'title': (form.get('title') or '').strip(),
        'subtitle': (form.get('subtitle') or '').strip() or None,
        'author': (form.get('author') or '').strip(),          # director
        'publisher': (form.get('publisher') or '').strip() or None,   # studio
        'publish_year': as_int('year', 1880, 2100, 'Year'),
        'runtime_minutes': as_int('runtime_minutes', 1, 2000, 'Runtime'),
        'format': fmt,
        'barcode': barcode,
        'catalog_number': (form.get('catalog_number') or '').strip() or None,
        'genre': (form.get('genre') or '').strip() or None,
        'description': (form.get('description') or '').strip() or None,
    }
    if not values['title']:
        errors.append('A title is needed.')
    # Keep what was typed when the barcode didn't validate, so it can be fixed
    values['barcode_input'] = raw_barcode
    # A cover saved by the lookup, kept across a re-shown form
    cover = form.get('existing_cover_url')
    values['existing_cover_url'] = cover if is_safe_upload_path(cover) else ''
    return values, errors


def find_video_duplicates(conn, user_id, barcode=None, title=None, exclude_id=None):
    """Household videos with the same barcode, or the same title (case,
    punctuation and a leading article ignored). Same scope as the book
    duplicate check: your household's shelf, never strangers' records."""
    members = get_library_members(user_id)
    marks = ','.join('?' * len(members))
    rows = conn.execute(f"""
        SELECT v.id, v.title, v.author, v.format, v.barcode, v.removed_at, u.username AS owner
        FROM library_videos v LEFT JOIN users u ON u.id = v.added_by
        WHERE v.added_by IN ({marks}) AND v.id IS NOT ?
    """, [*members, exclude_id]).fetchall()
    barcode = media.normalize_barcode(barcode) if barcode else None
    want_title = _normalise(title) if title else ''
    found = []
    for row in rows:
        reasons = []
        if barcode and row['barcode'] == barcode:
            reasons.append('barcode')
        if want_title and _normalise(row['title']) == want_title:
            reasons.append('title')
        if reasons:
            found.append({**dict(row), 'removed': row['removed_at'] is not None,
                          'format_label': media.format_label(row['format']),
                          'match_reason': reasons})
    return found


def _add_page(values, duplicates=(), status=200, destination='shelf'):
    """The Add Movie page (templates/add_item.html, shared with Add Book).
    destination='wishlist' is the wishlist's Add Movie (wishlist.add_to_wishlist)."""
    tmdb = bool(media_lookup.tmdb_key())
    if destination == 'wishlist':
        target = url_for('wishlist.add_to_wishlist')
        where = dict(back_url=url_for('wishlist.view_wishlist'), back_label='Wishlist',
                     other_add_url=url_for('wishlist.add_to_wishlist', type='book'),
                     notes=values.get('notes') or '')
    else:
        target = url_for('videos.add_video')
        where = dict(back_url=url_for('videos.index'), back_label='Movies',
                     other_add_url=url_for('books.add_book'), notes=None)
    code = values.get('barcode_input') or ''
    cover = values.get('existing_cover_url')
    return render_template(
        'add_item.html', m=media.media_labels(media.VIDEO), values=values,
        duplicates=duplicates, formats=media.VIDEO_FORMATS, tmdb=tmdb,
        # Arriving with a barcode (scanned on Add Book) opens its tab;
        # otherwise title search, when there's a TMDb key for it
        active_method='code' if code or not tmdb else 'search',
        search_enabled=tmdb, code_value=code,
        cover_url=url_for('static', filename=cover) if cover else None,
        destination=destination, form_action=target, code_action=target, **where), status


@videos_blueprint.route('/add', methods=['GET', 'POST'])
@login_required
def add_video():
    """Manual entry (the main path). ?barcode= pre-fills the barcode, e.g.
    when a tape was scanned on the Add Book page; ?format= picks the format
    (the floating add button's Cartridge / DVD)."""
    conn = get_db()
    if request.method == 'GET':
        barcode = media.normalize_barcode(request.args.get('barcode')) or ''
        fmt = request.args.get('format')
        fmt = fmt if fmt in media.VIDEO_FORMATS else media.DEFAULT_VIDEO_FORMAT
        values = {'format': fmt, 'barcode_input': barcode}
        dups = find_video_duplicates(conn, current_user.id, barcode=barcode) if barcode else []
        return _add_page(values, dups)

    values, errors = _form_values(request.form)
    duplicates = find_video_duplicates(conn, current_user.id, values['barcode'], values['title'])
    if duplicates and not request.form.get('confirm_duplicate'):
        errors.append('This looks like a movie already on your household\'s shelf. '
                      'Tick "Add it anyway" if it\'s a second copy.')
    if errors:
        for error in errors:
            flash(error, 'error')
        return _add_page(values, duplicates, status=400)

    # An upload wins; otherwise the cover a lookup saved (process_image only
    # accepts paths inside static/uploads)
    cover = process_image(request.files.get('image'), request.form.get('existing_cover_url'))
    cur = conn.execute('''
        INSERT INTO books (title, subtitle, author, publisher, publish_year, runtime_minutes,
                           format, barcode, catalog_number, genre, description, cover_image_url,
                           page_count, added_by, media_type)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, 'video')
    ''', (values['title'], values['subtitle'], values['author'], values['publisher'],
          values['publish_year'], values['runtime_minutes'], values['format'], values['barcode'],
          values['catalog_number'], values['genre'], values['description'], cover, current_user.id))
    conn.commit()
    flash(f"'{values['title']}' added to your movies.", 'success')
    return redirect(url_for('videos.show_video', id=cur.lastrowid))


@videos_blueprint.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_video(id):
    conn = get_db()
    video = conn.execute("SELECT * FROM books WHERE id = ?", (id,)).fetchone()
    if not video or not (current_user.is_admin or video['added_by'] == current_user.id):
        abort(404)
    if media.media_type_of(video) != media.VIDEO:
        return redirect(url_for('books.edit_book', id=id))
    from blueprints.books import _book_tools_context
    m = media.media_labels(media.VIDEO)

    def page(values, duplicates=(), status=200):
        return render_template('video_form.html', video=video, values=values, duplicates=duplicates,
                               m=m, formats=media.VIDEO_FORMATS,
                               **_book_tools_context(conn, video)), status

    if request.method == 'GET':
        values = dict(video)
        values['barcode_input'] = video['barcode'] or ''
        return page(values)

    values, errors = _form_values(request.form)
    if errors:
        for error in errors:
            flash(error, 'error')
        return page(values, status=400)

    cover = video['cover_image_url']
    upload = request.files.get('image')
    if upload and upload.filename:
        new_cover = process_image(upload)
        if new_cover:
            if cover and cover != new_cover:
                delete_image_file(cover)
            cover = new_cover
    conn.execute('''
        UPDATE books SET title = ?, subtitle = ?, author = ?, publisher = ?, publish_year = ?,
               runtime_minutes = ?, format = ?, barcode = ?, catalog_number = ?, genre = ?,
               description = ?, cover_image_url = ?
        WHERE id = ? AND media_type = 'video'
    ''', (values['title'], values['subtitle'], values['author'], values['publisher'],
          values['publish_year'], values['runtime_minutes'], values['format'], values['barcode'],
          values['catalog_number'], values['genre'], values['description'], cover, id))
    conn.commit()
    flash('Movie updated.', 'success')
    return redirect(url_for('videos.show_video', id=id))


@videos_blueprint.route('/check_duplicates', methods=['POST'])
@login_required
def check_duplicates():
    """For the add page (add_item.js), after a lookup: is this barcode or
    title already on the household's movie shelf?"""
    data = request.get_json(silent=True) or {}
    try:
        dups = find_video_duplicates(get_db(), current_user.id,
                                     barcode=(data.get('barcode') or '').strip(),
                                     title=(data.get('title') or '').strip())
    except Exception:
        current_app.logger.exception('Error checking video duplicates')
        return jsonify({'success': False, 'error': "Couldn't check for duplicates."}), 500
    return jsonify({'success': True, 'has_duplicates': bool(dups), 'duplicates': [
        {'id': d['id'], 'title': d['title'], 'owner': d['owner'], 'format': d['format'],
         'format_label': d['format_label'], 'removed': d['removed'],
         'match_reason': d['match_reason']} for d in dups]})


@videos_blueprint.route('/lookup')
@login_required
@limiter.limit('60 per hour')
def lookup():
    """Pre-fill for the Add Video form (utils/media_lookup.py).

    ?barcode= asks UPCitemdb, then TMDb on the title it found; ?title= (and
    &year=) asks TMDb only, for tapes without a barcode; ?tmdb_id= is a film
    picked from the Search tab (/videos/search). Always answers 200
    with {"success", "found", "details", "sources", "cover"}: not finding
    anything is normal for VHS, and the form is filled in by hand then.
    """
    barcode = (request.args.get('barcode') or '').strip()
    title = (request.args.get('title') or '').strip()[:200]
    year = request.args.get('year', type=int)
    tmdb_id = request.args.get('tmdb_id', type=int)
    if barcode and not media.normalize_barcode(barcode):
        return jsonify({'success': False, 'error': "That barcode isn't a valid UPC or EAN."}), 400
    if not barcode and not title and not tmdb_id:
        return jsonify({'success': False, 'error': 'Give a barcode or a title.'}), 400
    try:
        result = media_lookup.lookup(barcode=barcode or None, title=title or None, year=year,
                                     tmdb_id=tmdb_id)
    except Exception:
        current_app.logger.exception('Video lookup failed')
        return jsonify({'success': False, 'error': 'The lookup failed. Fill the form in by hand.'}), 500
    return jsonify({'success': True, 'tmdb': bool(media_lookup.tmdb_key()), **result})


@videos_blueprint.route('/search')
@login_required
@limiter.limit('120 per hour')
def search():
    """The Add Movie page's Search tab: films matching ?q= on TMDb, to pick
    one from (then /videos/lookup?tmdb_id= fills the form). Needs
    TMDB_API_KEY; without it the tab says so and this answers an error."""
    query = (request.args.get('q') or '').strip()[:200]
    if not media_lookup.tmdb_key():
        return jsonify({'success': False, 'error': 'Title search needs a TMDb key (TMDB_API_KEY in .env).'}), 400
    if len(query) < 2:
        return jsonify({'success': True, 'results': []})
    try:
        results = media_lookup.tmdb_search(query)
    except Exception:
        current_app.logger.exception('Movie search failed')
        return jsonify({'success': False, 'error': 'The search failed. Try again, or use the barcode.'}), 500
    return jsonify({'success': True, 'results': results})
