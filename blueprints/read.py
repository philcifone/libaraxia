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
        date_read = request.form.get('date_read')
        rating = request.form.get('rating')
        comment = request.form.get('comment')

        # Validate date format
        try:
            date_read = datetime.strptime(date_read, '%Y-%m-%d').date()
        except ValueError:
            flash("Invalid date format.", 'error')
            return redirect(request.url)

        # Validate rating
        if not rating or not rating.isdigit() or not (1 <= int(rating) <= 5):
            flash("Invalid rating. Please enter a number between 1 and 5.", 'error')
            return redirect(request.url)

        # Insert or update the read data
        conn.execute('''
            INSERT INTO read_data (user_id, book_id, date_read, rating, comment)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, book_id) DO UPDATE SET
                date_read = excluded.date_read,
                rating = excluded.rating,
                comment = excluded.comment
        ''', (current_user.id, book_id, date_read, int(rating), comment))
        conn.commit()

        flash("Your rating and review have been saved!", 'success')
        return redirect(url_for('base.index', collection_type='read'))

    # Fetch book details and existing read data
    book_query = '''
        SELECT id, title, author, cover_image_url FROM books WHERE id = ?
    '''
    book = conn.execute(book_query, (book_id,)).fetchone()

    read_data_query = '''
        SELECT date_read, rating, comment FROM read_data
        WHERE user_id = ? AND book_id = ?
    '''
    read_data = conn.execute(read_data_query, (current_user.id, book_id)).fetchone()

    conn.close()

    # Convert book data to the format you use (e.g., book[1])
    books = {1: {"id": book["id"], "title": book["title"], "author": book["author"], "cover_image_url": book["cover_image_url"]}} if book else {}

    return render_template(
        'rate_review.html',
        book=books.get(1),  # Matches book[1] format
        read_data=read_data
    )


# Example redirect in collections.py
# def add_to_read(book_id):
#     # Code to add book to the "read" collection
#     return redirect(url_for('read.rate_review', book_id=book_id))
