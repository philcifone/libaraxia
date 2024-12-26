from flask import Blueprint, request, redirect, url_for, flash, render_template, g
from utils.database import get_db_connection
from flask_login import login_required, current_user

collections_blueprint = Blueprint('collections', __name__, template_folder='templates')

@collections_blueprint.route('/collections', methods=['GET'])
@login_required
def view_collections():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT c.collection_id, c.status, b.title
        FROM collections c
        JOIN books b ON c.book_id = b.id
        WHERE c.user_id = ?
    ''', (current_user.id,))
    collections = cursor.fetchall()
    conn.close()

    return render_template('collections.html', collections=collections)

@collections_blueprint.route('/collections/add', methods=['POST'])
@login_required
def add_to_collection():
    book_id = request.form.get('id')  # 'id' from the form matches books.id
    status = request.form.get('status')

    if not book_id or not status:
        flash('Missing book ID or status.', 'danger')
        return redirect(request.referrer)

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Check if the book already exists in the user's collection
        cursor.execute('''
            SELECT 1 FROM collections
            WHERE user_id = ? AND book_id = ?
        ''', (current_user.id, book_id))
        exists = cursor.fetchone()

        if exists:
            # Update the status if the book already exists
            cursor.execute('''
                UPDATE collections
                SET status = ?
                WHERE user_id = ? AND book_id = ?
            ''', (status, current_user.id, book_id))
            flash('Book status updated!', 'success')
        else:
            # Insert a new record if the book doesn't exist
            cursor.execute('''
                INSERT INTO collections (user_id, book_id, status)
                VALUES (?, ?, ?)
            ''', (current_user.id, book_id, status))
            flash('Book added to your collection!', 'success')

        conn.commit()
    except Exception as e:
        flash(f'Failed to update collection: {e}', 'danger')
    finally:
        conn.close()

    return redirect(url_for('collections.view_collections'))

@collections_blueprint.route('/collections/<status>', methods=['GET'])
@login_required
def view_by_status(status):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT b.id, b.title, b.author, b.cover_image_url
        FROM collections c
        JOIN books b ON c.book_id = b.id
        WHERE c.user_id = ? AND c.status = ?
    ''', (current_user.id, status))
    books = cursor.fetchall()
    conn.close()

    return render_template('collection_status.html', books=books, status=status)

