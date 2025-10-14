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
from models import admin_required

books_blueprint = Blueprint('books', __name__, template_folder='templates')


@books_blueprint.route("/add", methods=["GET", "POST"])
@login_required
@admin_required
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
                    request.form["page_count"],
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
@admin_required
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
@admin_required
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

@books_blueprint.route("/select_search_result", methods=["POST"])
@login_required
@admin_required
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

        # Create book details dictionary
        book_details = {
            "title": original_data.get("title", ""),
            "subtitle": original_data.get("subtitle", ""),
            "author": original_data.get("author", ""),
            "publisher": original_data.get("publisher", ""),
            "year": original_data.get("publishedDate", "").split("-")[0] if original_data.get("publishedDate") else "",
            "isbn": isbn,
            "page_count": original_data.get("pageCount", 0),
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
    """Fetch high-resolution cover image for a book by ISBN or title/author.

    Searches multiple sources and tries to download the best quality cover available.
    """
    try:
        data = request.get_json()
        isbn = data.get("isbn", "").strip()
        title = data.get("title", "").strip()
        author = data.get("author", "").strip()

        current_app.logger.debug(f"Fetching cover - ISBN: {isbn}, Title: {title}, Author: {author}")

        # Search multiple sources for covers
        cover_candidates = search_covers_multiple_sources(isbn=isbn, title=title, author=author)

        if not cover_candidates:
            return jsonify({
                "success": False,
                "error": "No covers found from any source"
            })

        current_app.logger.info(f"Found {len(cover_candidates)} cover candidates from various sources")

        # Try to download covers in priority order
        for cover_url, source, priority in cover_candidates:
            current_app.logger.info(f"Attempting to download from {source} (priority {priority}): {cover_url}")

            local_cover_url = download_and_save_cover(cover_url)

            if local_cover_url:
                current_app.logger.info(f"Successfully downloaded cover from {source}")
                return jsonify({
                    "success": True,
                    "cover_url": local_cover_url,
                    "source": source,
                    "tried_sources": len(cover_candidates)
                })
            else:
                current_app.logger.warning(f"Failed to download from {source}, trying next source...")

        # All attempts failed
        return jsonify({
            "success": False,
            "error": f"Failed to download covers from {len(cover_candidates)} sources"
        })

    except Exception as e:
        current_app.logger.error(f"Error fetching cover: {str(e)}")
        return jsonify({"success": False, "error": str(e)})
        
@books_blueprint.route("/edit/<int:id>", methods=["GET", "POST"])
@login_required
@admin_required
def edit_book(id):
    with get_db_connection() as conn:
        book_details = None

        if request.method == "POST":
            if "isbn_lookup" in request.form:
                isbn = request.form["isbn"]
                book_details = fetch_book_details_from_isbn(isbn)
                if not book_details:
                    flash("Book not found. Please enter details manually.", "error")
            else:
                # Get current cover
                current_cover = conn.execute("SELECT cover_image_url FROM books WHERE id = ?", (id,)).fetchone()[0]

                # Check if a cover was fetched via the fetch cover button
                fetched_cover = request.form.get("fetched_cover_url")

                # Priority: uploaded image > fetched cover > existing cover
                if request.files.get("image") and request.files.get("image").filename != '':
                    # User uploaded a new image
                    cover_image_url = process_image(request.files.get("image"), current_cover)
                elif fetched_cover:
                    # User fetched a new cover
                    cover_image_url = fetched_cover
                else:
                    # Keep existing cover
                    cover_image_url = current_cover

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
                    request.form.get("page_count", 0),
                    cover_image_url,
                    request.form.get("description", ""),
                    request.form["subtitle"],
                    request.form["genre"],
                    id
                ))

                flash("Book updated successfully!", "success")
                return redirect(url_for("base.index"))

        book = conn.execute("SELECT * FROM books WHERE id = ?", (id,)).fetchone()

    return render_template("edit_book.html", book=book, book_details=book_details)

@books_blueprint.route("/book/<int:id>")
@login_required
def show_book(id):
    conn = get_db_connection()
    try:
        # Get book details
        book = conn.execute("SELECT * FROM books WHERE id = ?", (id,)).fetchone()

        # Get reading status
        read_data = conn.execute("""
            SELECT date_read, rating, comment
            FROM read_data
            WHERE user_id = ? AND book_id = ?
        """, (current_user.id, id)).fetchone()

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

        return render_template(
            "book_detail.html",
            book=book,
            read_data=read_data,
            collection_status=collection_status,
            custom_collections=custom_collections,
            wishlist_entry=wishlist_entry,
            in_wishlist=wishlist_entry is not None
        )
    finally:
        conn.close()

@books_blueprint.route("/delete/<int:id>")
@login_required
@admin_required
def delete_book(id):
    with get_db_connection() as conn:
        conn.execute("DELETE FROM books WHERE id = ?", (id,))
    return redirect(url_for('base.index'))

@books_blueprint.route("/search", methods=["GET"])
@login_required
def search():
    # Get search term
    search_term = request.args.get("search_term", "").lower()
    
    # Get sort parameters with validation
    sort_by = request.args.get("sort_by", "title")
    sort_order = request.args.get("sort_order", "asc")

    valid_columns = {"title", "author", "publish_year", "created_at"}
    valid_orders = {"asc", "desc"}

    if sort_by not in valid_columns:
        sort_by = "title"
    if sort_order not in valid_orders:
        sort_order = "asc"

    # Build the base query
    query = '''
        SELECT DISTINCT b.* FROM books b
        LEFT JOIN collections c ON b.id = c.book_id AND c.user_id = ?
        LEFT JOIN read_data r ON b.id = r.book_id AND r.user_id = ?
        LEFT JOIN book_tags t ON b.id = t.book_id AND t.user_id = ?
        LEFT JOIN wishlist w ON b.id = w.book_id AND w.user_id = ?
        WHERE (b.title LIKE ? OR b.author LIKE ? OR b.publish_year LIKE ?)
        AND w.wishlist_id IS NULL
    '''
    params = [current_user.id, current_user.id, current_user.id, current_user.id]
    search_like = f"%{search_term}%"
    params.extend([search_like, search_like, search_like])
    
    # Apply filters if they exist
    if request.args.get('genre'):
        query += " AND b.genre = ?"
        params.append(request.args.get('genre'))
    
    if request.args.get('read_status'):
        query += " AND c.status = ?"
        params.append(request.args.get('read_status'))
    
    if request.args.get('rating'):
        query += " AND r.rating = ?"
        params.append(request.args.get('rating'))
    
    tags = request.args.getlist('tags[]')
    if tags:
        # Only use tags from the database
        valid_tags_query = '''
            SELECT DISTINCT tag_name FROM book_tags WHERE user_id = ?
        '''
        conn = get_db_connection()
        valid_tags = [row['tag_name'] for row in conn.execute(valid_tags_query, (current_user.id,)).fetchall()]
        conn.close()

        # Filter to only include valid tags
        valid_tags_in_request = [tag for tag in tags if tag in valid_tags]
        if valid_tags_in_request:
            placeholders = ','.join(['?' for _ in valid_tags_in_request])
            query += f" AND t.tag_name IN ({placeholders})"
            params.extend(valid_tags_in_request)
    
    # Add sorting
    query += f" ORDER BY {sort_by} {sort_order}"

    # Execute query
    conn = get_db_connection()
    try:
        books = conn.execute(query, params).fetchall()
        
        # Get filter options for the template
        filter_options = get_filter_options()
        
        return render_template("search.html",
                             books=books,
                             filter_options=filter_options,
                             sort_by=sort_by,
                             sort_order=sort_order,
                             search_term=search_term)
    finally:
        conn.close()