from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from utils.database import get_db_connection
import sqlite3
from datetime import datetime

tags_blueprint = Blueprint('tags', __name__)

@tags_blueprint.route('/add', methods=['POST'])
@login_required
def add_tag():
    data = request.get_json()
    book_id = data.get('book_id')
    tags = data.get('tags', [])
    
    if not book_id or not tags:
        return jsonify({'error': 'Missing required data'}), 400
    
    conn = get_db_connection()
    try:
        for tag in tags:
            tag = tag.strip().lower()  # Normalize tags
            if tag:  # Skip empty tags
                try:
                    conn.execute('''
                        INSERT INTO book_tags (user_id, book_id, tag_name)
                        VALUES (?, ?, ?)
                    ''', (current_user.id, book_id, tag))
                except sqlite3.IntegrityError:
                    # Skip duplicates silently
                    continue
        conn.commit()
        
        # Fetch all tags for this book/user combination
        all_tags = conn.execute('''
            SELECT tag_name FROM book_tags 
            WHERE user_id = ? AND book_id = ?
            ORDER BY created_at DESC
        ''', (current_user.id, book_id)).fetchall()
        
        return jsonify({
            'success': True,
            'tags': [tag[0] for tag in all_tags]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@tags_blueprint.route('/remove', methods=['POST'])
@login_required
def remove_tag():
    data = request.get_json()
    book_id = data.get('book_id')
    tag_name = data.get('tag')
    
    if not book_id or not tag_name:
        return jsonify({'error': 'Missing required data'}), 400
    
    conn = get_db_connection()
    try:
        conn.execute('''
            DELETE FROM book_tags 
            WHERE user_id = ? AND book_id = ? AND tag_name = ?
        ''', (current_user.id, book_id, tag_name.lower()))
        conn.commit()
        
        # Fetch remaining tags
        all_tags = conn.execute('''
            SELECT tag_name FROM book_tags 
            WHERE user_id = ? AND book_id = ?
            ORDER BY created_at DESC
        ''', (current_user.id, book_id)).fetchall()
        
        return jsonify({
            'success': True,
            'tags': [tag[0] for tag in all_tags]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@tags_blueprint.route('/get/<int:book_id>', methods=['GET'])
@login_required
def get_tags(book_id):
    conn = get_db_connection()
    try:
        tags = conn.execute('''
            SELECT tag_name FROM book_tags 
            WHERE user_id = ? AND book_id = ?
            ORDER BY created_at DESC
        ''', (current_user.id, book_id)).fetchall()
        
        return jsonify({
            'tags': [tag[0] for tag in tags]
        })
    finally:
        conn.close()