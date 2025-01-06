from flask import Blueprint, request, redirect, url_for, flash, render_template, g, jsonify
from utils.database import get_db_connection
from flask_login import login_required, current_user

collections_blueprint = Blueprint('collections', __name__, template_folder='templates')

@collections_blueprint.route('/collections', methods=['GET'])
@login_required
def view_collections():
    conn = get_db_connection()
    try:
        # Fetch default reading lists (status-based collections)
        cursor = conn.execute('''
            SELECT c.status, COUNT(c.book_id) as book_count
            FROM collections c
            WHERE c.user_id = ?
            GROUP BY c.status
        ''', (current_user.id,))
        reading_lists = cursor.fetchall()
        
        # Fetch custom collections
        cursor = conn.execute('''
            SELECT uc.collection_id, uc.name, COUNT(cb.book_id) as book_count
            FROM user_collections uc
            LEFT JOIN collection_books cb ON uc.collection_id = cb.collection_id
            WHERE uc.user_id = ?
            GROUP BY uc.collection_id, uc.name
        ''', (current_user.id,))
        custom_collections = cursor.fetchall()
        
        return render_template('collections.html', 
                             reading_lists=reading_lists,
                             custom_collections=custom_collections)
    finally:
        conn.close()

@collections_blueprint.route('/collections/create', methods=['POST'])
@login_required
def create_custom_collection():
    name = request.form.get('name')
    if not name:
        flash('Collection name is required.', 'error')
        return redirect(url_for('collections.view_collections'))
    
    conn = get_db_connection()
    try:
        cursor = conn.execute('''
            INSERT INTO user_collections (user_id, name)
            VALUES (?, ?)
        ''', (current_user.id, name))
        conn.commit()
        flash('Collection created successfully!', 'success')
    except Exception as e:
        flash('Error creating collection.', 'error')
    finally:
        conn.close()
    
    return redirect(url_for('collections.view_collections'))

@collections_blueprint.route('/collections/<int:collection_id>/add', methods=['POST'])
@login_required
def add_to_custom_collection(collection_id):
    print(f"Received add request for collection {collection_id}")
    print("Form data:", request.form)
    
    book_id = request.form.get('book_id')
    if not book_id:
        print("No book_id provided")
        return jsonify({'success': False, 'error': 'Missing book ID'}), 400
    
    print(f"Adding book {book_id} to collection {collection_id}")
    conn = get_db_connection()
    try:
        # Verify the collection belongs to the user
        cursor = conn.execute('''
            SELECT 1 FROM user_collections 
            WHERE collection_id = ? AND user_id = ?
        ''', (collection_id, current_user.id))
        if not cursor.fetchone():
            print(f"Collection {collection_id} not found for user {current_user.id}")
            return jsonify({'success': False, 'error': 'Collection not found'}), 404
        
        # Add book to collection
        print("Inserting into collection_books")
        conn.execute('''
            INSERT OR REPLACE INTO collection_books (collection_id, book_id)
            VALUES (?, ?)
        ''', (collection_id, book_id))
        conn.commit()
        print("Successfully added book to collection")
        return jsonify({'success': True})
    except Exception as e:
        print(f"Error adding book to collection: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()

@collections_blueprint.route('/collections/<int:collection_id>/remove', methods=['POST'])
@login_required
def remove_from_custom_collection(collection_id):
    print(f"Received remove request for collection {collection_id}")
    print("Form data:", request.form)
    
    book_id = request.form.get('book_id')
    if not book_id:
        print("No book_id provided")
        return jsonify({'success': False, 'error': 'Missing book ID'}), 400
    
    print(f"Removing book {book_id} from collection {collection_id}")
    conn = get_db_connection()
    try:
        # Verify the collection belongs to the user
        cursor = conn.execute('''
            SELECT 1 FROM user_collections 
            WHERE collection_id = ? AND user_id = ?
        ''', (collection_id, current_user.id))
        if not cursor.fetchone():
            print(f"Collection {collection_id} not found for user {current_user.id}")
            return jsonify({'success': False, 'error': 'Collection not found'}), 404
        
        # Remove book from collection
        print("Deleting from collection_books")
        conn.execute('''
            DELETE FROM collection_books 
            WHERE collection_id = ? AND book_id = ?
        ''', (collection_id, book_id))
        conn.commit()
        print("Successfully removed book from collection")
        return jsonify({'success': True})
    except Exception as e:
        print(f"Error removing book from collection: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()

@collections_blueprint.route('/collections/<int:collection_id>/view', methods=['GET'])
@login_required
def view_custom_collection(collection_id):
    conn = get_db_connection()
    try:
        # Get collection details
        cursor = conn.execute('''
            SELECT uc.*, COUNT(cb.book_id) as book_count
            FROM user_collections uc
            LEFT JOIN collection_books cb ON uc.collection_id = cb.collection_id
            WHERE uc.collection_id = ? AND uc.user_id = ?
            GROUP BY uc.collection_id
        ''', (collection_id, current_user.id))
        collection = cursor.fetchone()
        
        if not collection:
            flash('Collection not found.', 'error')
            return redirect(url_for('collections.view_collections'))
        
        # Get books in collection
        cursor = conn.execute('''
            SELECT b.id, b.title, b.author, b.cover_image_url
            FROM books b
            JOIN collection_books cb ON b.id = cb.book_id
            WHERE cb.collection_id = ?
        ''', (collection_id,))
        books = cursor.fetchall()
        
        return render_template('collection_status.html',
                             collection=collection,
                             books=books,
                             is_custom=True,
                             status=None)  # Include status but set to None for custom collections
    finally:
        conn.close()

@collections_blueprint.route('/collections/status/add', methods=['POST'])
@login_required
def add_to_status_collection():
    book_id = request.form.get('id')
    status = request.form.get('status')
    
    if not book_id or not status:
        flash('Missing book ID or status.', 'danger')
        return redirect(request.referrer)
    
    conn = get_db_connection()
    try:
        cursor = conn.execute('''
            SELECT 1 FROM collections
            WHERE user_id = ? AND book_id = ?
        ''', (current_user.id, book_id))
        exists = cursor.fetchone()
        
        if exists:
            conn.execute('''
                UPDATE collections
                SET status = ?
                WHERE user_id = ? AND book_id = ?
            ''', (status, current_user.id, book_id))
        else:
            conn.execute('''
                INSERT INTO collections (user_id, book_id, status)
                VALUES (?, ?, ?)
            ''', (current_user.id, book_id, status))
        
        conn.commit()
        flash('Collection updated successfully!', 'success')
        
        if status == 'read':
            return redirect(url_for('read.rate_review', book_id=book_id))
            
    except Exception as e:
        flash(f'Failed to update collection: {e}', 'danger')
    finally:
        conn.close()
    
    return redirect(request.referrer)

@collections_blueprint.route('/collections/status/<status>', methods=['GET'])
@login_required
def view_by_status(status):
    conn = get_db_connection()
    try:
        cursor = conn.execute('''
            SELECT b.id, b.title, b.author, b.cover_image_url
            FROM collections c
            JOIN books b ON c.book_id = b.id
            WHERE c.user_id = ? AND c.status = ?
        ''', (current_user.id, status))
        books = cursor.fetchall()
        
        return render_template('collection_status.html',
                             status=status,
                             books=books,
                             is_custom=False,
                             collection=None)  # Include collection but set to None for status-based collections
    finally:
        conn.close()