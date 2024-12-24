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
        JOIN books b ON c.book_id = b.book_id
        WHERE c.user_id = ?
    ''', (current_user.id,))
    collections = cursor.fetchall()
    conn.close()

    return render_template('collections.html', collections=collections)

@collections_blueprint.route('/collections/add', methods=['POST'])
@login_required
def add_to_collection():
    book_id = request.form['book_id']
    status = request.form['status']

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO collections (user_id, book_id, status)
            VALUES (?, ?, ?)
        ''', (current_user.id, book_id, status))
        conn.commit()
        flash('Book added to your collection!', 'success')
    except Exception as e:
        flash('Failed to add book to collection.', 'danger')
    finally:
        conn.close()

    return redirect(url_for('collections.view_collections'))
