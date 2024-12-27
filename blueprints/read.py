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
        date_read = request.form.get('date_read')
        rating = request.form.get('rating')
        comment = request.form.get('comment')

        # Validation
        try:
            # Validate and convert date
            date_read = datetime.strptime(date_read, '%Y-%m-%d').date()
        except ValueError:
            flash("Invalid date format.", 'error')
            return redirect(request.url)

        if not rating or not rating.isdigit() or int(rating) < 1 or int(rating) > 5:
            flash("Invalid rating. Please enter a number between 1 and 5.", 'error')
            return redirect(request.url)

        # Insert or update Read Data entry
        conn.execute('''
            INSERT INTO read_data (user_id, book_id, date_read, rating, comment)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, book_id) DO UPDATE SET
                date_read = excluded.date_read,
                rating = excluded.rating,
                comment = excluded.comment
        ''', (current_user.id, book_id, date_read, int(rating), comment))
        conn.commit()
        conn.close()

        flash("Your rating and review have been saved!", 'success')
        return redirect(url_for('collections.view_collections', collection_type='read'))

    # Existing data fetch
    read_data = conn.execute('''
        SELECT date_read, rating, comment FROM read_data
        WHERE user_id = ? AND book_id = ?
    ''', (current_user.id, book_id)).fetchone()
    conn.close()

    return render_template('rate_review.html', book_id=book_id, read_data=read_data)

# Example redirect in collections.py
# def add_to_read(book_id):
#     # Code to add book to the "read" collection
#     return redirect(url_for('read.rate_review', book_id=book_id))
