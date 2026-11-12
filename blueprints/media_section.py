"""Shared code for the Movies & TV and Music sections (Phase 8.7).

Both sections are `books` rows of one media type (utils/media.py), each
read through its own view (library_videos, library_records), so the Library
and the other section never see them. Their pages are the same: a grid with
the header search and filters, household and friends' tabs, add and edit
forms, a duplicate check, and the detail page (books.render_item_page). A
`Section` describes what differs; `make_blueprint` builds the routes.
blueprints/videos.py and blueprints/records.py each make one and add their
own lookups (TMDb/UPCitemdb, MusicBrainz).

Endpoint names follow media.item_endpoint: videos.show_video,
records.add_record, ... plus index / shared / friends for the tabs.

Access is the same as for books (CLAUDE.md, Access Model): your own items,
your household's (shared view), a friend's (by username), and the detail
page goes through models.can_view_book.
"""
from dataclasses import dataclass, field
from typing import Callable, Optional

from flask import (Blueprint, render_template, request, redirect, url_for, flash,
                   abort, jsonify, current_app)
from flask_login import login_required, current_user

from models import can_view_book, get_library_members, is_friends_with
from utils import households, media, search, sorting
from utils.reviews import then_review_values
from utils.book_utils import (process_image, shelf_filter, show_choice, off_shelf_matches, wishlist_matches,
                              _normalise, get_filter_options)
from utils.database import get_db
from utils import cover_crop
from utils.image_utils import delete_image_file, is_safe_upload_path


@dataclass(frozen=True)
class Section:
    media_type: str                 # media.VIDEO / media.RECORD
    view: str                       # 'library_videos'
    # Extra context for the add page (lookup flags, which tab opens first),
    # given the form values. Returns a dict for add_item.html.
    add_context: Callable[[dict], dict] = field(default=lambda values: {})
    # Help text under the empty grid
    empty_text: str = ''
    # Records: the cat. no. identifies a pressing, and there's no barcode
    match_catalog_number: bool = False
    # The add page's lookup to run on load, from a source id in the URL
    # (?tmdb_id=, ?discogs=, ?mbid=; Do I have this?, ROADMAP 13b): the
    # section's own JSON lookup URL, or None. Given request.args.
    lookup_url: Callable[[dict], Optional[str]] = field(default=lambda args: None)

    # ---------------------------------------------------------- naming
    @property
    def m(self):
        return media.media_labels(self.media_type)

    @property
    def name(self):
        """Blueprint name and URL prefix: 'videos', 'records'."""
        return media.BLUEPRINTS[self.media_type]

    def endpoint(self, action):
        """'show' -> 'videos.show_video'."""
        return media.item_endpoint(self.media_type, action)

    @property
    def has_barcode(self):
        return media.HAS_BARCODE[self.media_type]

    @property
    def formats(self):
        return media.FORMATS[self.media_type]

    @property
    def default_format(self):
        return media.DEFAULT_FORMAT[self.media_type]

    def item_m(self, values):
        """The words for one item of this section, from a row or the form's
        values: a video's kind picks "TV show" or "movie" (media.KIND_WORDS)."""
        return media.item_labels({**dict(values), 'media_type': self.media_type})

    def kind_arg(self, args):
        """An add page's ?kind=tv (the add button's TV entry): {'video_kind':
        'tv'} to start the form on TV, or {} (the form's default, Movie)."""
        if self.media_type == media.VIDEO and media.video_kind(args.get('kind')):
            return {'video_kind': media.TV}
        return {}

    def pick_format(self, fmt):
        return fmt if fmt in self.formats else self.default_format

    # ---------------------------------------------------------- queries
    @staticmethod
    def search_match(term, viewer_id):
        """The search box's condition on alias b, and its parameters: every
        word, accents and punctuation ignored, in any of these columns or the
        viewer's tags on the item (utils/search.py, ROADMAP 7.2b)."""
        return search.match(term, ['title', 'subtitle', 'author', 'publisher', 'barcode',
                                   'catalog_number', 'publish_year'], viewer_id=viewer_id)

    def on_wishlist(self, conn, args, viewer_id):
        """The viewer's wishlist entries of this type that match the search
        (book_utils.wishlist_matches), or None."""
        term = (args.get('search_term') or '').strip()
        if not term:
            return None
        match_sql, match_params = self.search_match(term, viewer_id)
        return wishlist_matches(conn, viewer_id, self.media_type, match_sql, match_params)

    def off_shelf(self, conn, owner_ids, args, viewer_id):
        """The search hint's matches (book_utils.off_shelf_matches), only
        for a search on the default Show."""
        term = (args.get('search_term') or '').strip()
        if not term or show_choice(args):
            return None
        match_sql, match_params = self.search_match(term, viewer_id)
        return off_shelf_matches(conn, self.view, owner_ids, match_sql, match_params, viewer_id)

    def filtered(self, conn, owner_ids, args, viewer_id):
        """Items owned by `owner_ids`, with the search, filters and sort from
        the query string. The parameter names are the Library's
        (search_term, genre, read_status, rating, tags[], show), so
        the shared header search and filter panel (_search_sort_filter.html)
        work here too; `format` is the sections' own. Status, rating and tag
        filters are the viewer's own, as on the Library pages."""
        marks = ','.join('?' * len(owner_ids))
        # self.view is one of our own view names, never request input
        sql = f"SELECT b.* FROM {self.view} b WHERE b.added_by IN ({marks})"
        params = list(owner_ids)
        sql += shelf_filter(args)

        term = (args.get('search_term') or '').strip()
        if term:
            match_sql, match_params = self.search_match(term, viewer_id)
            sql += f" AND ({match_sql})"
            params += match_params
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

        # The menu's choices for this section (utils/sorting.py)
        sort_by, sort_order = sorting.choice(args, self.media_type)
        order_sql, order_params = sorting.order_by(sort_by, sort_order, viewer_id)
        return conn.execute(sql + order_sql, params + order_params).fetchall(), sort_by, sort_order

    def find_duplicates(self, conn, user_id, barcode=None, title=None, author=None,
                        catalog_number=None, exclude_id=None):
        """Household items of this type with the same barcode or cat. no., or
        the same title (case, punctuation and a leading article ignored). For
        records the title only counts with the same artist, or when either
        artist is blank: plenty of records are called "Greatest Hits". Same
        scope as the book duplicate check: your household's shelf, never
        strangers' records."""
        members = get_library_members(user_id)
        marks = ','.join('?' * len(members))
        rows = conn.execute(f"""
            SELECT v.id, v.title, v.author, v.format, v.barcode, v.catalog_number,
                   v.removed_at, v.owned, u.username AS owner
            FROM {self.view} v LEFT JOIN users u ON u.id = v.added_by
            WHERE v.added_by IN ({marks}) AND v.id IS NOT ?
        """, [*members, exclude_id]).fetchall()
        barcode = media.normalize_barcode(barcode) if barcode and self.has_barcode else None
        want_title = _normalise(title) if title else ''
        want_author = _normalise(author) if author else ''
        want_catno = _catno(catalog_number) if self.match_catalog_number else ''
        found = []
        for row in rows:
            reasons = []
            if barcode and row['barcode'] == barcode:
                reasons.append('barcode')
            if want_catno and _catno(row['catalog_number']) == want_catno:
                reasons.append('catalogue number')
            if want_title and _normalise(row['title']) == want_title:
                theirs = _normalise(row['author']) if row['author'] else ''
                if (self.media_type != media.RECORD or not want_author or not theirs
                        or theirs == want_author):
                    reasons.append('title')
            if reasons:
                found.append({**dict(row), 'removed': row['removed_at'] is not None,
                              'not_owned': not row['owned'],
                              'format_label': media.format_label(row['format']),
                              'match_reason': reasons})
        return found

    # ---------------------------------------------------------- forms
    def form_values(self, form):
        """Cleaned form fields, plus a list of problems to show."""
        errors = []
        raw_barcode = (form.get('barcode') or '').strip() if self.has_barcode else ''
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

        values = {
            'title': (form.get('title') or '').strip(),
            'subtitle': (form.get('subtitle') or '').strip() or None,
            'author': (form.get('author') or '').strip(),               # director / artist
            'publisher': (form.get('publisher') or '').strip() or None,  # studio / label
            'publish_year': as_int('year', 1880, 2100, 'Year'),
            'runtime_minutes': as_int('runtime_minutes', 1, 2000, self.m['length']),
            'format': self.pick_format(form.get('format')),
            'barcode': barcode,
            'catalog_number': (form.get('catalog_number') or '').strip() or None,
            'genre': (form.get('genre') or '').strip() or None,
            'description': (form.get('description') or '').strip() or None,
        }
        # Movie or TV (15.1): 'tv' or None (a movie); the season is kept for
        # TV only, so switching a set back to Movie drops it
        kind = media.video_kind(form.get('video_kind')) if self.media_type == media.VIDEO else None
        values['video_kind'] = kind
        values['season'] = ((form.get('season') or '').strip()[:100] or None) if kind == media.TV else None
        if not values['title']:
            errors.append('A title is needed.')
        # Keep what was typed when the barcode didn't validate, so it can be fixed
        values['barcode_input'] = raw_barcode
        # Kept across a re-shown form too: "I don't own this", and where
        # saving goes next (then=review: the review page, ROADMAP 13)
        values['not_owned'] = bool(form.get('not_owned'))
        values['then'] = 'review' if form.get('then') == 'review' else ''
        # A cover saved by the lookup, kept across a re-shown form
        cover = form.get('existing_cover_url')
        values['existing_cover_url'] = cover if is_safe_upload_path(cover) else ''
        return values, errors

    def duplicates_for(self, conn, values, exclude_id=None):
        return self.find_duplicates(conn, current_user.id, barcode=values.get('barcode'),
                                    title=values.get('title'), author=values.get('author'),
                                    catalog_number=values.get('catalog_number'),
                                    exclude_id=exclude_id)

    def insert(self, conn, values, cover, owner_id, owned=True):
        """A new books row of this type; returns its id. The caller commits.
        owned=False: seen or heard but not had (8B.3), kept off the shelf."""
        cur = conn.execute('''
            INSERT INTO books (title, subtitle, author, publisher, publish_year, runtime_minutes,
                               format, barcode, catalog_number, genre, description, cover_image_url,
                               page_count, added_by, media_type, owned, video_kind, season)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?)
        ''', (values['title'], values['subtitle'], values['author'], values['publisher'],
              values['publish_year'], values['runtime_minutes'], values['format'], values['barcode'],
              values['catalog_number'], values['genre'], values['description'], cover, owner_id,
              self.media_type, 1 if owned else 0, values.get('video_kind'), values.get('season')))
        return cur.lastrowid

    def add_page(self, values, duplicates=(), status=200, destination='shelf'):
        """The add page (templates/add_item.html, shared with Add Book).
        destination='wishlist' is the wishlist's add (wishlist.add_to_wishlist)."""
        m = self.m
        if destination == 'wishlist':
            target = url_for('wishlist.add_to_wishlist')     # the form posts media_type
            where = dict(back_url=url_for('wishlist.view_wishlist'), back_label='Wishlist',
                         other_add_url=url_for('wishlist.add_to_wishlist', type='book'),
                         notes=values.get('notes') or '')
        else:
            target = url_for(self.endpoint('add'))
            where = dict(back_url=url_for(f'{self.name}.index'), back_label=m['section'],
                         other_add_url=url_for('books.add_book'), notes=None)
        code = values.get('barcode_input') or ''
        cover = values.get('existing_cover_url')
        # "Add a Movie or Show" until a kind is known (?kind=, or a re-shown
        # form), then "Add a TV Show" / "Add a Movie"
        if 'video_kind' in values:
            m = self.item_m(values)
        context = dict(active_method='search', search_enabled=True, tmdb=False)
        context.update(self.add_context(values))
        return render_template(
            'add_item.html', m=m, values=values, duplicates=duplicates, formats=self.formats,
            code_value=code, cover_url=url_for('static', filename=cover) if cover else None,
            destination=destination, form_action=target, code_action=target,
            **context, **where), status


def _catno(value):
    """A catalogue number for comparing: case, spaces and dashes ignored."""
    return ''.join(ch for ch in (value or '').upper() if ch.isalnum())


def make_blueprint(section: Section) -> Blueprint:
    """The routes of one section; see the module docstring."""
    bp = Blueprint(section.name, __name__, template_folder='templates')
    m_type = section.media_type
    item = media.ITEMS[m_type]

    def grid_page(owner_ids, tab, **extra):
        conn = get_db()
        # Filters, sorts and list view use the statuses, ratings and tags of
        # whoever's entries are in view: the friend on their shelf, you on
        # yours and the household's (11.3)
        data_user = owner_ids[0] if tab == 'friend' else current_user.id
        rows, sort_by, sort_order = section.filtered(conn, owner_ids, request.args, data_user)
        return render_template(
            'media_grid.html', books=rows, tab=tab, marks_user=data_user,
            total_count=len(rows), has_more=False, current_page=1,
            sort_by=sort_by, sort_order=sort_order,
            filter_options=get_filter_options(owner_ids, m_type, data_user=data_user),
            m=section.m, empty_text=section.empty_text,
            # Friends' grids show only their shelf, so no hint there
            off_shelf=None if tab == 'friend' else section.off_shelf(
                conn, owner_ids, request.args, current_user.id),
            on_wishlist=None if tab == 'friend' else section.on_wishlist(
                conn, request.args, current_user.id),
            **extra)

    # ------------------------------------------------------ grids
    @login_required
    def index():
        """Your own items."""
        return grid_page([current_user.id], 'mine')

    @login_required
    def shared():
        """Your household's (everyone in your library group, you included),
        or chosen members' and yours with ?member= (utils/households.member_choice)."""
        others, owner_ids, member_filter = households.member_choice(
            get_db(), current_user.id, request.args.getlist('member', type=int))
        return grid_page(owner_ids, 'shared', household_members=others, member_filter=member_filter)

    @login_required
    def friends():
        """Old Friends' tab of the section: friends are their own page now
        (friends.index, ROADMAP 11.3)."""
        return redirect(url_for('friends.index'))

    @login_required
    def user_items(username):
        """A friend's items (or your own)."""
        owner = get_db().execute('SELECT id, username FROM users WHERE username = ?',
                                 (username,)).fetchone()
        if not owner:
            abort(404)
        if owner['id'] != current_user.id and not is_friends_with(current_user.id, owner['id']):
            abort(404)
        return grid_page([owner['id']], 'friend', owner=owner)

    # ------------------------------------------------------ one item
    @login_required
    def show_item(id):
        conn = get_db()
        row = conn.execute('SELECT * FROM books WHERE id = ?', (id,)).fetchone()
        if not row or not can_view_book(conn, current_user, id):
            abort(404)
        kind = media.media_type_of(row)
        if kind != m_type:
            return redirect(url_for(media.item_endpoint(kind), id=id))
        from blueprints.books import render_item_page
        return render_item_page(conn, row)

    @login_required
    def add_item():
        """Manual entry (the main path). ?format= picks the format (the
        floating add button); ?barcode= pre-fills the barcode, for movies
        scanned on the Add Book page."""
        conn = get_db()
        if request.method == 'GET':
            barcode = (media.normalize_barcode(request.args.get('barcode')) or ''
                       if section.has_barcode else '')
            values = {'format': section.pick_format(request.args.get('format')),
                      'barcode_input': barcode,
                      **section.kind_arg(request.args),
                      # From Do I have this? (13b): a title, or an id to look up
                      **media.add_prefill(request.args),
                      'lookup_url': section.lookup_url(request.args),
                      # From Reviews' "Add it as not owned" (ROADMAP 13)
                      **then_review_values(request.args)}
            dups = (section.find_duplicates(conn, current_user.id, barcode=barcode)
                    if barcode else [])
            return section.add_page(values, dups)

        values, errors = section.form_values(request.form)
        duplicates = section.duplicates_for(conn, values)
        if duplicates and not request.form.get('confirm_duplicate'):
            errors.append(f"This looks like a {section.item_m(values)['noun']} already on your household's "
                          "shelf. Tick \"Add it anyway\" if it's a second copy.")
        if errors:
            for error in errors:
                flash(error, 'error')
            return section.add_page(values, duplicates, status=400)

        # An upload wins; otherwise the cover a lookup saved (process_image
        # only accepts paths inside static/uploads)
        # A crop (15.3) wins over an upload, which wins over the lookup's cover
        cover = cover_crop.crop_or_flash(request.form, [request.form.get('existing_cover_url')]) or process_image(
            request.files.get('image'), request.form.get('existing_cover_url'))
        owned = not request.form.get('not_owned')
        new_id = section.insert(conn, values, cover, current_user.id, owned=owned)
        conn.commit()
        if values['then'] == 'review':
            flash(f"'{values['title']}' added{'' if owned else ' as unshelved'}. Now your review.", 'success')
            return redirect(url_for('read.rate_review', book_id=new_id, **{'from': 'reviews'}))
        im = section.item_m(values)
        if owned:
            flash(f"'{values['title']}' added to your {im['plural']}.", 'success')
        else:
            flash(f"'{values['title']}' added as unshelved, so it isn't on your {im['shelf']}. "
                  f"Rate and review it here.", 'success')
        return redirect(url_for(section.endpoint('show'), id=new_id))

    @login_required
    def edit_item(id):
        conn = get_db()
        row = conn.execute("SELECT * FROM books WHERE id = ?", (id,)).fetchone()
        if not row or not (current_user.is_admin or row['added_by'] == current_user.id):
            abort(404)
        kind = media.media_type_of(row)
        if kind != m_type:
            return redirect(url_for(media.item_endpoint(kind, 'edit'), id=id))
        from blueprints.books import _book_tools_context

        def page(values, status=200):
            # Worded by the kind on the form (a re-shown POST) or the row's
            return render_template('media_form.html', video=row, values=values,
                                   m=section.item_m(values), formats=section.formats,
                                   **_book_tools_context(conn, row)), status

        if request.method == 'GET':
            values = dict(row)
            values['barcode_input'] = row['barcode'] or ''
            return page(values)

        values, errors = section.form_values(request.form)
        if errors:
            for error in errors:
                flash(error, 'error')
            return page(values, status=400)

        cover = row['cover_image_url']
        upload = request.files.get('image')
        cropped = cover_crop.crop_or_flash(request.form, [cover])
        if cropped:
            if cover:
                delete_image_file(cover)
            cover = cropped
        elif upload and upload.filename:
            new_cover = process_image(upload)
            if new_cover:
                if cover and cover != new_cover:
                    delete_image_file(cover)
                cover = new_cover
        conn.execute('''
            UPDATE books SET title = ?, subtitle = ?, author = ?, publisher = ?, publish_year = ?,
                   runtime_minutes = ?, format = ?, barcode = ?, catalog_number = ?, genre = ?,
                   description = ?, cover_image_url = ?, video_kind = ?, season = ?
            WHERE id = ? AND media_type = ?
        ''', (values['title'], values['subtitle'], values['author'], values['publisher'],
              values['publish_year'], values['runtime_minutes'], values['format'], values['barcode'],
              values['catalog_number'], values['genre'], values['description'], cover,
              values['video_kind'], values['season'], id, m_type))
        conn.commit()
        flash(f"{section.item_m(values)['Noun']} updated.", 'success')
        return redirect(url_for(section.endpoint('show'), id=id))

    @login_required
    def check_duplicates():
        """For the add page (add_item.js), after a lookup or pick: is this
        already on the household's shelf?"""
        data = request.get_json(silent=True) or {}
        try:
            dups = section.find_duplicates(
                get_db(), current_user.id,
                barcode=(data.get('barcode') or '').strip(),
                title=(data.get('title') or '').strip(),
                author=(data.get('author') or '').strip(),
                catalog_number=(data.get('catalog_number') or '').strip())
        except Exception:
            current_app.logger.exception('Error checking %s duplicates', m_type)
            return jsonify({'success': False, 'error': "Couldn't check for duplicates."}), 500
        return jsonify({'success': True, 'has_duplicates': bool(dups), 'duplicates': [
            {'id': d['id'], 'title': d['title'], 'owner': d['owner'], 'format': d['format'],
             'format_label': d['format_label'], 'removed': d['removed'],
             'url': url_for(section.endpoint('show'), id=d['id']),
             'match_reason': d['match_reason']} for d in dups]})

    bp.add_url_rule('/', 'index', index)
    bp.add_url_rule('/shared', 'shared', shared)
    bp.add_url_rule('/friends', 'friends', friends)
    bp.add_url_rule('/user/<username>', f'user_{item}s', user_items)
    bp.add_url_rule('/<int:id>', f'show_{item}', show_item)
    bp.add_url_rule('/add', f'add_{item}', add_item, methods=['GET', 'POST'])
    bp.add_url_rule('/edit/<int:id>', f'edit_{item}', edit_item, methods=['GET', 'POST'])
    bp.add_url_rule('/check_duplicates', 'check_duplicates', check_duplicates, methods=['POST'])
    return bp


def section_for(media_type) -> Optional[Section]:
    """The Section of a media type (None for books, which have their own
    blueprint). Imported late: videos.py and records.py import this module."""
    from blueprints.records import RECORDS
    from blueprints.videos import VIDEOS
    return {media.VIDEO: VIDEOS, media.RECORD: RECORDS}.get(media_type)
