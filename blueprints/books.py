from flask import render_template, redirect, url_for, request, flash, Blueprint, current_app, jsonify
from flask_login import login_required, current_user
from typing import Optional, Dict, Any
from utils.database import get_db_connection
from utils.book_utils import (
    get_filter_options,
    fetch_book_details_from_isbn,
    process_image,
    download_and_save_cover,
    search_google_books,
    search_covers_multiple_sources,
    ALLOWED_EXTENSIONS,
    MAX_IMAGE_SIZE
)
from models import admin_required, shares_library_with, get_library_members

books_blueprint = Blueprint('books', __name__, template_folder='templates')


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

            with get_db_connection() as conn:
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
        return jsonify({"error": str(e)}), 500

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
        return jsonify({"success": False, "error": str(e)})

@books_blueprint.route("/check_duplicates", methods=["POST"])
@login_required
def check_duplicates():
    """Check if a book already exists in the library or wishlist"""
    try:
        data = request.get_json()
        title = data.get("title", "").strip()
        isbn = data.get("isbn", "").strip()

        current_app.logger.debug(f"Checking duplicates for title: {title}, ISBN: {isbn}")

        duplicates = []

        with get_db_connection() as conn:
            # Get library members to restrict search scope
            library_member_ids = get_library_members(current_user.id)
            placeholders = ','.join(['?' for _ in library_member_ids])

            # Check for exact title match or ISBN match (only within library scope)
            query_parts = []
            params = library_member_ids.copy()

            if title:
                query_parts.append("LOWER(title) = LOWER(?)")
                params.append(title)

            if isbn:
                if query_parts:
                    query_parts.append("OR isbn = ?")
                else:
                    query_parts.append("isbn = ?")
                params.append(isbn)

            if not query_parts:
                return jsonify({"has_duplicates": False, "duplicates": []})

            query = f"SELECT id, title, author, isbn FROM books WHERE added_by IN ({placeholders}) AND ({' '.join(query_parts)})"
            existing_books = conn.execute(query, params).fetchall()

            for book in existing_books:
                # Check if in library (collections table)
                in_library = conn.execute("""
                    SELECT 1 FROM collections
                    WHERE user_id = ? AND book_id = ?
                """, (current_user.id, book['id'])).fetchone()

                # Check if in wishlist
                in_wishlist = conn.execute("""
                    SELECT 1 FROM wishlist
                    WHERE user_id = ? AND book_id = ?
                """, (current_user.id, book['id'])).fetchone()

                duplicate_info = {
                    "id": book['id'],
                    "title": book['title'],
                    "author": book['author'],
                    "isbn": book['isbn'],
                    "in_library": bool(in_library),
                    "in_wishlist": bool(in_wishlist),
                    "match_reason": []
                }

                # Determine what matched
                if title and book['title'].lower() == title.lower():
                    duplicate_info["match_reason"].append("title")
                if isbn and book['isbn'] == isbn:
                    duplicate_info["match_reason"].append("ISBN")

                duplicates.append(duplicate_info)

        has_duplicates = len(duplicates) > 0
        current_app.logger.info(f"Found {len(duplicates)} potential duplicates")

        return jsonify({
            "has_duplicates": has_duplicates,
            "duplicates": duplicates
        })

    except Exception as e:
        current_app.logger.error(f"Error checking duplicates: {str(e)}")
        return jsonify({"success": False, "error": str(e)})

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
        return jsonify({"success": False, "error": str(e)})

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
        return jsonify({"success": False, "error": str(e)})
        
@books_blueprint.route("/edit/<int:id>", methods=["GET", "POST"])
@login_required
def edit_book(id):
    with get_db_connection() as conn:
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
                        from utils.image_utils import delete_image_file
                        delete_image_file(current_cover)
                    cover_image_url = process_image(request.files.get("image"), current_cover)
                elif fetched_cover:
                    # User fetched a new cover - delete old cover first
                    if current_cover and current_cover != fetched_cover:
                        from utils.image_utils import delete_image_file
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

                flash("Book updated successfully!", "success")
                return redirect(url_for("base.index"))

    return render_template("edit_book.html", book=book, book_details=book_details)

@books_blueprint.route("/book/<int:id>")
@login_required
def show_book(id):
    conn = get_db_connection()
    try:
        # Get book details
        book = conn.execute("SELECT * FROM books WHERE id = ?", (id,)).fetchone()

        # Check if ANY user has this book on their wishlist
        # First, check if there's a specific wishlist_owner parameter from URL
        wishlist_owner = request.args.get('wishlist_owner')
        wishlist_owner_entry = None
        wishlist_owner_user = None

        if wishlist_owner and wishlist_owner != current_user.username:
            # Get the wishlist owner's user info
            wishlist_owner_user = conn.execute(
                "SELECT id, username FROM users WHERE username = ?",
                (wishlist_owner,)
            ).fetchone()

            if wishlist_owner_user:
                # Get the wishlist entry for that user
                wishlist_owner_entry = conn.execute("""
                    SELECT wishlist_id, notes, added_at
                    FROM wishlist
                    WHERE user_id = ? AND book_id = ?
                """, (wishlist_owner_user['id'], id)).fetchone()

        # If no specific wishlist_owner was found, check if ANY user has this on their wishlist
        # This ensures the wishlist section shows when clicking from activity feed
        if not wishlist_owner_entry:
            # Get the first user (excluding current user) who has this book on their wishlist
            any_wishlist_entry = conn.execute("""
                SELECT w.wishlist_id, w.notes, w.added_at, u.id, u.username
                FROM wishlist w
                JOIN users u ON w.user_id = u.id
                WHERE w.book_id = ? AND w.user_id != ?
                ORDER BY w.added_at DESC
                LIMIT 1
            """, (id, current_user.id)).fetchone()

            if any_wishlist_entry:
                wishlist_owner_entry = {
                    'wishlist_id': any_wishlist_entry['wishlist_id'],
                    'notes': any_wishlist_entry['notes'],
                    'added_at': any_wishlist_entry['added_at']
                }
                wishlist_owner_user = {
                    'id': any_wishlist_entry['id'],
                    'username': any_wishlist_entry['username']
                }
                wishlist_owner = any_wishlist_entry['username']

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
                CASE WHEN date_completed IS NULL THEN 1 ELSE 0 END,
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

        # Get library members for transfer functionality
        library_member_ids = get_library_members(current_user.id)
        library_members = []
        if len(library_member_ids) > 1:
            # Get full user info for library members
            placeholders = ','.join(['?' for _ in library_member_ids])
            library_members = conn.execute(
                f'SELECT id, username FROM users WHERE id IN ({placeholders})',
                library_member_ids
            ).fetchall()

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
            library_members=library_members,
            friend_reviews=friend_reviews
        )
    finally:
        conn.close()

@books_blueprint.route("/delete/<int:id>")
@login_required
def delete_book(id):
    with get_db_connection() as conn:
        # Get the book to check who added it and get the cover image
        book = conn.execute("SELECT added_by, cover_image_url FROM books WHERE id = ?", (id,)).fetchone()

        if not book:
            flash("Book not found.", "error")
            return redirect(url_for('base.index'))

        # Allow deletion if user is admin or if they added the book
        if current_user.is_admin or book['added_by'] == current_user.id:
            # Delete the cover image file if it exists
            if book['cover_image_url']:
                from utils.image_utils import delete_image_file
                delete_image_file(book['cover_image_url'])

            conn.execute("DELETE FROM books WHERE id = ?", (id,))
            flash("Book deleted successfully.", "success")
        else:
            flash("You don't have permission to delete this book.", "error")

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

    conn = get_db_connection()
    try:
        # Get library members to filter books
        library_member_ids = get_library_members(current_user.id)

        # Search only books from current user or their library members
        placeholders = ','.join(['?' for _ in library_member_ids])
        query = f'''
            SELECT b.* FROM books b
            WHERE b.added_by IN ({placeholders})
            AND NOT EXISTS (SELECT 1 FROM wishlist w WHERE w.book_id = b.id)
            AND (LOWER(b.title) LIKE LOWER(?) OR LOWER(b.author) LIKE LOWER(?) OR CAST(b.publish_year AS TEXT) LIKE ?)
        '''
        search_like = f"%{search_term}%"
        params = library_member_ids + [search_like, search_like, search_like]

        # Apply filters if they exist (simplified)
        if request.args.get('genre'):
            query += " AND LOWER(b.genre) = LOWER(?)"
            params.append(request.args.get('genre'))

        if request.args.get('read_status'):
            query += " AND EXISTS (SELECT 1 FROM collections c WHERE c.book_id = b.id AND c.user_id = ? AND c.status = ?)"
            params.extend([current_user.id, request.args.get('read_status')])

        if request.args.get('rating'):
            query += " AND EXISTS (SELECT 1 FROM read_data r WHERE r.book_id = b.id AND r.user_id = ? AND r.rating = ?)"
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
                'cover_image_url': book['cover_image_url']
            } for book in books]

            return jsonify({
                'books': books_data,
                'total_count': total_count,
                'has_more': has_more,
                'current_page': page
            })

        # Get filter options for the template
        filter_options = get_filter_options()

        return render_template("search.html",
                             books=books,
                             filter_options=filter_options,
                             sort_by=sort_by,
                             sort_order=sort_order,
                             search_term=search_term,
                             total_count=total_count,
                             has_more=has_more,
                             current_page=page)
    finally:
        conn.close()


@books_blueprint.route("/transfer/<int:book_id>", methods=["POST"])
@login_required
def transfer_book(book_id):
    """Transfer book ownership to another user in the same library group"""
    new_owner_id = request.form.get('new_owner_id', type=int)

    if not new_owner_id:
        flash("Please select a user to transfer the book to", "error")
        return redirect(request.referrer or url_for('base.index'))

    conn = get_db_connection()
    try:
        # Get the book and verify current user owns it or shares library
        book = conn.execute(
            'SELECT id, title, added_by FROM books WHERE id = ?',
            (book_id,)
        ).fetchone()

        if not book:
            flash("Book not found", "error")
            return redirect(url_for('base.index'))

        # Check if current user can transfer (must own it or share library with owner)
        if book['added_by'] != current_user.id and not shares_library_with(current_user.id, book['added_by']):
            flash("You don't have permission to transfer this book", "error")
            return redirect(request.referrer or url_for('base.index'))

        # Check if new owner shares library with current user
        if not shares_library_with(current_user.id, new_owner_id):
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
    finally:
        conn.close()

    return redirect(request.referrer or url_for('base.index'))