from flask import render_template, redirect, url_for, request, flash, Blueprint, current_app, jsonify, abort, Response
from flask_login import login_required, current_user
from typing import Optional, Dict, Any
from utils.database import get_db
from utils.book_utils import (
    get_filter_options,
    removed_filter,
    find_duplicates,
    fetch_book_details_from_isbn,
    process_image,
    download_and_save_cover,
    search_google_books,
    search_covers_multiple_sources,
    thumbnail_jpeg,
    ALLOWED_EXTENSIONS,
    MAX_IMAGE_SIZE
)
from utils.image_utils import delete_image_file, is_safe_upload_path
from utils.rate_limiting import limiter
from models import (admin_required, shares_library_with, get_library_members,
                    other_users_with_book_data, can_view_book, circle_ids)

books_blueprint = Blueprint('books', __name__, template_folder='templates')


@books_blueprint.route("/thumbnail")
@login_required
@limiter.limit("600 per hour")
def thumbnail():
    """Search-result cover, fetched server-side (see book_utils.thumbnail_jpeg).

    ?url= must point at Google Books or Open Library; anything else, or no
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
    book_details = None
    search_results = None
    
    if request.method == "POST":
        if "isbn_lookup" in request.form:
            # ISBN search
            isbn = request.form["isbn"]
            book_details = fetch_book_details_from_isbn(isbn)
            if book_details:
                flash(f"Book details fetched from {book_details['source']}", "success")
            else:
                book_details = {"error": "Book not found. Please enter details manually."}
                flash("Book not found. Please enter details manually.", "error")
                
        elif "title_search" in request.form:
            # Title/Author search - use consolidated function
            query = request.form["search_query"]
            search_results = search_google_books(query, max_results=15)
            if not search_results:
                flash("No results found", "error")
                
        elif "barcode_scan" in request.form:
            # Handle barcode scan result
            isbn = request.form["barcode_result"]
            if isbn:
                book_details = fetch_book_details_from_isbn(isbn)
                if book_details:
                    flash(f"Book details fetched from {book_details['source']}", "success")
                else:
                    book_details = {"error": "Book not found. Please enter details manually."}
                    flash("Book not found. Please enter details manually.", "error")
                    
        elif "submit_book" in request.form:
            # Process uploaded image or use downloaded cover
            cover_image_url = process_image(
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

            conn = get_db()
            conn.execute("""
                INSERT INTO books (title, author, publisher, publish_year, isbn,
                                 page_count, cover_image_url, description, subtitle, genre, added_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                request.form["title"],
                request.form["author"],
                request.form["publisher"],
                request.form["year"],
                request.form["isbn"],
                page_count,
                cover_image_url,
                request.form.get("description"),
                request.form["subtitle"],
                request.form["genre"],
                current_user.id
            ))
            conn.commit()

            flash("Book added successfully!", "success")
            return redirect(url_for("base.index"))

    return render_template(
        "add_book.html",
        book_details=book_details,
        search_results=search_results
    )

@books_blueprint.route("/search_books")
@login_required
def search_books():
    """AJAX endpoint for book search - returns JSON for frontend"""
    query = request.args.get("q", "")
    if not query:
        return jsonify({"items": []})

    try:
        current_app.logger.debug(f"Starting search for query: {query}")

        # Use consolidated search function (limits to 6 results for AJAX)
        processed_items = search_google_books(query, max_results=6)

        current_app.logger.debug(f"Found {len(processed_items)} results")

        response = jsonify({"items": processed_items})
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response

    except Exception as e:
        current_app.logger.error(f"Unexpected error in search_books: {str(e)}", exc_info=True)
        return jsonify({"error": "Search failed. Please try again."}), 500

@books_blueprint.route("/fetch_isbn_details")
@login_required
def fetch_isbn_details():
    """AJAX endpoint for barcode scanner - fetches book by ISBN"""
    isbn = request.args.get("isbn", "")
    if not isbn:
        return jsonify({"success": False, "error": "No ISBN provided"})

    try:
        current_app.logger.debug(f"Fetching book details for ISBN: {isbn}")

        # Use existing ISBN fetch function
        book_details = fetch_book_details_from_isbn(isbn)

        if book_details:
            current_app.logger.info(f"Successfully fetched book: {book_details.get('title')}")
            return jsonify({"success": True, "book_details": book_details})
        else:
            current_app.logger.warning(f"No book found for ISBN: {isbn}")
            return jsonify({"success": False, "error": "Book not found"})

    except Exception as e:
        current_app.logger.error(f"Error fetching ISBN details: {str(e)}")
        return jsonify({"success": False, "error": "Something went wrong. Please try again."})

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
            isbn=(data.get("isbn") or "").strip())
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

        # Download and save cover image first
        local_cover_url = None
        if thumbnail_url:
            current_app.logger.info(f"Attempting to download cover from: {thumbnail_url}")
            local_cover_url = download_and_save_cover(thumbnail_url)
            if not local_cover_url:
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
@admin_required
def fetch_cover():
    """Fetch high-resolution cover images for a book by ISBN or title/author.

    Searches multiple sources and returns all found covers for user selection.
    """
    try:
        data = request.get_json()
        isbn = data.get("isbn", "").strip()
        title = data.get("title", "").strip()
        author = data.get("author", "").strip()

        current_app.logger.debug(f"Fetching covers - ISBN: {isbn}, Title: {title}, Author: {author}")

        # Search multiple sources for covers
        cover_candidates = search_covers_multiple_sources(isbn=isbn, title=title, author=author)

        if not cover_candidates:
            return jsonify({
                "success": False,
                "error": "No covers found from any source"
            })

        current_app.logger.info(f"Found {len(cover_candidates)} cover candidates from various sources")

        # Try to download all covers and return them for user selection
        downloaded_covers = []
        for cover_url, source, priority in cover_candidates:
            current_app.logger.info(f"Attempting to download from {source} (priority {priority}): {cover_url}")

            local_cover_url = download_and_save_cover(cover_url)

            if local_cover_url:
                current_app.logger.info(f"Successfully downloaded cover from {source}")
                downloaded_covers.append({
                    "url": local_cover_url,
                    "source": source,
                    "priority": priority
                })
            else:
                current_app.logger.warning(f"Failed to download from {source}, skipping...")

        if not downloaded_covers:
            return jsonify({
                "success": False,
                "error": f"Failed to download covers from {len(cover_candidates)} sources"
            })

        # Return all downloaded covers for user selection
        return jsonify({
            "success": True,
            "covers": downloaded_covers,
            "total_found": len(cover_candidates),
            "total_downloaded": len(downloaded_covers)
        })

    except Exception as e:
        current_app.logger.error(f"Error fetching cover: {str(e)}")
        return jsonify({"success": False, "error": "Something went wrong. Please try again."})
        
@books_blueprint.route("/edit/<int:id>", methods=["GET", "POST"])
@login_required
def edit_book(id):
    conn = get_db()
    # Get the book to check who added it
    book = conn.execute("SELECT * FROM books WHERE id = ?", (id,)).fetchone()

    if not book:
        flash("Book not found.", "error")
        return redirect(url_for("base.index"))

    # Allow editing if user is admin or if they added the book
    if not (current_user.is_admin or book['added_by'] == current_user.id):
        flash("You don't have permission to edit this book.", "error")
        return redirect(url_for("base.index"))

    book_details = None

    if request.method == "POST":
        if "isbn_lookup" in request.form:
            isbn = request.form["isbn"]
            book_details = fetch_book_details_from_isbn(isbn)
            if not book_details:
                flash("Book not found. Please enter details manually.", "error")
        else:
            # Get current cover
            current_cover = book['cover_image_url']

            # Check if a cover was fetched via the fetch cover button
            fetched_cover = request.form.get("fetched_cover_url")

            # Priority: uploaded image > fetched cover > existing cover
            if request.files.get("image") and request.files.get("image").filename != '':
                # User uploaded a new image - delete old cover first
                if current_cover:
                    delete_image_file(current_cover)
                cover_image_url = process_image(request.files.get("image"), current_cover)
            elif is_safe_upload_path(fetched_cover):
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

            conn.execute("""
                UPDATE books
                SET title = ?, author = ?, publisher = ?, publish_year = ?,
                    page_count = ?, cover_image_url = ?, description = ?, subtitle = ?, genre = ?
                WHERE id = ?
            """, (
                request.form["title"],
                request.form["author"],
                request.form.get("publisher"),
                request.form.get("year"),
                page_count,
                cover_image_url,
                request.form.get("description", ""),
                request.form["subtitle"],
                request.form["genre"],
                id
            ))
            conn.commit()

            flash("Book updated successfully!", "success")
            return redirect(url_for("base.index"))

    return render_template("edit_book.html", book=book, book_details=book_details,
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
        WHERE uc.user_id = ?
        GROUP BY uc.collection_id, uc.name
    """, (id, current_user.id)).fetchall()

    # Check if book is in user's wishlist
    wishlist_entry = conn.execute("""
        SELECT wishlist_id, notes, added_at
        FROM wishlist
        WHERE user_id = ? AND book_id = ?
    """, (current_user.id, id)).fetchone()

    collection_status = collection_status['status'] if collection_status else 'untracked'

    can_manage = current_user.is_admin or book['added_by'] == current_user.id

    library_member_ids = get_library_members(current_user.id)

    # Get friend reviews for this book
    # Friends are users who share the library with current user or are connected via friend requests
    friend_reviews = []
    if library_member_ids:
        placeholders = ','.join(['?' for _ in library_member_ids])
        friend_reviews = conn.execute(f"""
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

    return render_template(
        "book_detail.html",
        book=book,
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
        friend_reviews=friend_reviews,
        can_manage=can_manage,
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
    flash(f"'{book['title']}' removed from the library. Reviews and reading history are kept.", "success")
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
    flash(f"'{book['title']}' is back in the library.", "success")
    return redirect(url_for('books.show_book', id=id))


@books_blueprint.route("/delete/<int:id>", methods=["POST"])
@login_required
def delete_book(id):
    """Hard delete, for entries that were a mistake (duplicates, bad scans).

    Refused while any other user has their own data on the book, because the
    delete cascades into reviews, statuses and reading history.
    """
    conn = get_db()
    book = conn.execute("SELECT added_by, cover_image_url FROM books WHERE id = ?", (id,)).fetchone()

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
    sort_by = request.args.get("sort_by", "title")
    sort_order = request.args.get("sort_order", "asc")

    valid_columns = {"title", "author", "publish_year", "created_at"}
    valid_orders = {"asc", "desc"}

    if sort_by not in valid_columns:
        sort_by = "title"
    if sort_order not in valid_orders:
        sort_order = "asc"

    # Limit per_page to reasonable values
    per_page = max(12, min(per_page, 100))

    conn = get_db()
    # Get library members to filter books
    library_member_ids = get_library_members(current_user.id)

    # Search only books from current user or their library members
    placeholders = ','.join(['?' for _ in library_member_ids])
    query = f'''
        SELECT b.* FROM library_books b
        WHERE b.added_by IN ({placeholders})
        AND (LOWER(b.title) LIKE LOWER(?) OR LOWER(b.author) LIKE LOWER(?) OR CAST(b.publish_year AS TEXT) LIKE ?)
    '''
    search_like = f"%{search_term}%"
    params = library_member_ids + [search_like, search_like, search_like]

    # Removed (deaccessioned) books are hidden unless asked for
    query += removed_filter(request.args.get('show_removed'))

    # Apply filters if they exist (simplified)
    if request.args.get('genre'):
        query += " AND LOWER(b.genre) = LOWER(?)"
        params.append(request.args.get('genre'))

    if request.args.get('read_status'):
        query += " AND EXISTS (SELECT 1 FROM collections c WHERE c.book_id = b.id AND c.user_id = ? AND c.status = ?)"
        params.extend([current_user.id, request.args.get('read_status')])

    if request.args.get('rating'):
        query += " AND EXISTS (SELECT 1 FROM read_data r WHERE r.book_id = b.id AND r.user_id = ? AND r.rating >= ?)"
        params.extend([current_user.id, int(request.args.get('rating'))])

    tags = request.args.getlist('tags[]')
    if tags:
        # Validate tags exist for this user
        valid_tags_query = 'SELECT DISTINCT tag_name FROM book_tags WHERE user_id = ?'
        valid_tags = [row['tag_name'] for row in conn.execute(valid_tags_query, (current_user.id,)).fetchall()]

        # Filter to only valid tags
        valid_tags_in_request = [tag for tag in tags if tag in valid_tags]
        if valid_tags_in_request:
            placeholders = ','.join(['?' for _ in valid_tags_in_request])
            query += f" AND EXISTS (SELECT 1 FROM book_tags t WHERE t.book_id = b.id AND t.user_id = ? AND t.tag_name IN ({placeholders}))"
            params.append(current_user.id)
            params.extend(valid_tags_in_request)

    # Get total count before pagination
    count_query = query.replace("SELECT b.*", "SELECT COUNT(b.id)")
    total_count = conn.execute(count_query, params).fetchone()[0]

    # Add sorting and pagination
    query += f" ORDER BY b.{sort_by} {sort_order} LIMIT ? OFFSET ?"
    offset = (page - 1) * per_page
    params.extend([per_page, offset])

    # Get paginated books
    books = conn.execute(query, params).fetchall()
    has_more = (offset + len(books)) < total_count

    # Handle AJAX requests for infinite scroll
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        books_data = [{
            'id': book['id'],
            'title': book['title'],
            'author': book['author'],
            'cover_image_url': book['cover_image_url'],
            'removed': book['removed_at'] is not None
        } for book in books]

        return jsonify({
            'books': books_data,
            'total_count': total_count,
            'has_more': has_more,
            'current_page': page
        })

    # Get filter options for the template
    filter_options = get_filter_options(library_member_ids)

    return render_template("search.html",
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