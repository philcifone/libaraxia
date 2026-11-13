import json
from flask import render_template, redirect, url_for, request, flash, Blueprint, current_app, jsonify, abort, Response, stream_with_context
from flask_login import login_required, current_user
from typing import Optional, Dict, Any
from utils.database import get_db
from utils.book_utils import (
    card_json,
    get_filter_options,
    show_choice,
    off_shelf_matches,
    wishlist_matches,
    find_duplicates,
    fetch_book_details_from_isbn,
    process_image,
    google_cover_candidates,
    fetch_cover_by_isbn_direct,
    save_best_cover,
    search_books_page,
    cover_search_steps,
    thumbnail_jpeg,
    ALLOWED_EXTENSIONS,
    MAX_IMAGE_SIZE
)
from utils import cover_crop, media_covers
from utils.image_utils import delete_image_file, is_safe_upload_path
from utils.rate_limiting import limiter
from models import (admin_required, shares_library_with, get_library_members,
                    other_users_with_book_data, can_view_book, circle_ids)
from utils import grid_query, media, sorting
from utils.reviews import then_review_values
from utils.search import by_arg, next_page, page_arg

books_blueprint = Blueprint('books', __name__, template_folder='templates')


@books_blueprint.route("/thumbnail")
@login_required
@limiter.limit("600 per hour")
def thumbnail():
    """Search-result cover, fetched server-side (see book_utils.thumbnail_jpeg).

    ?url= must point at Google Books, Open Library or TMDb; anything else, or no
    usable image, is a 404 and the page shows its no-cover image instead.
    """
    data = thumbnail_jpeg(request.args.get("url", ""))
    if data is None:
        abort(404)
    response = Response(data, mimetype="image/jpeg")
    response.headers["Cache-Control"] = "private, max-age=86400"
    return response


@books_blueprint.route("/add", methods=["GET", "POST"])
@login_required
def add_book():
    """Add a book (templates/add_item.html, shared with Add Movie and the
    wishlist's add page).

    The page's lookups run in add_item.js. Two POSTs land here: the form
    itself (submit_book), and the ISBN box's plain-form fallback
    (isbn_lookup), which re-renders the page filled in, on the ISBN tab.
    """
    if request.method == "POST" and "submit_book" in request.form:
        conn = get_db()
        # A copy already on the household's shelf needs "Add it anyway"
        # ticked, like Add Movie. Wishlist-only matches stay a warning: adding
        # a book you wished for is the normal "I bought it" case.
        on_shelf = [d for d in find_duplicates(conn, current_user.id,
                                               request.form.get("title", ""),
                                               request.form.get("author", ""),
                                               request.form.get("isbn", ""),
                                               request.form.get("subtitle", ""))
                    if d["in_library"]]
        if on_shelf and not request.form.get("confirm_duplicate"):
            flash("This looks like a book already on your household's shelf. "
                  "Tick \"Add it anyway\" if it's a second copy.", "error")
            values = request.form.to_dict()
            # Keep a looked-up cover only if it's one of ours (an upload is
            # lost on the re-render, as on any refused form)
            if not is_safe_upload_path(values.get("existing_cover_url")):
                values["existing_cover_url"] = ""
            return render_add_book(values=values, duplicates=on_shelf, status=400)

        # A crop (15.3) wins; else the uploaded image or the downloaded cover
        cover_image_url = cover_crop.crop_or_flash(
            request.form, [request.form.get("existing_cover_url")]) or process_image(
            request.files.get("image"),
            request.form.get("existing_cover_url")
        )

        # Sanitize page_count: convert to integer or default to 0 if invalid
        page_count_raw = request.form.get("page_count", "").strip()
        try:
            page_count = int(page_count_raw) if page_count_raw else 0
            # Ensure non-negative
            page_count = max(0, page_count)
        except (ValueError, TypeError):
            current_app.logger.warning(f"Invalid page_count value: {page_count_raw}, defaulting to 0")
            page_count = 0

        # "I don't own this" (8B.3): kept off the shelf, there for its review
        owned = not request.form.get("not_owned")
        cursor = conn.execute("""
            INSERT INTO books (title, author, publisher, publish_year, isbn,
                             page_count, cover_image_url, description, subtitle, genre, added_by, owned,
                             format)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            request.form["title"],
            request.form["author"],
            request.form.get("publisher", ""),
            request.form.get("year", ""),
            request.form.get("isbn", ""),
            page_count,
            cover_image_url,
            request.form.get("description"),
            request.form.get("subtitle", ""),
            request.form.get("genre", ""),
            current_user.id,
            1 if owned else 0,
            media.book_format(request.form.get("format")),   # Book (NULL) or Audiobook
        ))
        conn.commit()

        if request.form.get("then") == "review":
            # From Reviews' "Add it as not owned" (ROADMAP 13): on to the review
            flash(f"Book added{'' if owned else ' as unshelved'}. Now your review.", "success")
            return redirect(url_for("read.rate_review", book_id=cursor.lastrowid, **{"from": "reviews"}))
        if not owned:
            # The library won't show it, so go to its page, where the review is
            flash("Book added as unshelved, so it isn't on your shelf. Rate and review it here.", "success")
            return redirect(url_for("books.show_book", id=cursor.lastrowid))
        flash("Book added successfully!", "success")
        return redirect(url_for("base.index"))

    return render_add_book()


def render_add_book(destination="shelf", values=None, duplicates=(), status=200):
    """The Add Book page, for the Library or (destination="wishlist") the
    wishlist. Also answers the ISBN box's no-JS lookup (POST isbn_lookup):
    the page again, filled in, on the ISBN tab. `values` and `duplicates`
    re-render a refused submit (add_book)."""
    to_wishlist = destination == "wishlist"
    if values is not None:
        cover = values.get("existing_cover_url")
        return _add_book_page(values, destination,
                              cover_url=url_for("static", filename=cover) if cover else None,
                              isbn="", duplicates=duplicates), status
    book_details = None
    # ?isbn= (from Do I have this?): the ISBN tab, filled in; the page looks it up
    isbn = request.args.get("isbn", "").strip() if request.method == "GET" else ""
    if request.method == "POST" and "isbn_lookup" in request.form:
        isbn = request.form.get("isbn", "").strip()
        if media.classify_code(isbn) == media.VIDEO:
            flash("That's a movie barcode, not an ISBN: add it here instead.", "info")
            barcode = media.normalize_barcode(isbn)
            return redirect(url_for("wishlist.add_to_wishlist", type=media.VIDEO, barcode=barcode)
                            if to_wishlist else url_for("videos.add_video", barcode=barcode))
        book_details = fetch_book_details_from_isbn(isbn)
        if book_details:
            flash(f"Book details fetched from {book_details['source']}", "success")
        else:
            flash("Book not found. Please enter details manually.", "error")

    values = book_details or {}
    if request.method == "GET":
        # A title from Do I have this? (13b), when it had no ISBN
        if not isbn:
            values.update(media.add_prefill(request.args))
        # From Reviews' "Add it as not owned" (ROADMAP 13)
        values.update(then_review_values(request.args))
    # Preview: the cover the lookup saved, else its remote thumbnail (proxied)
    cover_url = None
    if values.get("local_cover_url"):
        cover_url = url_for("static", filename=values["local_cover_url"])
    elif values.get("thumbnail_url"):
        cover_url = url_for("books.thumbnail", url=values["thumbnail_url"])
    return _add_book_page(values, destination, cover_url=cover_url, isbn=isbn)


def _add_book_page(values, destination, cover_url, isbn, duplicates=()):
    """Render add_item.html for a book (see render_add_book)."""
    to_wishlist = destination == "wishlist"
    target = url_for("wishlist.add_to_wishlist") if to_wishlist else url_for("books.add_book")
    return render_template(
        "add_item.html",
        m=media.media_labels(media.BOOK),
        values=values,
        duplicates=duplicates,
        active_method="code" if isbn else "search",
        search_enabled=True,
        code_value=isbn,
        cover_url=cover_url,
        destination=destination,
        form_action=target,
        code_action=target,
        back_url=url_for("wishlist.view_wishlist") if to_wishlist else url_for("base.index"),
        back_label="Wishlist" if to_wishlist else "Library",
        other_add_url=(url_for("wishlist.add_to_wishlist", type=media.VIDEO) if to_wishlist
                       else url_for("videos.add_video")),
        # A non-ISBN barcode could be a movie or an album: Add Book offers both
        music_add_url=(url_for("wishlist.add_to_wishlist", type=media.RECORD) if to_wishlist
                       else url_for("records.add_record")),
        notes="" if to_wishlist else None,
    )

@books_blueprint.route("/search_books")
@login_required
def search_books():
    """Add Book's Search tab: {"items": [...], "next": {...} | null}, one page
    (BOOK_PAGE) of Google Books results (Open Library when Google is down or
    has nothing). "X by Y" is title X by author Y; `next` is the parameters
    for "Show more" (page, by, src), utils.search.next_page."""
    query = (request.args.get("q") or "").strip()[:200]
    if not query:
        return jsonify({"items": [], "next": None})
    page = page_arg(request.args)
    source = "openlibrary" if request.args.get("src") == "ol" else None
    try:
        items, more, by, source = search_books_page(query, page, by_arg(request.args), source)
    except Exception:
        current_app.logger.exception("Book search failed")
        return jsonify({"error": "Search failed. Please try again."}), 500
    keep = {"by": by, "src": "ol" if source == "openlibrary" else None}
    return jsonify({"items": items, "next": next_page(page, more, **keep)})

def video_code_response(code):
    """JSON for a scanned/typed code that turned out to be a video barcode
    (not an ISBN): where to add it instead. Shared with the wishlist page."""
    barcode = media.normalize_barcode(code)
    return jsonify({
        "success": False,
        "media_type": media.VIDEO,
        "barcode": barcode,
        "add_url": url_for("videos.add_video", barcode=barcode),
        "error": "That's a movie barcode, not an ISBN.",
    })


@books_blueprint.route("/fetch_barcode_details")
@login_required
def fetch_barcode_details():
    """AJAX endpoint for the scanner and ISBN box: what a code is.

    An ISBN (EAN-13 starting 978/979, or ISBN-10) is looked up as a book:
    {"success", "media_type": "book", "book_details"}. Any other EAN-13 or
    UPC-A is a video: {"success": false, "media_type": "video", "barcode",
    "add_url"} and the page sends the user to the Videos add form. Codes
    that are neither (bad check digit, wrong length) are tried as an ISBN
    anyway, as before, since people type ISBNs with typos the APIs forgive.
    """
    code = request.args.get("code") or request.args.get("isbn") or ""
    if not code:
        return jsonify({"success": False, "error": "No ISBN provided"})
    if media.classify_code(code) == media.VIDEO:
        return video_code_response(code)
    isbn = code

    try:
        current_app.logger.debug(f"Fetching book details for ISBN: {isbn}")

        # Use existing ISBN fetch function
        book_details = fetch_book_details_from_isbn(isbn)

        if book_details:
            current_app.logger.info(f"Successfully fetched book: {book_details.get('title')}")
            return jsonify({"success": True, "media_type": media.BOOK, "book_details": book_details})
        else:
            current_app.logger.warning(f"No book found for ISBN: {isbn}")
            return jsonify({"success": False, "media_type": media.BOOK, "error": "Book not found"})

    except Exception as e:
        current_app.logger.error(f"Error fetching ISBN details: {str(e)}")
        return jsonify({"success": False, "error": "Something went wrong. Please try again."})


@books_blueprint.route("/fetch_isbn_details")
@login_required
def fetch_isbn_details():
    """Old name of fetch_barcode_details (?isbn=), kept so nothing breaks."""
    return fetch_barcode_details()

@books_blueprint.route("/check_duplicates", methods=["POST"])
@login_required
def check_duplicates():
    """Warn before adding a book that's already on the household's shelf or
    your wishlist (same ISBN, or same title and author)."""
    data = request.get_json(silent=True) or {}
    try:
        duplicates = find_duplicates(
            get_db(), current_user.id,
            title=(data.get("title") or "").strip(),
            author=(data.get("author") or "").strip(),
            isbn=(data.get("isbn") or "").strip(),
            subtitle=(data.get("subtitle") or "").strip())
    except Exception:
        current_app.logger.exception("Error checking duplicates")
        return jsonify({"success": False, "error": "Couldn't check for duplicates."}), 500
    return jsonify({"has_duplicates": bool(duplicates), "duplicates": duplicates})


@books_blueprint.route("/select_search_result", methods=["POST"])
@login_required
def select_search_result():
    """Handle selection of a book from search results"""
    try:
        data = request.get_json()
        current_app.logger.debug(f"Received book selection data: {data}")

        original_data = data.get("bookData", {})
        isbn = original_data.get("isbn")
        thumbnail_url = original_data.get("thumbnail")

        # commented out because some books dont have ISBNs
        #if not isbn:
        #    current_app.logger.warning("No ISBN provided in book selection")
        #    return jsonify({"success": False, "error": "No ISBN provided"})

        # Download and save the cover first. The result's thumbnail is Google's
        # 128 px one, so try the large size of the same cover, then Open
        # Library by ISBN, and keep the best (ROADMAP 8F). Every URL goes
        # through the SSRF guard in _fetch_image.
        candidates = google_cover_candidates(thumbnail_url) if thumbnail_url else []
        if isbn:
            candidates += fetch_cover_by_isbn_direct(isbn)
        local_cover_url = save_best_cover(candidates) if candidates else None
        if candidates and not local_cover_url:
            current_app.logger.warning("Failed to download cover image")

        # Sanitize page_count: convert to integer or default to 0 if invalid
        page_count_raw = original_data.get("pageCount", 0)
        try:
            page_count = int(page_count_raw) if page_count_raw else 0
            # Ensure non-negative
            page_count = max(0, page_count)
        except (ValueError, TypeError):
            current_app.logger.warning(f"Invalid pageCount value from API: {page_count_raw}, defaulting to 0")
            page_count = 0

        # Create book details dictionary
        book_details = {
            "title": original_data.get("title", ""),
            "subtitle": original_data.get("subtitle", ""),
            "author": original_data.get("author", ""),
            "publisher": original_data.get("publisher", ""),
            "year": original_data.get("publishedDate", "").split("-")[0] if original_data.get("publishedDate") else "",
            "isbn": isbn,
            "page_count": page_count,
            "description": original_data.get("description", ""),
            "genre": original_data.get("genre", ""),
            "cover_image_url": local_cover_url,  # Use local URL for database
            "local_cover_url": local_cover_url,  # Use for form preview
            "thumbnail_url": thumbnail_url       # Keep original URL as backup
        }

        if local_cover_url:
            current_app.logger.info(f"Successfully processed book with local cover: {local_cover_url}")
        else:
            current_app.logger.warning("No cover image was saved")

        return jsonify({"success": True, "book_details": book_details})

    except Exception as e:
        current_app.logger.error(f"Error in select_search_result: {str(e)}")
        return jsonify({"success": False, "error": "Something went wrong. Please try again."})

@books_blueprint.route("/fetch_cover", methods=["POST"])
@login_required
@limiter.limit("30 per hour")       # each search downloads a dozen or so images
def fetch_cover():
    """"Find a better cover" on the add and edit pages: search every cover
    source for the item, download what they offer, and let the user pick.
    `type` picks the sources: a book (default) by ISBN / title / author
    (book_utils.cover_search_steps); a movie or album by barcode / title /
    creator / year / format (media_covers.cover_search_steps).

    That's a dozen or more HTTP calls, so the answer is streamed as it goes
    (NDJSON, one JSON object per line) and the page shows progress and each
    cover as it arrives (edit_book.js):
      {"type": "step", "phase": "search" | "download", "label", "done", "total"}
      {"type": "cover", "url", "source"}         a downloaded cover, uploads/...
      {"type": "done", "count", "error"?}        always last
    """
    data = request.get_json(silent=True) or {}
    def text(key):
        value = data.get(key)
        return value.strip() if isinstance(value, str) else ""
    media_type = text("type") or media.BOOK
    if media_type not in media.MEDIA_TYPES:
        return jsonify({"success": False, "error": "Unknown media type."}), 400
    isbn, title, author = text("isbn"), text("title"), text("author")
    year = int(text("year")) if text("year").isdigit() and len(text("year")) == 4 else None

    def line(**event):
        return json.dumps(event) + "\n"

    def events():
        count = 0
        try:
            # 1. Ask each source for cover URLs
            if media_type == media.BOOK:
                steps = cover_search_steps(isbn=isbn, title=title, author=author)
            else:
                steps = media_covers.cover_search_steps(media_type, title=title, author=author,
                                                        barcode=text("barcode"), year=year,
                                                        fmt=text("format"))
            candidates, seen = [], set()
            for i, (label, run) in enumerate(steps):
                yield line(type="step", phase="search", label=label, done=i, total=len(steps))
                try:
                    found = run()
                except Exception as e:      # one source failing doesn't end the search
                    current_app.logger.warning(f"Cover source {label} failed: {e.__class__.__name__}")
                    continue
                for url, source in found:
                    if url and url not in seen:
                        seen.add(url)
                        candidates.append((url, source))

            # 2. Download each (through the SSRF guard) and send it as it lands
            for i, (url, source) in enumerate(candidates):
                yield line(type="step", phase="download", label=source, done=i, total=len(candidates))
                # A Google link becomes its large size, then the 128 px one (8F)
                local = save_best_cover(google_cover_candidates(url))
                if local:
                    count += 1
                    yield line(type="cover", url=local, source=source)

            error = None
            if not candidates:
                error = "No covers found from any source."
            elif not count:
                error = f"None of the {len(candidates)} covers found could be downloaded."
            yield line(type="done", count=count, **({"error": error} if error else {}))
        except Exception as e:
            current_app.logger.error(f"Error fetching cover: {e}")
            yield line(type="done", count=count, error="Something went wrong. Please try again.")

    return Response(stream_with_context(events()), mimetype="application/x-ndjson",
                    headers={"Cache-Control": "no-cache",
                             "X-Accel-Buffering": "no"})   # nginx: pass lines on as they come


@books_blueprint.route("/edit/<int:id>", methods=["GET", "POST"])
@login_required
def edit_book(id):
    conn = get_db()
    # Get the book to check who added it
    book = conn.execute("SELECT * FROM books WHERE id = ?", (id,)).fetchone()

    if not book:
        flash("Book not found.", "error")
        return redirect(url_for("base.index"))
    if media.media_type_of(book) != media.BOOK:
        return redirect(url_for(media.item_endpoint(media.media_type_of(book), "edit"), id=id))

    # Allow editing if user is admin or if they added the book
    if not (current_user.is_admin or book['added_by'] == current_user.id):
        flash("You don't have permission to edit this book.", "error")
        return redirect(url_for("base.index"))

    if request.method == "POST":
        # Get current cover
        current_cover = book['cover_image_url']

        # A cover picked with "Find a better cover" (edit_book.js puts its
        # uploads/... path in existing_cover_url; fetched_cover_url is the
        # old field name)
        fetched_cover = request.form.get("existing_cover_url") or request.form.get("fetched_cover_url")

        # Priority: crop > uploaded image > fetched cover > existing cover.
        # The crop may start from this cover, a fetched one or a staged photo.
        cropped = cover_crop.crop_or_flash(
            request.form, [current_cover, fetched_cover if is_safe_upload_path(fetched_cover) else None])
        if cropped:
            if current_cover and current_cover != cropped:
                delete_image_file(current_cover)
            cover_image_url = cropped
        elif request.files.get("image") and request.files.get("image").filename != '':
            # User uploaded a new image - delete old cover first
            if current_cover:
                delete_image_file(current_cover)
            cover_image_url = process_image(request.files.get("image"), current_cover)
        elif fetched_cover and is_safe_upload_path(fetched_cover):
            # User fetched a new cover - delete old cover first
            if current_cover and current_cover != fetched_cover:
                delete_image_file(current_cover)
            cover_image_url = fetched_cover
        else:
            # Keep existing cover
            cover_image_url = current_cover

        # Sanitize page_count: convert to integer or default to 0 if invalid
        page_count_raw = request.form.get("page_count", "").strip()
        try:
            page_count = int(page_count_raw) if page_count_raw else 0
            # Ensure non-negative
            page_count = max(0, page_count)
        except (ValueError, TypeError):
            current_app.logger.warning(f"Invalid page_count value: {page_count_raw}, defaulting to 0")
            page_count = 0

        # The ISBN is saved too: until Phase 8.5 the form showed it but the
        # UPDATE left it out, so corrections were silently dropped.
        conn.execute("""
            UPDATE books
            SET title = ?, author = ?, publisher = ?, publish_year = ?, isbn = ?,
                page_count = ?, cover_image_url = ?, description = ?, subtitle = ?, genre = ?,
                format = ?
            WHERE id = ?
        """, (
            request.form["title"],
            request.form["author"],
            request.form.get("publisher"),
            request.form.get("year"),
            request.form.get("isbn", book['isbn']),
            page_count,
            cover_image_url,
            request.form.get("description", ""),
            request.form.get("subtitle", ""),
            request.form.get("genre", ""),
            media.book_format(request.form.get("format")),
            id
        ))
        conn.commit()

        flash("Book updated successfully!", "success")
        return redirect(url_for("books.show_book", id=id))

    values = dict(book)
    values['existing_cover_url'] = ''     # set only by "Find a better cover"
    return render_template("edit_book.html", book=book, values=values,
                           m=media.media_labels(media.BOOK),
                           **_book_tools_context(conn, book))


def _transfer_candidates(conn):
    """Who the current user may hand a book to: their household (admins:
    anyone, e.g. for unowned books after a user was deleted). The transfer
    route enforces the same rule on POST."""
    if current_user.is_admin:
        return conn.execute('SELECT id, username FROM users ORDER BY username').fetchall()
    member_ids = get_library_members(current_user.id)
    if len(member_ids) <= 1:
        return []
    marks = ','.join('?' * len(member_ids))
    return conn.execute(f'SELECT id, username FROM users WHERE id IN ({marks}) ORDER BY username',
                        member_ids).fetchall()


def _book_tools_context(conn, book):
    """Template data for _book_tools.html (edit page; owner or admin only)."""
    owner = (conn.execute('SELECT username FROM users WHERE id = ?', (book['added_by'],)).fetchone()
             if book['added_by'] is not None else None)
    in_wishlist = conn.execute('SELECT 1 FROM wishlist WHERE user_id = ? AND book_id = ?',
                               (current_user.id, book['id'])).fetchone() is not None
    return {
        'library_members': _transfer_candidates(conn),
        'owner_username': owner['username'] if owner else None,
        # Who else has reviews/history on it: a hard delete is refused while anyone does
        'others_with_data': other_users_with_book_data(conn, book['id'], book['added_by']),
        'in_wishlist': in_wishlist,
    }

@books_blueprint.route("/book/<int:id>")
@login_required
def show_book(id):
    conn = get_db()
    # Get book details
    book = conn.execute("SELECT * FROM books WHERE id = ?", (id,)).fetchone()
    # 404 rather than 403 for books outside the user's circle, so ids
    # can't be probed for existence
    if not book or not can_view_book(conn, current_user, id):
        abort(404)
    # Movies and vinyls have their own page (same template, their wording).
    # Links to /books/book/<id> (feed, collections, old bookmarks) land there.
    if media.media_type_of(book) != media.BOOK:
        return redirect(url_for(media.item_endpoint(media.media_type_of(book)), id=id))
    return render_item_page(conn, book)


def render_item_page(conn, book):
    """The detail page of a book or video the user may see (the caller has
    checked can_view_book). Labels and statuses come from utils/media.py."""
    id = book['id']

    # Someone else's wishlist entry (notes included) for this book, shown
    # only for people in the viewer's circle. ?wishlist_owner=<username>
    # picks whose (links from a friend's wishlist); otherwise the most
    # recent one, so the section also shows when coming from the feed.
    others = [uid for uid in circle_ids(conn, current_user.id) if uid != current_user.id]
    wishlist_owner = request.args.get('wishlist_owner')
    wishlist_owner_entry = None
    wishlist_owner_user = None
    if others:
        marks = ','.join('?' * len(others))
        query = f"""
            SELECT w.wishlist_id, w.notes, w.added_at, u.id, u.username
            FROM wishlist w
            JOIN users u ON w.user_id = u.id
            WHERE w.book_id = ? AND w.user_id IN ({marks})
        """
        entry = None
        if wishlist_owner and wishlist_owner != current_user.username:
            entry = conn.execute(query + " AND u.username = ?",
                                 [id, *others, wishlist_owner]).fetchone()
        if not entry:
            entry = conn.execute(query + " ORDER BY w.added_at DESC LIMIT 1",
                                 [id, *others]).fetchone()
        if entry:
            wishlist_owner_entry = {
                'wishlist_id': entry['wishlist_id'],
                'notes': entry['notes'],
                'added_at': entry['added_at'],
            }
            wishlist_owner_user = {'id': entry['id'], 'username': entry['username']}
            wishlist_owner = entry['username']
        else:
            wishlist_owner = None

    # Get reading status and most recent reading session
    read_data = conn.execute("""
        SELECT rating, comment
        FROM read_data
        WHERE user_id = ? AND book_id = ?
    """, (current_user.id, id)).fetchone()

    # Get all reading sessions (ordered by completion date, oldest first)
    reading_sessions = conn.execute("""
        SELECT session_id, date_started, date_completed, created_at
        FROM reading_sessions
        WHERE user_id = ? AND book_id = ?
        ORDER BY
            -- undated past reads first, then by date, then in progress
            CASE WHEN date_completed IS NULL AND date_started IS NULL THEN 0
                 WHEN date_completed IS NULL THEN 2 ELSE 1 END,
            COALESCE(date_completed, date_started, created_at) ASC,
            created_at ASC
    """, (current_user.id, id)).fetchall()

    # Get the latest session for quick display
    latest_session = reading_sessions[-1] if reading_sessions else None

    collection_status = conn.execute("""
        SELECT status
        FROM collections
        WHERE user_id = ? AND book_id = ?
    """, (current_user.id, id)).fetchone()

    # Get custom collections with book membership status
    custom_collections = conn.execute("""
        SELECT
            uc.collection_id,
            uc.name,
            COUNT(cb2.book_id) as book_count,
            CASE WHEN cb.book_id IS NOT NULL THEN 1 ELSE 0 END as has_book
        FROM user_collections uc
        LEFT JOIN collection_books cb ON uc.collection_id = cb.collection_id
            AND cb.book_id = ?
        LEFT JOIN collection_books cb2 ON uc.collection_id = cb2.collection_id
        -- this section's shelves (8C), and any other shelf it's already on
        WHERE uc.user_id = ? AND (uc.media_type = ? OR cb.book_id IS NOT NULL)
        GROUP BY uc.collection_id, uc.name
        ORDER BY uc.name COLLATE NOCASE
    """, (id, current_user.id, media.media_type_of(book))).fetchall()

    # Check if book is in user's wishlist
    wishlist_entry = conn.execute("""
        SELECT wishlist_id, notes, added_at
        FROM wishlist
        WHERE user_id = ? AND book_id = ?
    """, (current_user.id, id)).fetchone()

    collection_status = collection_status['status'] if collection_status else 'untracked'

    can_manage = current_user.is_admin or book['added_by'] == current_user.id

    library_member_ids = get_library_members(current_user.id)

    # Reviews of this book by the user's household (people who share their
    # library). Friends' reviews aren't here: they hang on the friend's own
    # copy of the book, and show on the friend's profile instead.
    household_reviews = []
    if library_member_ids:
        placeholders = ','.join(['?' for _ in library_member_ids])
        household_reviews = conn.execute(f"""
            SELECT
                u.id,
                u.username,
                u.avatar_url,
                rd.rating,
                rd.comment,
                rs.date_completed,
                c.status as reading_status
            FROM read_data rd
            JOIN users u ON rd.user_id = u.id
            LEFT JOIN collections c ON c.user_id = rd.user_id AND c.book_id = rd.book_id
            LEFT JOIN reading_sessions rs ON rs.user_id = rd.user_id
                AND rs.book_id = rd.book_id
                AND rs.date_completed IS NOT NULL
            WHERE rd.book_id = ?
                AND rd.user_id IN ({placeholders})
                AND rd.user_id != ?
                AND (rd.rating IS NOT NULL OR rd.comment IS NOT NULL)
            GROUP BY u.id
            ORDER BY MAX(rs.date_completed) DESC, u.username ASC
        """, [id] + library_member_ids + [current_user.id]).fetchall()

    # What your Goodreads imports did to this book (ROADMAP 14b): yours only
    goodreads_notes = []
    if media.media_type_of(book) == media.BOOK:
        from utils.goodreads_plan import provenance
        goodreads_notes = provenance(conn, current_user.id, id)

    return render_template(
        "book_detail.html",
        book=book,
        goodreads_notes=goodreads_notes,
        read_data=read_data,
        latest_session=latest_session,
        reading_sessions=reading_sessions,
        collection_status=collection_status,
        custom_collections=custom_collections,
        wishlist_entry=wishlist_entry,
        in_wishlist=wishlist_entry is not None,
        wishlist_owner=wishlist_owner,
        wishlist_owner_user=wishlist_owner_user,
        wishlist_owner_entry=wishlist_owner_entry,
        household_reviews=household_reviews,
        can_manage=can_manage,
        m=media.item_labels(book),
        runtime=media.format_runtime(book['runtime_minutes']),
    )

@books_blueprint.route("/remove/<int:id>", methods=["POST"])
@login_required
def remove_book(id):
    """Deaccession: the book has left the house (given away, sold, lost).

    It disappears from library views but the record stays, with everyone's
    reviews, ratings and reading history. Owner or admin; reversible.
    """
    conn = get_db()
    book = conn.execute("SELECT title, added_by FROM books WHERE id = ?", (id,)).fetchone()
    if not book or not (current_user.is_admin or book['added_by'] == current_user.id):
        flash("You don't have permission to remove this book.", "error")
        return redirect(url_for('base.index'))
    note = (request.form.get('removed_note') or '').strip()[:200] or None
    conn.execute("UPDATE books SET removed_at = CURRENT_TIMESTAMP, removed_note = ? WHERE id = ?", (note, id))
    conn.commit()
    flash(f"'{book['title']}' removed. Reviews and history are kept.", "success")
    return redirect(url_for('books.show_book', id=id))


@books_blueprint.route("/restore/<int:id>", methods=["POST"])
@login_required
def restore_book(id):
    """Undo a removal: the book is back on the shelf."""
    conn = get_db()
    book = conn.execute("SELECT title, added_by FROM books WHERE id = ?", (id,)).fetchone()
    if not book or not (current_user.is_admin or book['added_by'] == current_user.id):
        flash("You don't have permission to restore this book.", "error")
        return redirect(url_for('base.index'))
    conn.execute("UPDATE books SET removed_at = NULL, removed_note = NULL WHERE id = ?", (id,))
    conn.commit()
    flash(f"'{book['title']}' is back on the shelf.", "success")
    return redirect(url_for('books.show_book', id=id))


@books_blueprint.route("/ownership/<int:id>", methods=["POST"])
@login_required
def set_ownership(id):
    """Owned or not (ROADMAP 8B.3), for every media type.

    owned=1: "I own it now" (you bought what you'd read, watched or listened
    to); it goes on the shelf, with your review and history already on it.
    owned=0: "I don't own this" (added by mistake as owned). Either way it's
    no longer removed: removal is for copies that left, not for these.
    Owner or admin.
    """
    owned = 1 if request.form.get('owned') == '1' else 0
    conn = get_db()
    book = conn.execute("SELECT title, added_by, media_type FROM books WHERE id = ?", (id,)).fetchone()
    if not book or not (current_user.is_admin or book['added_by'] == current_user.id):
        flash("You can't change that.", "error")
        return redirect(url_for('base.index'))
    conn.execute("UPDATE books SET owned = ?, removed_at = NULL, removed_note = NULL WHERE id = ?",
                 (owned, id))
    conn.commit()
    m = media.media_labels(book['media_type'])
    where = 'in your library' if book['media_type'] == media.BOOK else f"on your {m['shelf']}"
    if owned:
        flash(f"'{book['title']}' is {where} now.", "success")
    else:
        flash(f"'{book['title']}' is marked unshelved, so it isn't {where}. "
              f"Choose Show: Unshelved in the filters to see it.", "success")
    return redirect(url_for(media.item_endpoint(book['media_type']), id=id))


@books_blueprint.route("/delete/<int:id>", methods=["POST"])
@login_required
def delete_book(id):
    """Hard delete, for entries that were a mistake (duplicates, bad scans).

    Refused while any other user has their own data on the book, because the
    delete cascades into reviews, statuses and reading history.
    """
    conn = get_db()
    book = conn.execute("SELECT added_by, cover_image_url, media_type, video_kind FROM books WHERE id = ?",
                        (id,)).fetchone()

    if not book:
        flash("Book not found.", "error")
        return redirect(url_for('base.index'))

    if not (current_user.is_admin or book['added_by'] == current_user.id):
        flash("You don't have permission to delete this book.", "error")
        return redirect(url_for('base.index'))

    others = other_users_with_book_data(conn, id, book['added_by'])
    if others:
        flash("Can't delete this book: " + ", ".join(others) +
              " has reviews or reading history on it, and deleting would erase them.", "error")
        return redirect(url_for('books.show_book', id=id))

    conn.execute("DELETE FROM books WHERE id = ?", (id,))
    conn.commit()

    # Only after the row is gone, so a failed delete never loses the cover.
    if book['cover_image_url']:
        delete_image_file(book['cover_image_url'])
    kind = media.media_type_of(book)
    if kind != media.BOOK:
        flash(f"{media.item_labels(book)['Noun']} deleted.", "success")
        return redirect(url_for(f"{media.BLUEPRINTS[kind]}.index"))
    flash("Book deleted successfully.", "success")
    return redirect(url_for('base.index'))

@books_blueprint.route("/search", methods=["GET"])
@login_required
def search():
    # Get pagination parameters
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 30, type=int)

    # Get search term
    search_term = request.args.get("search_term", "").strip()

    # Get sort parameters with validation
    sort_by, sort_order = sorting.choice(request.args, media.BOOK)

    # Limit per_page to reasonable values
    per_page = max(12, min(per_page, 100))

    conn = get_db()
    # Get library members to filter books
    library_member_ids = get_library_members(current_user.id)

    # The query is shared with bulk edit's "select all in this view" (utils/grid_query.py)
    query, params, match_sql, match_params = grid_query.search_query(
        conn, library_member_ids, request.args, current_user.id)

    # Get total count before pagination
    count_query = query.replace("SELECT b.*", "SELECT COUNT(b.id)")
    total_count = conn.execute(count_query, params).fetchone()[0]

    # Add sorting and pagination
    order_sql, order_params = sorting.order_by(sort_by, sort_order, current_user.id)
    query += order_sql + " LIMIT ? OFFSET ?"
    offset = (page - 1) * per_page
    params.extend([*order_params, per_page, offset])

    # Get paginated books
    books = conn.execute(query, params).fetchall()
    has_more = (offset + len(books)) < total_count

    # Handle AJAX requests for infinite scroll
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        books_data = card_json(conn, current_user.id, books)   # list view's columns too

        return jsonify({
            'books': books_data,
            'total_count': total_count,
            'has_more': has_more,
            'current_page': page
        })

    # Get filter options for the template
    filter_options = get_filter_options(library_member_ids)

    # "Not on your shelf, but you read it" (8B.3): only on the default Show
    off_shelf = None
    if search_term and not show_choice(request.args):
        off_shelf = off_shelf_matches(conn, 'library_books', library_member_ids,
                                      match_sql, match_params, current_user.id)
    # ...and "it's on your wishlist" (7.2b)
    on_wishlist = wishlist_matches(conn, current_user.id, media.BOOK, match_sql, match_params) if search_term else None

    return render_template("search.html",
                         off_shelf=off_shelf,
                         on_wishlist=on_wishlist,
                         books=books,
                         filter_options=filter_options,
                         sort_by=sort_by,
                         sort_order=sort_order,
                         search_term=search_term,
                         total_count=total_count,
                         has_more=has_more,
                         current_page=page)


@books_blueprint.route("/transfer/<int:book_id>", methods=["POST"])
@login_required
def transfer_book(book_id):
    """Transfer book ownership to another user in the same library group"""
    new_owner_id = request.form.get('new_owner_id', type=int)

    if not new_owner_id:
        flash("Please select a user to transfer the book to", "error")
        return redirect(request.referrer or url_for('base.index'))

    conn = get_db()
    try:
        # Get the book and verify current user owns it
        book = conn.execute(
            'SELECT id, title, added_by FROM books WHERE id = ?',
            (book_id,)
        ).fetchone()

        if not book:
            flash("Book not found", "error")
            return redirect(url_for('base.index'))

        # Only the book's owner (or an admin) can give it away
        if book['added_by'] != current_user.id and not current_user.is_admin:
            flash("You don't have permission to transfer this book", "error")
            return redirect(request.referrer or url_for('base.index'))

        # Owners can only give books within their household; admins to anyone
        if not current_user.is_admin and not shares_library_with(current_user.id, new_owner_id):
            flash("You can only transfer books to users in your library group", "error")
            return redirect(request.referrer or url_for('base.index'))

        # Get new owner's username for flash message
        new_owner = conn.execute(
            'SELECT username FROM users WHERE id = ?',
            (new_owner_id,)
        ).fetchone()

        if not new_owner:
            flash("Invalid user selected", "error")
            return redirect(request.referrer or url_for('base.index'))

        # Transfer the book
        conn.execute(
            'UPDATE books SET added_by = ? WHERE id = ?',
            (new_owner_id, book_id)
        )
        conn.commit()

        flash(f"'{book['title']}' transferred to {new_owner['username']}", "success")
        current_app.logger.info(
            f"User {current_user.username} transferred book '{book['title']}' to {new_owner['username']}"
        )

    except Exception as e:
        current_app.logger.error(f"Error transferring book: {str(e)}")
        flash("Error transferring book", "error")

    return redirect(request.referrer or url_for('base.index'))