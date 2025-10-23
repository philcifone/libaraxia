from flask import Blueprint, request, redirect, url_for, flash, render_template, g, jsonify
from utils.database import get_db_connection
from flask_login import login_required, current_user

collections_blueprint = Blueprint('collections', __name__, template_folder='templates')

@collections_blueprint.route('/collections', methods=['GET'])
@login_required
def view_collections():
    conn = get_db_connection()
    try:
        # Fetch default reading lists (status-based collections) with book count
        cursor = conn.execute('''
            SELECT c.status, COUNT(b.id) as book_count
            FROM collections c
            JOIN books b ON c.book_id = b.id
            WHERE c.user_id = ?
            GROUP BY c.status
        ''', (current_user.id,))
        reading_lists = cursor.fetchall()

        # Fetch cover previews for each reading status (up to 8 covers)
        reading_list_covers = {}
        for reading_list in reading_lists:
            status = reading_list['status']
            cursor = conn.execute('''
                SELECT b.cover_image_url
                FROM collections c
                JOIN books b ON c.book_id = b.id
                WHERE c.user_id = ? AND c.status = ?
                ORDER BY c.collection_id DESC
                LIMIT 8
            ''', (current_user.id, status))
            reading_list_covers[status] = [row['cover_image_url'] for row in cursor.fetchall()]

        # Fetch custom collections
        cursor = conn.execute('''
            SELECT uc.collection_id, uc.name, COUNT(b.id) as book_count
            FROM user_collections uc
            LEFT JOIN collection_books cb ON uc.collection_id = cb.collection_id
            LEFT JOIN books b ON cb.book_id = b.id
            WHERE uc.user_id = ?
            GROUP BY uc.collection_id, uc.name
        ''', (current_user.id,))
        custom_collections = cursor.fetchall()

        # Fetch cover previews for each custom collection (up to 8 covers)
        custom_collection_covers = {}
        for collection in custom_collections:
            collection_id = collection['collection_id']
            cursor = conn.execute('''
                SELECT b.cover_image_url
                FROM collection_books cb
                JOIN books b ON cb.book_id = b.id
                WHERE cb.collection_id = ?
                ORDER BY cb.added_at DESC
                LIMIT 8
            ''', (collection_id,))
            custom_collection_covers[collection_id] = [row['cover_image_url'] for row in cursor.fetchall()]

        return render_template('collections.html',
                             reading_lists=reading_lists,
                             custom_collections=custom_collections,
                             reading_list_covers=reading_list_covers,
                             custom_collection_covers=custom_collection_covers)
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
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ? AND book_id = ?
            ''', (status, current_user.id, book_id))
        else:
            conn.execute('''
                INSERT INTO collections (user_id, book_id, status, created_at, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
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
    # Get optional username parameter (defaults to current user)
    username = request.args.get('username', current_user.username)

    conn = get_db_connection()
    try:
        # Get the target user
        target_user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()

        if not target_user:
            flash('User not found!', 'danger')
            return redirect(url_for('base.index'))

        target_user_id = target_user['id']
        is_own_profile = (target_user_id == current_user.id)

        # Check friendship status if viewing someone else's profile
        if not is_own_profile:
            from models import get_friendship_status
            friendship_status = get_friendship_status(current_user.id, target_user_id)

            # Only allow viewing if they are friends
            if friendship_status not in ('self', 'friends'):
                flash('You must be friends to view this shelf!', 'warning')
                return redirect(url_for('user.profile', username=username))

        # Fetch books for the target user
        cursor = conn.execute('''
            SELECT b.id, b.title, b.author, b.cover_image_url
            FROM collections c
            JOIN books b ON c.book_id = b.id
            WHERE c.user_id = ? AND c.status = ?
        ''', (target_user_id, status))
        books = cursor.fetchall()

        return render_template('collection_status.html',
                             status=status,
                             books=books,
                             is_custom=False,
                             collection=None,
                             target_username=username,
                             is_own_profile=is_own_profile)
    finally:
        conn.close()

@collections_blueprint.route('/manage_book_collections', methods=['POST'])
@login_required
def manage_book_collections():
    book_id = request.form.get('book_id')
    collection_id = request.form.get('collection_id')
    
    if not book_id or not collection_id:
        flash('Missing required information', 'error')
        return redirect(request.referrer)

    conn = get_db_connection()
    try:
        # Check if book is already in collection
        existing = conn.execute('''
            SELECT 1 FROM collection_books 
            WHERE collection_id = ? AND book_id = ?
        ''', (collection_id, book_id)).fetchone()

        if existing:
            # Remove from collection if already exists
            conn.execute('''
                DELETE FROM collection_books 
                WHERE collection_id = ? AND book_id = ?
            ''', (collection_id, book_id))
            flash('Book removed from collection', 'success')
        else:
            # Add to collection
            conn.execute('''
                INSERT INTO collection_books (collection_id, book_id)
                VALUES (?, ?)
            ''', (collection_id, book_id))
            flash('Book added to collection', 'success')
        
        conn.commit()
    except Exception as e:
        flash(f'Error managing collection: {str(e)}', 'error')
    finally:
        conn.close()

    return redirect(request.referrer)

@collections_blueprint.route('/delete_collection/<int:collection_id>', methods=['POST'])
@login_required
def delete_collection(collection_id):
    conn = get_db_connection()
    try:
        # Verify ownership and delete
        cursor = conn.execute('''
            DELETE FROM user_collections 
            WHERE collection_id = ? AND user_id = ? 
            RETURNING 1
        ''', (collection_id, current_user.id))
        
        if cursor.fetchone():
            # Also delete associated books
            conn.execute('DELETE FROM collection_books WHERE collection_id = ?', (collection_id,))
            conn.commit()
            flash('Collection deleted successfully', 'success')
        else:
            flash('Collection not found', 'error')
            
    except Exception as e:
        flash(f'Error deleting collection: {str(e)}', 'error')
    finally:
        conn.close()
    
    return redirect(url_for('collections.view_collections'))

@collections_blueprint.route('/get_book_collections/<int:book_id>')
@login_required
def get_book_collections(book_id):
    conn = get_db_connection()
    collections = conn.execute('''
        SELECT uc.collection_id as id, uc.name 
        FROM user_collections uc
        JOIN collection_books cb ON uc.collection_id = cb.collection_id
        WHERE uc.user_id = ? AND cb.book_id = ?
    ''', (current_user.id, book_id)).fetchall()
    conn.close()
    return jsonify({'collections': [dict(c) for c in collections]})