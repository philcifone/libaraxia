from flask import render_template, redirect, url_for, request, flash, Blueprint, current_app, jsonify
from flask_login import login_required, current_user
from utils.database import get_db
from models import other_users_with_book_data, can_view_book
from utils.book_utils import (
    fetch_book_details_from_isbn,
    process_image,
    download_and_save_cover,
    search_google_books,
    find_duplicates,
)
from utils.book_matching import own_book_for_wishlist

wishlist_blueprint = Blueprint('wishlist', __name__, template_folder='templates')


@wishlist_blueprint.route("/user/<username>", methods=["GET"])
@login_required
def view_user_wishlist(username):
    """View another user's wishlist (friends only)"""
    conn = get_db()
    # Get the target user
    target_user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()

    if not target_user:
        flash('User not found!', 'error')
        return redirect(url_for('base.index'))

    target_user_id = target_user['id']
    is_own_wishlist = (target_user_id == current_user.id)

    # If viewing own wishlist, redirect to main wishlist page
    if is_own_wishlist:
        return redirect(url_for('wishlist.view_wishlist'))

    # Check friendship status
    from models import get_friendship_status
    friendship_status = get_friendship_status(current_user.id, target_user_id)

    # Only allow viewing if they are friends
    if friendship_status not in ('self', 'friends'):
        flash('You must be friends to view this wishlist!', 'warning')
        return redirect(url_for('user.profile', username=username))

    # Get wishlist books for the target user
    wishlist_books = conn.execute("""
        SELECT b.*, w.wishlist_id, w.notes, w.added_at as wishlist_added_at
        FROM wishlist w
        JOIN books b ON w.book_id = b.id
        WHERE w.user_id = ?
        ORDER BY w.added_at DESC
    """, (target_user_id,)).fetchall()

    return render_template(
        "user_wishlist.html",
        wishlist_books=wishlist_books,
        target_username=username,
        target_user=target_user
    )


@wishlist_blueprint.route("/view", methods=["GET", "POST"])
@login_required
def view_wishlist():
    """Main wishlist page - shows search interface and current wishlist books"""
    if request.method == "POST":
        # Only handle manual book form submission
        if "submit_book" in request.form:
            # Add book to wishlist
            # First, add to books table if it doesn't exist
            conn = get_db()
            # Check if book already exists by ISBN
            isbn = request.form.get("isbn")
            # Only your own books are reused (utils/book_matching.py)
            book_id, kind = own_book_for_wishlist(conn, current_user.id, isbn)
            if kind == 'library':
                flash("That book is already in your library.", "error")
                return redirect(url_for("books.show_book", id=book_id))
            if not book_id:
                # Process uploaded image or use downloaded cover
                cover_image_url = process_image(
                    request.files.get("image"),
                    request.form.get("existing_cover_url")
                )

                # Insert new book
                cursor = conn.execute("""
                    INSERT INTO books (title, author, publisher, publish_year, isbn,
                                     page_count, cover_image_url, description, subtitle, genre, added_by)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    request.form["title"],
                    request.form["author"],
                    request.form.get("publisher", ""),
                    request.form.get("year", ""),
                    isbn,
                    request.form.get("page_count", 0),
                    cover_image_url,
                    request.form.get("description", ""),
                    request.form.get("subtitle", ""),
                    request.form.get("genre", ""),
                    current_user.id
                ))
                book_id = cursor.lastrowid

            # Add to wishlist
            try:
                conn.execute("""
                    INSERT INTO wishlist (user_id, book_id, notes)
                    VALUES (?, ?, ?)
                """, (current_user.id, book_id, request.form.get("notes", "")))
                conn.commit()
                flash("Book added to wishlist!", "success")
            except Exception as e:
                conn.rollback()  # undo a half-done insert (e.g. book added, wishlist row failed)
                if "UNIQUE constraint failed" in str(e):
                    flash("This book is already in your wishlist!", "error")
                else:
                    current_app.logger.exception('Error adding to wishlist')
                    flash("Couldn't add the book to your wishlist.", "error")

            return redirect(url_for("wishlist.view_wishlist"))

    # Get wishlist books for display
    conn = get_db()
    wishlist_books = conn.execute("""
        SELECT b.*, w.wishlist_id, w.notes, w.added_at as wishlist_added_at
        FROM wishlist w
        JOIN books b ON w.book_id = b.id
        WHERE w.user_id = ?
        ORDER BY w.added_at DESC
    """, (current_user.id,)).fetchall()

    return render_template(
        "wishlist.html",
        wishlist_books=wishlist_books
    )


@wishlist_blueprint.route("/check_duplicates", methods=["POST"])
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


@wishlist_blueprint.route("/select_search_result", methods=["POST"])
@login_required
def select_search_result():
    """Handle selection of a book from search results - directly add to wishlist"""
    try:
        data = request.get_json()
        current_app.logger.debug(f"Received wishlist book selection data: {data}")

        original_data = data.get("bookData", {})
        isbn = original_data.get("isbn")
        thumbnail_url = original_data.get("thumbnail")

        conn = get_db()
        # Only your own books are reused (utils/book_matching.py). Checked
        # before the cover download so a refusal leaves no orphaned file.
        book_id, kind = own_book_for_wishlist(conn, current_user.id, isbn)
        if kind == 'library':
            return jsonify({"success": False, "error": "That book is already in your library."})
        if kind == 'wishlist':
            return jsonify({"success": False, "error": "This book is already in your wishlist!"})

        # Download and save the cover
        local_cover_url = None
        if thumbnail_url:
            current_app.logger.info(f"Attempting to download cover from: {thumbnail_url}")
            local_cover_url = download_and_save_cover(thumbnail_url)
            if not local_cover_url:
                current_app.logger.warning("Failed to download cover image")

        if not book_id:
            # Insert new book
            cursor = conn.execute("""
                INSERT INTO books (title, author, publisher, publish_year, isbn,
                                 page_count, cover_image_url, description, subtitle, genre, added_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                original_data.get("title", ""),
                original_data.get("author", ""),
                original_data.get("publisher", ""),
                original_data.get("publishedDate", "").split("-")[0] if original_data.get("publishedDate") else "",
                isbn,
                original_data.get("pageCount", 0),
                local_cover_url,
                original_data.get("description", ""),
                original_data.get("subtitle", ""),
                original_data.get("genre", ""),
                current_user.id
            ))
            book_id = cursor.lastrowid

        # Add to wishlist
        try:
            conn.execute("""
                INSERT INTO wishlist (user_id, book_id, notes)
                VALUES (?, ?, ?)
            """, (current_user.id, book_id, ""))
            conn.commit()

            # Fetch the complete book data to return
            book = conn.execute("""
                SELECT b.*, w.wishlist_id, w.notes, w.added_at as wishlist_added_at
                FROM wishlist w
                JOIN books b ON w.book_id = b.id
                WHERE w.user_id = ? AND b.id = ?
            """, (current_user.id, book_id)).fetchone()

            if local_cover_url:
                current_app.logger.info(f"Successfully added book to wishlist with local cover: {local_cover_url}")
            else:
                current_app.logger.warning("Book added to wishlist but no cover image was saved")

            return jsonify({
                "success": True,
                "message": "Book added to wishlist!",
                "book": dict(book)
            })

        except Exception as e:
            conn.rollback()  # undo a half-done insert (e.g. book added, wishlist row failed)
            if "UNIQUE constraint failed" in str(e):
                return jsonify({"success": False, "error": "This book is already in your wishlist!"})
            else:
                raise e

    except Exception as e:
        current_app.logger.error(f"Error in select_search_result: {str(e)}")
        return jsonify({"success": False, "error": "Something went wrong. Please try again."})


@wishlist_blueprint.route("/search_books")
@login_required
def search_books():
    """AJAX endpoint for book search - returns JSON for frontend"""
    query = request.args.get("q", "")
    if not query:
        return jsonify({"items": []})

    try:
        current_app.logger.debug(f"Wishlist search for query: {query}")
        processed_items = search_google_books(query, max_results=6)
        current_app.logger.debug(f"Found {len(processed_items)} results")
        response = jsonify({"items": processed_items})
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response

    except Exception as e:
        current_app.logger.error(f"Unexpected error in wishlist search: {str(e)}", exc_info=True)
        return jsonify({"error": "Search failed. Please try again."}), 500


@wishlist_blueprint.route("/fetch_isbn_details")
@login_required
def fetch_isbn_details():
    """AJAX endpoint for barcode scanner - fetches book by ISBN"""
    isbn = request.args.get("isbn", "")
    if not isbn:
        return jsonify({"success": False, "error": "No ISBN provided"})

    try:
        current_app.logger.debug(f"Fetching book details for ISBN: {isbn}")
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


@wishlist_blueprint.route("/move_to_library/<int:book_id>", methods=["POST"])
@login_required
def move_to_library(book_id):
    """Move a book from wishlist to the user's library"""
    conn = get_db()
    # Check if book is in user's wishlist
    wishlist_entry = conn.execute("""
        SELECT wishlist_id FROM wishlist
        WHERE user_id = ? AND book_id = ?
    """, (current_user.id, book_id)).fetchone()

    if not wishlist_entry:
        flash("Book not found in your wishlist.", "error")
        return redirect(url_for("wishlist.view_wishlist"))

    # Add to collections with default status "want to read"
    try:
        # Check if already in collections
        existing = conn.execute("""
            SELECT 1 FROM collections
            WHERE user_id = ? AND book_id = ?
        """, (current_user.id, book_id)).fetchone()

        if not existing:
            conn.execute("""
                INSERT INTO collections (user_id, book_id, status, created_at, updated_at)
                VALUES (?, ?, 'want to read', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """, (current_user.id, book_id))

        # Remove from wishlist
        conn.execute("""
            DELETE FROM wishlist
            WHERE user_id = ? AND book_id = ?
        """, (current_user.id, book_id))

        conn.commit()
        flash("Book added to your library!", "success")

        # Redirect to book detail page
        return redirect(url_for("books.show_book", id=book_id))

    except Exception as e:
        conn.rollback()  # undo a half-done insert (e.g. book added, wishlist row failed)
        current_app.logger.exception('Error moving book to library')
        flash("Couldn't move the book to your library.", "error")
        return redirect(url_for("wishlist.view_wishlist"))


@wishlist_blueprint.route("/remove/<int:book_id>", methods=["POST"])
@login_required
def remove_from_wishlist(book_id):
    """Remove a book from the current user's wishlist.

    The books row itself is deleted only when it is this user's own wishlist
    entry (they added it and wishlisted it) and nobody, including them, has
    any other data on it. Library books and other people's books are never
    deleted from here.
    """
    book_was_deleted = False
    conn = get_db()
    removed = conn.execute(
        "DELETE FROM wishlist WHERE user_id = ? AND book_id = ?",
        (current_user.id, book_id)).rowcount
    book = conn.execute("SELECT added_by FROM books WHERE id = ?", (book_id,)).fetchone()

    shelved_as_read = False
    if removed and book and book['added_by'] == current_user.id:
        if not other_users_with_book_data(conn, book_id, None):
            conn.execute("DELETE FROM books WHERE id = ?", (book_id,))
            book_was_deleted = True
        else:
            # The entry is kept because someone (usually you: a rating from a
            # Goodreads to-read row) has data on it. Without its wishlist row
            # it would count as owned and show up in your library, so mark
            # it removed instead; reviews keep working on removed books.
            shelved_as_read = _keep_as_not_owned(conn, book_id)
    conn.commit()

    if book_was_deleted:
        flash("Book removed from wishlist and deleted.", "success")
    elif shelved_as_read:
        flash(f"Book removed from wishlist. You've read it, so it's kept on your "
              f"\"{READ_NOT_OWNED}\" collection with your review.", "success")
    elif removed:
        flash("Book removed from wishlist.", "success")
    else:
        flash("That book isn't on your wishlist.", "error")

    # Determine where to redirect based on context
    referrer = request.referrer

    # If book was deleted or if we came from wishlist page, go to wishlist
    if book_was_deleted or (referrer and 'wishlist' in referrer):
        return redirect(url_for("wishlist.view_wishlist"))
    # If we came from book detail page or library, go to library
    elif referrer and ('book' in referrer or 'books' in referrer):
        return redirect(url_for("base.index"))
    # Default fallback to wishlist
    else:
        return redirect(url_for("wishlist.view_wishlist"))


# Custom collection for books you've read but don't own, kept when such a book
# leaves your wishlist (see remove_from_wishlist).
READ_NOT_OWNED = "Read but not owned"


def _keep_as_not_owned(conn, book_id):
    """Mark the current user's ex-wishlist book removed (not in the library).

    If they've read it (a rating/review or a 'read' status), also put it on
    the READ_NOT_OWNED collection, created on first use. Returns True if it
    went on that collection. Restoring the book on its page (you bought it
    after all) brings it into the library as usual.
    """
    conn.execute("""
        UPDATE books SET removed_at = CURRENT_TIMESTAMP, removed_note = 'Removed from wishlist; not owned'
        WHERE id = ? AND removed_at IS NULL
    """, (book_id,))
    has_read = conn.execute("""
        SELECT 1 FROM read_data WHERE user_id = ? AND book_id = ?
        UNION SELECT 1 FROM collections WHERE user_id = ? AND book_id = ? AND status = 'read'
    """, (current_user.id, book_id, current_user.id, book_id)).fetchone()
    if not has_read:
        return False
    conn.execute("INSERT OR IGNORE INTO user_collections (user_id, name) VALUES (?, ?)",
                 (current_user.id, READ_NOT_OWNED))
    collection_id = conn.execute("SELECT collection_id FROM user_collections WHERE user_id = ? AND name = ?",
                                 (current_user.id, READ_NOT_OWNED)).fetchone()[0]
    conn.execute("INSERT OR IGNORE INTO collection_books (collection_id, book_id) VALUES (?, ?)",
                 (collection_id, book_id))
    return True


@wishlist_blueprint.route("/update_notes/<int:book_id>", methods=["POST"])
@login_required
def update_notes(book_id):
    """Update notes for a wishlist book"""
    notes = request.form.get("notes", "")

    conn = get_db()
    conn.execute("""
        UPDATE wishlist
        SET notes = ?
        WHERE user_id = ? AND book_id = ?
    """, (notes, current_user.id, book_id))
    conn.commit()
    flash("Notes updated!", "success")

    return redirect(request.referrer or url_for("wishlist.view_wishlist"))


@wishlist_blueprint.route("/quick_add/<int:book_id>", methods=["POST"])
@login_required
def quick_add_to_wishlist(book_id):
    """Quick add an existing book to wishlist (from library view)"""
    conn = get_db()
    # Only books in the user's circle (models.can_view_book)
    if not can_view_book(conn, current_user, book_id):
        flash("Book not found.", "error")
        return redirect(request.referrer or url_for("base.index"))
    try:
        conn.execute("""
            INSERT INTO wishlist (user_id, book_id)
            VALUES (?, ?)
        """, (current_user.id, book_id))
        conn.commit()
        flash("Book added to wishlist!", "success")
    except Exception as e:
        conn.rollback()  # undo a half-done insert (e.g. book added, wishlist row failed)
        if "UNIQUE constraint failed" in str(e):
            flash("This book is already in your wishlist!", "error")
        else:
            current_app.logger.exception('Error adding to wishlist')
            flash("Couldn't add the book to your wishlist.", "error")

    return redirect(request.referrer or url_for("base.index"))
