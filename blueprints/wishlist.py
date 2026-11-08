from flask import render_template, redirect, url_for, request, flash, Blueprint, current_app, jsonify
from utils import media
from flask_login import login_required, current_user
from utils.database import get_db
from models import other_users_with_book_data, can_view_book
from utils.book_utils import process_image, find_duplicates
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
    wishlist_books = _wishlist_rows(conn, target_user_id)

    return render_template(
        "user_wishlist.html",
        wishlist_books=wishlist_books,
        target_username=username,
        target_user=target_user
    )


def _wishlist_rows(conn, user_id):
    """A user's wishlist, newest first: books rows plus the wishlist note."""
    return conn.execute("""
        SELECT b.*, w.wishlist_id, w.notes, w.added_at as wishlist_added_at
        FROM wishlist w
        JOIN books b ON w.book_id = b.id
        WHERE w.user_id = ?
        ORDER BY w.added_at DESC
    """, (user_id,)).fetchall()


@wishlist_blueprint.route("/view", methods=["GET", "POST"])
@login_required
def view_wishlist():
    """Your wishlist: books and movies, in separate sections, with tabs on
    top (?show=books|movies, default both). Adding happens on the shared add
    page (add_to_wishlist), opened from the + button; a POST here is the old
    form's address and is handled the same way."""
    if request.method == "POST":
        return add_to_wishlist()
    show = request.args.get("show")
    show = show if show in WISHLIST_TABS else "both"
    rows = _wishlist_rows(get_db(), current_user.id)
    return render_template(
        "wishlist.html",
        show=show,
        wishlist_books=[r for r in rows if media.media_type_of(r) == media.BOOK],
        wishlist_movies=[r for r in rows if media.media_type_of(r) == media.VIDEO],
    )


# The wishlist page's tabs, in order
WISHLIST_TABS = ("books", "movies", "both")


@wishlist_blueprint.route("/add", methods=["GET", "POST"])
@login_required
def add_to_wishlist():
    """Add a book or movie to your wishlist: the shared add page
    (templates/add_item.html) with a note field, pointed here.

    GET ?type=book|video (&format=, &barcode= for movies). POST is the form;
    for books, also the ISBN box's no-JS lookup (isbn_lookup)."""
    kind = request.values.get("type") or request.form.get("media_type") or media.BOOK
    if kind == media.VIDEO:
        return _add_movie()
    return _add_book()


def _add_book():
    from blueprints.books import render_add_book
    conn = get_db()
    if request.method == "POST" and "isbn_lookup" not in request.form:
        isbn = request.form.get("isbn")
        # Only your own books are reused (utils/book_matching.py)
        book_id, kind = own_book_for_wishlist(conn, current_user.id, isbn)
        if kind == 'library':
            flash("That book is already in your library.", "error")
            return redirect(url_for("books.show_book", id=book_id))
        if not book_id:
            cover_image_url = process_image(request.files.get("image"),
                                            request.form.get("existing_cover_url"))
            page_count = request.form.get("page_count", type=int) or 0
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
                max(0, page_count),
                cover_image_url,
                request.form.get("description", ""),
                request.form.get("subtitle", ""),
                request.form.get("genre", ""),
                current_user.id
            ))
            book_id = cursor.lastrowid
        return _add_wishlist_row(conn, book_id, "Book")
    # The page, or the ISBN box's no-JS lookup
    return render_add_book(destination="wishlist")


def _add_movie():
    from blueprints.videos import _add_page, _form_values
    conn = get_db()
    if request.method == "GET":
        fmt = request.args.get("format")
        values = {"format": fmt if fmt in media.VIDEO_FORMATS else media.DEFAULT_VIDEO_FORMAT,
                  "barcode_input": media.normalize_barcode(request.args.get("barcode")) or ""}
        return _add_page(values, destination="wishlist")

    values, errors = _form_values(request.form)
    values["notes"] = request.form.get("notes", "")
    if errors:
        for error in errors:
            flash(error, "error")
        return _add_page(values, destination="wishlist", status=400)
    # Your own copy with this barcode: on your shelf already, or wished
    if values["barcode"]:
        mine = conn.execute("""
            SELECT b.id, b.removed_at,
                   EXISTS (SELECT 1 FROM wishlist w WHERE w.book_id = b.id AND w.user_id = ?) AS wished
            FROM books b WHERE b.added_by = ? AND b.media_type = 'video' AND b.barcode = ?
        """, (current_user.id, current_user.id, values["barcode"])).fetchall()
        for row in mine:
            if row["wished"]:
                flash("This movie is already on your wishlist!", "error")
                return redirect(url_for("wishlist.view_wishlist"))
            if row["removed_at"] is None:
                flash("That movie is already in your collection.", "error")
                return redirect(url_for("videos.show_video", id=row["id"]))
    cover = process_image(request.files.get("image"), request.form.get("existing_cover_url"))
    cursor = conn.execute("""
        INSERT INTO books (title, subtitle, author, publisher, publish_year, runtime_minutes,
                           format, barcode, catalog_number, genre, description, cover_image_url,
                           page_count, added_by, media_type)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, 'video')
    """, (values['title'], values['subtitle'], values['author'], values['publisher'],
          values['publish_year'], values['runtime_minutes'], values['format'], values['barcode'],
          values['catalog_number'], values['genre'], values['description'], cover, current_user.id))
    return _add_wishlist_row(conn, cursor.lastrowid, "Movie")


def _add_wishlist_row(conn, book_id, noun):
    try:
        conn.execute("INSERT INTO wishlist (user_id, book_id, notes) VALUES (?, ?, ?)",
                     (current_user.id, book_id, request.form.get("notes", "")))
        conn.commit()
        flash(f"{noun} added to your wishlist!", "success")
    except Exception as e:
        conn.rollback()  # undo a half-done insert (e.g. book added, wishlist row failed)
        if "UNIQUE constraint failed" in str(e):
            flash(f"This {noun.lower()} is already on your wishlist!", "error")
        else:
            current_app.logger.exception('Error adding to wishlist')
            flash("Couldn't add it to your wishlist.", "error")
    return redirect(url_for("wishlist.view_wishlist"))


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


@wishlist_blueprint.route("/move_to_library/<int:book_id>", methods=["POST"])
@login_required
def move_to_library(book_id):
    """You got it: a wishlist item moves onto your shelf (the Library for a
    book, Movies for a movie), marked want to read / want to watch."""
    conn = get_db()
    entry = conn.execute("""
        SELECT b.media_type FROM wishlist w JOIN books b ON b.id = w.book_id
        WHERE w.user_id = ? AND w.book_id = ?
    """, (current_user.id, book_id)).fetchone()

    if not entry:
        flash("That isn't on your wishlist.", "error")
        return redirect(url_for("wishlist.view_wishlist"))
    is_movie = entry["media_type"] == media.VIDEO

    try:
        existing = conn.execute("""
            SELECT 1 FROM collections
            WHERE user_id = ? AND book_id = ?
        """, (current_user.id, book_id)).fetchone()
        if not existing:
            conn.execute("""
                INSERT INTO collections (user_id, book_id, status, created_at, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """, (current_user.id, book_id, 'want to watch' if is_movie else 'want to read'))
        conn.execute("DELETE FROM wishlist WHERE user_id = ? AND book_id = ?",
                     (current_user.id, book_id))
        conn.commit()
    except Exception:
        conn.rollback()
        current_app.logger.exception('Error moving a wishlist item to the shelf')
        flash("Couldn't move it off your wishlist.", "error")
        return redirect(url_for("wishlist.view_wishlist"))

    if is_movie:
        flash("Movie added to your collection!", "success")
        return redirect(url_for("videos.show_video", id=book_id))
    flash("Book added to your library!", "success")
    return redirect(url_for("books.show_book", id=book_id))


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
    book = conn.execute("SELECT added_by, media_type FROM books WHERE id = ?", (book_id,)).fetchone()
    is_movie = bool(book) and book['media_type'] == media.VIDEO
    noun = "Movie" if is_movie else "Book"

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
            shelved_as_read = _keep_as_not_owned(conn, book_id, is_movie)
    conn.commit()

    if book_was_deleted:
        flash(f"{noun} removed from wishlist and deleted.", "success")
    elif shelved_as_read:
        verb = "watched" if is_movie else "read"
        flash(f"{noun} removed from wishlist. You've {verb} it, so it's kept on your "
              f"\"{NOT_OWNED[is_movie]}\" collection with your review.", "success")
    elif removed:
        flash(f"{noun} removed from wishlist.", "success")
    else:
        flash("That isn't on your wishlist.", "error")

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
WATCHED_NOT_OWNED = "Watched but not owned"
NOT_OWNED = {False: READ_NOT_OWNED, True: WATCHED_NOT_OWNED}     # by is_movie


def _keep_as_not_owned(conn, book_id, is_movie=False):
    """Mark the current user's ex-wishlist book removed (not in the library).

    If they've read it (a rating/review or a 'read' status), also put it on
    the READ_NOT_OWNED collection, created on first use; for a movie,
    watched and WATCHED_NOT_OWNED. Returns True if it
    went on that collection. Restoring the book on its page (you bought it
    after all) brings it into the library as usual.
    """
    conn.execute("""
        UPDATE books SET removed_at = CURRENT_TIMESTAMP, removed_note = 'Removed from wishlist; not owned'
        WHERE id = ? AND removed_at IS NULL
    """, (book_id,))
    has_read = conn.execute("""
        SELECT 1 FROM read_data WHERE user_id = ? AND book_id = ?
        UNION SELECT 1 FROM collections WHERE user_id = ? AND book_id = ? AND status = ?
    """, (current_user.id, book_id, current_user.id, book_id,
          media.DONE_STATUS[media.VIDEO if is_movie else media.BOOK])).fetchone()
    if not has_read:
        return False
    name = NOT_OWNED[is_movie]
    conn.execute("INSERT OR IGNORE INTO user_collections (user_id, name) VALUES (?, ?)",
                 (current_user.id, name))
    collection_id = conn.execute("SELECT collection_id FROM user_collections WHERE user_id = ? AND name = ?",
                                 (current_user.id, name)).fetchone()[0]
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
    row = conn.execute("SELECT media_type FROM books WHERE id = ?", (book_id,)).fetchone()
    noun = "Movie" if row and row["media_type"] == media.VIDEO else "Book"
    try:
        conn.execute("""
            INSERT INTO wishlist (user_id, book_id)
            VALUES (?, ?)
        """, (current_user.id, book_id))
        conn.commit()
        flash(f"{noun} added to your wishlist!", "success")
    except Exception as e:
        conn.rollback()  # undo a half-done insert (e.g. book added, wishlist row failed)
        if "UNIQUE constraint failed" in str(e):
            flash(f"This {noun.lower()} is already on your wishlist!", "error")
        else:
            current_app.logger.exception('Error adding to wishlist')
            flash("Couldn't add it to your wishlist.", "error")

    return redirect(request.referrer or url_for("base.index"))
