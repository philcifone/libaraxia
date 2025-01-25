from flask import Blueprint, render_template, redirect, url_for, request, flash, make_response
from flask_login import current_user, login_required
from utils.database import get_db_connection
from models import User, admin_required
import bcrypt
import csv
from io import StringIO

# Initialize Blueprint
user_blueprint = Blueprint('user', __name__)

def calculate_user_stats(conn, user_id):
    """Calculate user reading statistics"""
    query = '''
        SELECT 
            COUNT(DISTINCT r.book_id) as books_read,
            SUM(b.page_count) as pages_read,
            AVG(r.rating) as avg_rating
        FROM read_data r
        JOIN books b ON r.book_id = b.id
        WHERE r.user_id = ?
    '''
    stats = conn.execute(query, [user_id]).fetchone()
    return dict(stats) if stats else None

@user_blueprint.route('/<username>')
@login_required
def profile(username):
    # Ensure the current user is authenticated
    if not current_user.is_authenticated:
        return redirect(url_for('auth.login'))

    # Fetch the user details from the database
    conn = get_db_connection()
    try:
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        
        if not user:
            return "User not found!", 404

        # Convert user data to dictionary format
        user = dict(user)
        
        # Get user's reading stats
        stats = calculate_user_stats(conn, user['id'])

        # Library stats
        library_stats = calculate_library_stats(conn)

        return render_template('user.html', user=user, stats=stats, library_stats=library_stats)
    finally:
        conn.close()

@user_blueprint.route('/update_profile', methods=['POST'])
@login_required
def update_profile():
    email = request.form.get('email')
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')

    # Get current user's data
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (current_user.id,)).fetchone()
    
    if not user:
        conn.close()
        flash('User not found!', 'danger')
        return redirect(url_for('user.profile', username=current_user.username))

    user = dict(user)

    # Verify current password
    if not bcrypt.checkpw(current_password.encode('utf-8'), user['password'].encode('utf-8')):
        conn.close()
        flash('Current password is incorrect!', 'danger')
        return redirect(url_for('user.profile', username=current_user.username))

    # Start building update query
    update_fields = []
    params = []

    # Handle email update
    if email != user['email']:
        # Check if email is already taken
        email_check = conn.execute('SELECT id FROM users WHERE email = ? AND id != ?', 
                                 (email, current_user.id)).fetchone()
        if email_check:
            conn.close()
            flash('Email is already in use!', 'danger')
            return redirect(url_for('user.profile', username=current_user.username))
        update_fields.append('email = ?')
        params.append(email)

    # Handle password update
    if new_password:
        if new_password != confirm_password:
            conn.close()
            flash('New passwords do not match!', 'danger')
            return redirect(url_for('user.profile', username=current_user.username))
        
        hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
        update_fields.append('password = ?')
        params.append(hashed_password.decode('utf-8'))

    # If there are fields to update
    if update_fields:
        query = f"UPDATE users SET {', '.join(update_fields)} WHERE id = ?"
        params.append(current_user.id)
        
        try:
            conn.execute(query, params)
            conn.commit()
            flash('Profile updated successfully!', 'success')
        except Exception as e:
            conn.rollback()
            flash('An error occurred while updating your profile.', 'danger')
    
    conn.close()
    return redirect(url_for('user.profile', username=current_user.username))

def calculate_library_stats(conn):
   query = '''
       SELECT 
           COUNT(DISTINCT b.id) as total_books,
           SUM(b.page_count) as total_pages,
           COUNT(DISTINCT c.book_id) as read_books,
           (SELECT COUNT(*) FROM (
               SELECT DISTINCT author FROM books
           )) as unique_authors,
           (SELECT title FROM books WHERE page_count = (SELECT MAX(page_count) FROM books)) as longest_book,
           (SELECT MAX(page_count) FROM books) as longest_pages,
           (
               SELECT genre
               FROM (
                   SELECT genre, COUNT(*) as count 
                   FROM books 
                   WHERE genre IS NOT NULL 
                   GROUP BY genre
                   ORDER BY count DESC 
                   LIMIT 1
               )
           ) as most_common_genre
       FROM books b
       LEFT JOIN collections c ON b.id = c.book_id AND c.status = 'read'
   '''
   stats = dict(conn.execute(query).fetchone())
   if stats['total_books']:
       stats['read_percentage'] = round((stats['read_books'] / stats['total_books']) * 100)
       stats['total_pages'] = "{:,}".format(int(stats['total_pages'] or 0))
       stats['longest_pages'] = "{:,}".format(int(stats['longest_pages'] or 0))
   return stats

@user_blueprint.route('/export_library')
@login_required
def export_library():
    conn = get_db_connection()
    try:
        # Get all books with their statuses and ratings for the current user
        query = '''
            SELECT 
                b.title,
                b.author,
                b.publisher,
                b.publish_year,
                b.isbn,
                b.page_count,
                b.genre,
                c.status as reading_status,
                r.rating,
                r.date_read,
                r.comment as review,
                GROUP_CONCAT(t.tag_name) as tags
            FROM books b
            LEFT JOIN collections c ON b.id = c.book_id AND c.user_id = ?
            LEFT JOIN read_data r ON b.id = r.book_id AND r.user_id = ?
            LEFT JOIN book_tags t ON b.id = t.book_id AND t.user_id = ?
            GROUP BY b.id
            ORDER BY b.title
        '''
        books = conn.execute(query, (current_user.id, current_user.id, current_user.id)).fetchall()

        # Create CSV in memory
        si = StringIO()
        writer = csv.writer(si)
        
        # Write headers
        writer.writerow(['Title', 'Author', 'Publisher', 'Year', 'ISBN', 'Pages', 
                        'Genre', 'Reading Status', 'Rating', 'Date Read', 'Review', 'Tags'])
        
        # Write data
        for book in books:
            writer.writerow([
                book['title'],
                book['author'],
                book['publisher'],
                book['publish_year'],
                book['isbn'],
                book['page_count'],
                book['genre'],
                book['reading_status'] or 'Untracked',
                book['rating'],
                book['date_read'],
                book['review'],
                book['tags']
            ])

        # Create the response
        output = make_response(si.getvalue())
        output.headers["Content-Disposition"] = f"attachment; filename=library_export_{current_user.username}.csv"
        output.headers["Content-type"] = "text/csv"
        return output

    finally:
        conn.close()

        