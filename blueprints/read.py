from flask import Blueprint, request, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from utils.database import get_db_connection
from datetime import datetime

# Define the blueprint
read_blueprint = Blueprint('read', __name__, template_folder='templates')

@read_blueprint.route('/rate_review/<int:book_id>', methods=['GET', 'POST'])
@login_required
def rate_review(book_id):
    conn = get_db_connection()

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

        # Validate rating
        if not rating or not rating.isdigit() or not (1 <= int(rating) <= 5):
            flash("Invalid rating. Please enter a number between 1 and 5.", 'error')
            return redirect(request.url)

        # Update or insert reading session
        if session_id:
            # Update existing session
            conn.execute('''
                UPDATE reading_sessions
                SET date_started = ?, date_completed = ?
                WHERE session_id = ? AND user_id = ?
            ''', (date_started_obj, date_completed_obj, session_id, current_user.id))
        else:
            # Insert new reading session
            conn.execute('''
                INSERT INTO reading_sessions (user_id, book_id, date_started, date_completed)
                VALUES (?, ?, ?, ?)
            ''', (current_user.id, book_id, date_started_obj, date_completed_obj))

        # Insert or update the review/rating (separate from sessions)
        conn.execute('''
            INSERT INTO read_data (user_id, book_id, rating, comment)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, book_id) DO UPDATE SET
                rating = excluded.rating,
                comment = excluded.comment
        ''', (current_user.id, book_id, int(rating), comment))

        conn.commit()

        flash("Your rating and review have been saved!", 'success')
        return redirect(url_for('base.index', collection_type='read'))

    # Fetch book details and existing read data
    book_query = '''
        SELECT id, title, author, cover_image_url FROM books WHERE id = ?
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
            CASE WHEN date_completed IS NULL THEN 1 ELSE 0 END,
            COALESCE(date_completed, date_started, created_at) ASC,
            created_at ASC
    '''
    sessions = conn.execute(sessions_query, (current_user.id, book_id)).fetchall()

    conn.close()

    # Convert book data to the format you use (e.g., book[1])
    books = {1: {"id": book["id"], "title": book["title"], "author": book["author"], "cover_image_url": book["cover_image_url"]}} if book else {}

    return render_template(
        'rate_review.html',
        book=books.get(1),  # Matches book[1] format
        read_data=read_data,
        sessions=sessions
    )


@read_blueprint.route('/manage_session/<int:book_id>', methods=['POST'])
@login_required
def manage_session(book_id):
    """Add or update a reading session"""
    conn = get_db_connection()

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
                conn.close()
                if redirect_to == 'rate_review':
                    return redirect(url_for('read.rate_review', book_id=book_id))
                return redirect(url_for('books.show_book', id=book_id))
        except ValueError:
            flash("Invalid start date format.", 'error')
            conn.close()
            if redirect_to == 'rate_review':
                return redirect(url_for('read.rate_review', book_id=book_id))
            return redirect(url_for('books.show_book', id=book_id))

    if date_completed:
        try:
            date_completed_obj = datetime.strptime(date_completed, '%Y-%m-%d').date()
            # Check if completion date is in the future
            if date_completed_obj > today:
                flash("Completion date cannot be in the future.", 'error')
                conn.close()
                if redirect_to == 'rate_review':
                    return redirect(url_for('read.rate_review', book_id=book_id))
                return redirect(url_for('books.show_book', id=book_id))
        except ValueError:
            flash("Invalid completion date format.", 'error')
            conn.close()
            if redirect_to == 'rate_review':
                return redirect(url_for('read.rate_review', book_id=book_id))
            return redirect(url_for('books.show_book', id=book_id))

    # Validate that start date is before completion date
    if date_started_obj and date_completed_obj and date_started_obj > date_completed_obj:
        flash("Start date cannot be after completion date.", 'error')
        conn.close()
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
        ''', (date_started_obj, date_completed_obj, session_id, current_user.id))
        flash("Reading session updated successfully!", 'success')
    else:
        # Insert new reading session
        conn.execute('''
            INSERT INTO reading_sessions (user_id, book_id, date_started, date_completed)
            VALUES (?, ?, ?, ?)
        ''', (current_user.id, book_id, date_started_obj, date_completed_obj))
        flash("Reading session added successfully!", 'success')

    conn.commit()
    conn.close()

    # Redirect based on preference
    if redirect_to == 'rate_review':
        return redirect(url_for('read.rate_review', book_id=book_id))
    return redirect(url_for('books.show_book', id=book_id))


@read_blueprint.route('/delete_reading_session/<int:session_id>', methods=['POST'])
@login_required
def delete_reading_session(session_id):
    conn = get_db_connection()

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

    conn.close()

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
