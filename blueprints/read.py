from flask import Blueprint, request, render_template, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from utils.database import get_db
from models import can_view_book
from utils import media
from datetime import date, datetime

# Define the blueprint
read_blueprint = Blueprint('read', __name__, template_folder='templates')


def _iso(day):
    """A date as the 'YYYY-MM-DD' text the column holds, or None.

    sqlite3's built-in date adapter (which produced the same text) is
    deprecated since Python 3.12, so convert explicitly."""
    return day.isoformat() if day else None

@read_blueprint.route('/rate_review/<int:book_id>', methods=['GET', 'POST'])
@login_required
def rate_review(book_id):
    conn = get_db()
    # Only books in the user's circle (models.can_view_book)
    if not can_view_book(conn, current_user, book_id):
        abort(404)

    if request.method == 'POST':
        # Get form data
        date_started = request.form.get('date_started')
        date_completed = request.form.get('date_completed')
        rating = request.form.get('rating')
        comment = request.form.get('comment')
        session_id = request.form.get('session_id')  # For editing existing session

        # Validate dates
        date_started_obj = None
        date_completed_obj = None

        if date_started:
            try:
                date_started_obj = datetime.strptime(date_started, '%Y-%m-%d').date()
            except ValueError:
                flash("Invalid start date format.", 'error')
                return redirect(request.url)

        if date_completed:
            try:
                date_completed_obj = datetime.strptime(date_completed, '%Y-%m-%d').date()
            except ValueError:
                flash("Invalid completion date format.", 'error')
                return redirect(request.url)

        # Validate that start date is before completion date
        if date_started_obj and date_completed_obj and date_started_obj > date_completed_obj:
            flash("Start date cannot be after completion date.", 'error')
            return redirect(request.url)

        # Validate rating: 1-5, or none at all for a written review
        # (Goodreads imports have reviews without a rating)
        if rating:
            if not rating.isdigit() or not (1 <= int(rating) <= 5):
                flash("Invalid rating. Please enter a number between 1 and 5.", 'error')
                return redirect(request.url)
            rating = int(rating)
        elif (comment or '').strip():
            rating = None
        else:
            flash("Choose a rating or write a review.", 'error')
            return redirect(request.url)

        # Update or insert reading session
        if session_id:
            # Update existing session
            conn.execute('''
                UPDATE reading_sessions
                SET date_started = ?, date_completed = ?
                WHERE session_id = ? AND user_id = ?
            ''', (_iso(date_started_obj), _iso(date_completed_obj), session_id, current_user.id))
        elif date_started_obj or date_completed_obj:
            # New reading session, only when a date was given: saving a
            # review without dates used to add an empty session every time
            conn.execute('''
                INSERT INTO reading_sessions (user_id, book_id, date_started, date_completed)
                VALUES (?, ?, ?, ?)
            ''', (current_user.id, book_id, _iso(date_started_obj), _iso(date_completed_obj)))

        # Insert or update the review/rating (separate from sessions)
        conn.execute('''
            INSERT INTO read_data (user_id, book_id, rating, comment)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, book_id) DO UPDATE SET
                rating = excluded.rating,
                comment = excluded.comment
        ''', (current_user.id, book_id, rating, comment))

        conn.commit()

        flash("Your rating and review have been saved!", 'success')
        kind = media.media_type_of(conn.execute('SELECT media_type FROM books WHERE id = ?',
                                                (book_id,)).fetchone())
        # Opened from the Reviews section (?from=reviews, ROADMAP 13): back there
        if request.form.get('from') == 'reviews':
            return redirect(url_for('reviews.index', type=kind))
        if kind != media.BOOK:
            return redirect(url_for(media.item_endpoint(kind), id=book_id))
        return redirect(url_for('base.index', collection_type='read'))

    # Fetch book details and existing read data
    book_query = '''
        SELECT id, title, author, cover_image_url, media_type FROM books WHERE id = ?
    '''
    book = conn.execute(book_query, (book_id,)).fetchone()

    # Fetch existing review/rating
    read_data_query = '''
        SELECT rating, comment FROM read_data
        WHERE user_id = ? AND book_id = ?
    '''
    read_data = conn.execute(read_data_query, (current_user.id, book_id)).fetchone()

    # Fetch all reading sessions for this book (oldest first for proper labeling)
    sessions_query = '''
        SELECT session_id, date_started, date_completed, created_at
        FROM reading_sessions
        WHERE user_id = ? AND book_id = ?
        ORDER BY
            -- undated past reads first, then by date, then in progress
            CASE WHEN date_completed IS NULL AND date_started IS NULL THEN 0
                 WHEN date_completed IS NULL THEN 2 ELSE 1 END,
            COALESCE(date_completed, date_started, created_at) ASC,
            created_at ASC
    '''
    sessions = conn.execute(sessions_query, (current_user.id, book_id)).fetchall()

    # Just marked Read / Watched / Listened (?finished=1, from the status
    # menu): open the session form with today as the finished date, so the
    # book counts toward this year's goal with one tap (ROADMAP 12.3). An
    # open session (started, not finished) is the one to finish; nothing is
    # offered when a session already finished today.
    prefill = None
    if request.args.get('finished'):
        today = date.today().isoformat()
        if not any(s['date_completed'] == today for s in sessions):
            open_session = next((s for s in sessions if s['date_started'] and not s['date_completed']), None)
            prefill = ({'mode': 'edit', 'session_id': open_session['session_id'],
                        'started': open_session['date_started'], 'completed': today}
                       if open_session else
                       {'mode': 'add', 'session_id': '', 'started': '', 'completed': today})


    # Convert book data to the format you use (e.g., book[1])
    books = {1: {"id": book["id"], "title": book["title"], "author": book["author"], "cover_image_url": book["cover_image_url"]}} if book else {}

    return render_template(
        'rate_review.html',
        book=books.get(1),  # Matches book[1] format
        read_data=read_data,
        sessions=sessions,
        prefill=prefill,
        m=media.media_labels(media.media_type_of(book)),
        # Reached from the Reviews section: its crumb, and saving goes back there
        from_reviews=request.args.get('from') == 'reviews',
    )


@read_blueprint.route('/manage_session/<int:book_id>', methods=['POST'])
@login_required
def manage_session(book_id):
    """Add or update a reading session"""
    conn = get_db()
    # Only books in the user's circle (models.can_view_book)
    if not can_view_book(conn, current_user, book_id):
        abort(404)

    # Get form data
    session_id = request.form.get('session_id')
    date_started = request.form.get('date_started')
    date_completed = request.form.get('date_completed')
    redirect_to = request.form.get('redirect_to', 'book_detail')  # Default to book_detail

    # Validate dates
    date_started_obj = None
    date_completed_obj = None
    today = datetime.now().date()

    if date_started:
        try:
            date_started_obj = datetime.strptime(date_started, '%Y-%m-%d').date()
            # Check if start date is in the future
            if date_started_obj > today:
                flash("Start date cannot be in the future.", 'error')
                if redirect_to == 'rate_review':
                    return redirect(url_for('read.rate_review', book_id=book_id))
                return redirect(url_for('books.show_book', id=book_id))
        except ValueError:
            flash("Invalid start date format.", 'error')
            if redirect_to == 'rate_review':
                return redirect(url_for('read.rate_review', book_id=book_id))
            return redirect(url_for('books.show_book', id=book_id))

    if date_completed:
        try:
            date_completed_obj = datetime.strptime(date_completed, '%Y-%m-%d').date()
            # Check if completion date is in the future
            if date_completed_obj > today:
                flash("Completion date cannot be in the future.", 'error')
                if redirect_to == 'rate_review':
                    return redirect(url_for('read.rate_review', book_id=book_id))
                return redirect(url_for('books.show_book', id=book_id))
        except ValueError:
            flash("Invalid completion date format.", 'error')
            if redirect_to == 'rate_review':
                return redirect(url_for('read.rate_review', book_id=book_id))
            return redirect(url_for('books.show_book', id=book_id))

    # Validate that start date is before completion date
    if date_started_obj and date_completed_obj and date_started_obj > date_completed_obj:
        flash("Start date cannot be after completion date.", 'error')
        if redirect_to == 'rate_review':
            return redirect(url_for('read.rate_review', book_id=book_id))
        return redirect(url_for('books.show_book', id=book_id))

    # No dates at all is allowed (books read long ago), but only when the
    # page asked and the user said yes (undated=1, ROADMAP 14c). Without it a
    # stray Save of an empty form would add a blank session.
    if not date_started_obj and not date_completed_obj and request.form.get('undated') != '1':
        flash("No dates were entered, so nothing was saved.", 'info')
        if redirect_to == 'rate_review':
            return redirect(url_for('read.rate_review', book_id=book_id))
        return redirect(url_for('books.show_book', id=book_id))

    # Update or insert reading session
    if session_id:
        # Update existing session
        conn.execute('''
            UPDATE reading_sessions
            SET date_started = ?, date_completed = ?
            WHERE session_id = ? AND user_id = ?
        ''', (_iso(date_started_obj), _iso(date_completed_obj), session_id, current_user.id))
        flash("Reading session updated successfully!", 'success')
    else:
        # Insert new reading session
        conn.execute('''
            INSERT INTO reading_sessions (user_id, book_id, date_started, date_completed)
            VALUES (?, ?, ?, ?)
        ''', (current_user.id, book_id, _iso(date_started_obj), _iso(date_completed_obj)))
        flash("Reading session added successfully!", 'success')

    conn.commit()

    # Redirect based on preference
    if redirect_to == 'rate_review':
        return redirect(url_for('read.rate_review', book_id=book_id))
    return redirect(url_for('books.show_book', id=book_id))


@read_blueprint.route('/delete_reading_session/<int:session_id>', methods=['POST'])
@login_required
def delete_reading_session(session_id):
    conn = get_db()

    # Get book_id and redirect preference
    book_id = request.form.get('book_id')
    redirect_to = request.form.get('redirect_to', 'rate_review')  # Default to rate_review

    # Verify the session belongs to the current user before deleting
    session = conn.execute('''
        SELECT user_id, book_id FROM reading_sessions
        WHERE session_id = ?
    ''', (session_id,)).fetchone()

    if session and session['user_id'] == current_user.id:
        conn.execute('DELETE FROM reading_sessions WHERE session_id = ?', (session_id,))
        conn.commit()
        flash("Reading session deleted successfully!", 'success')

        # Use book_id from session if not provided in form
        if not book_id:
            book_id = session['book_id']
    else:
        flash("Session not found or you don't have permission to delete it.", 'error')


    # Redirect based on preference
    if book_id:
        if redirect_to == 'book_detail':
            return redirect(url_for('books.show_book', id=book_id))
        else:
            return redirect(url_for('read.rate_review', book_id=book_id))
    else:
        return redirect(url_for('base.index'))


# Example redirect in collections.py
# def add_to_read(book_id):
#     # Code to add book to the "read" collection
#     return redirect(url_for('read.rate_review', book_id=book_id))
