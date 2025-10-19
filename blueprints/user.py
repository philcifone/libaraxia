from flask import Blueprint, render_template, redirect, url_for, request, flash, make_response, jsonify, current_app
from flask_login import current_user, login_required
from utils.database import get_db_connection
from models import User, admin_required
from werkzeug.utils import secure_filename
import bcrypt
import csv
import os
from io import StringIO
from PIL import Image

# Initialize Blueprint
user_blueprint = Blueprint('user', __name__)

# Allowed extensions for profile pictures
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def calculate_user_stats(conn, user_id):
    """Calculate user reading statistics"""
    query = '''
        SELECT
            COUNT(DISTINCT r.book_id) as books_read,
            SUM(CAST(b.page_count AS INTEGER)) as pages_read,
            AVG(r.rating) as avg_rating
        FROM read_data r
        JOIN books b ON r.book_id = b.id
        WHERE r.user_id = ?
    '''
    stats = conn.execute(query, [user_id]).fetchone()

    # Calculate year-to-date reading progress
    from datetime import datetime
    current_year = datetime.now().year
    ytd_query = '''
        SELECT COUNT(DISTINCT rs.book_id) as books_read_this_year
        FROM reading_sessions rs
        WHERE rs.user_id = ?
        AND rs.date_completed IS NOT NULL
        AND strftime('%Y', rs.date_completed) = ?
    '''
    ytd_stats = conn.execute(ytd_query, [user_id, str(current_year)]).fetchone()

    result = dict(stats) if stats else {}
    if ytd_stats:
        result['books_read_this_year'] = ytd_stats['books_read_this_year']
    else:
        result['books_read_this_year'] = 0

    # Calculate user-specific read percentage (books user has read vs total books in library)
    library_query = '''
        SELECT COUNT(DISTINCT id) as total_books
        FROM books
    '''
    library_total = conn.execute(library_query).fetchone()

    books_read = result.get('books_read', 0) or 0
    total_books = library_total['total_books'] if library_total else 0

    if total_books > 0:
        result['read_percentage'] = round((books_read / total_books) * 100, 1)
    else:
        result['read_percentage'] = 0

    # Reading by month (last 12 months)
    reading_by_month_query = '''
        SELECT
            strftime('%Y-%m', rs.date_completed) as month,
            COUNT(DISTINCT rs.book_id) as books_count
        FROM reading_sessions rs
        WHERE rs.user_id = ?
        AND rs.date_completed IS NOT NULL
        AND rs.date_completed >= date('now', '-12 months')
        GROUP BY month
        ORDER BY month
    '''
    result['reading_by_month'] = [dict(row) for row in conn.execute(reading_by_month_query, [user_id]).fetchall()]

    # Top genres
    top_genres_query = '''
        SELECT
            b.genre,
            COUNT(DISTINCT r.book_id) as count
        FROM read_data r
        JOIN books b ON r.book_id = b.id
        WHERE r.user_id = ? AND b.genre IS NOT NULL AND b.genre != ''
        GROUP BY b.genre
        ORDER BY count DESC
        LIMIT 5
    '''
    result['top_genres'] = [dict(row) for row in conn.execute(top_genres_query, [user_id]).fetchall()]

    # Rating distribution
    rating_dist_query = '''
        SELECT
            r.rating,
            COUNT(*) as count
        FROM read_data r
        WHERE r.user_id = ? AND r.rating IS NOT NULL
        GROUP BY r.rating
        ORDER BY r.rating
    '''
    result['rating_distribution'] = [dict(row) for row in conn.execute(rating_dist_query, [user_id]).fetchall()]

    # Collection status breakdown
    collection_status_query = '''
        SELECT
            c.status,
            COUNT(DISTINCT c.book_id) as count
        FROM collections c
        WHERE c.user_id = ?
        GROUP BY c.status
    '''
    result['collection_status'] = [dict(row) for row in conn.execute(collection_status_query, [user_id]).fetchall()]

    # Top authors
    top_authors_query = '''
        SELECT
            b.author,
            COUNT(DISTINCT r.book_id) as books_count,
            ROUND(AVG(r.rating), 1) as avg_rating
        FROM read_data r
        JOIN books b ON r.book_id = b.id
        WHERE r.user_id = ?
        GROUP BY b.author
        ORDER BY books_count DESC, avg_rating DESC
        LIMIT 5
    '''
    result['top_authors'] = [dict(row) for row in conn.execute(top_authors_query, [user_id]).fetchall()]

    # Reading streak stats
    streak_query = '''
        SELECT
            MIN(date_completed) as first_read,
            MAX(date_completed) as last_read,
            COUNT(DISTINCT date(date_completed)) as unique_days
        FROM reading_sessions
        WHERE user_id = ? AND date_completed IS NOT NULL
    '''
    streak_stats = conn.execute(streak_query, [user_id]).fetchone()
    if streak_stats:
        result.update(dict(streak_stats))

    return result

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

        # Get current year for the reading goal section
        from datetime import datetime
        current_year = datetime.now().year

        return render_template('user.html', user=user, stats=stats, library_stats=library_stats, current_year=current_year)
    finally:
        conn.close()

@user_blueprint.route('/update_reading_goal', methods=['POST'])
@login_required
def update_reading_goal():
    reading_goal = request.form.get('reading_goal')

    if reading_goal is None or reading_goal == '':
        flash('Please provide a reading goal!', 'danger')
        return redirect(url_for('user.profile', username=current_user.username))

    try:
        goal_value = int(reading_goal)
        if goal_value < 0:
            flash('Reading goal must be a positive number!', 'danger')
            return redirect(url_for('user.profile', username=current_user.username))

        conn = get_db_connection()
        try:
            conn.execute('UPDATE users SET reading_goal = ? WHERE id = ?', (goal_value, current_user.id))
            conn.commit()
            flash('Reading goal updated successfully!', 'success')
        except Exception as e:
            conn.rollback()
            flash('An error occurred while updating your reading goal.', 'danger')
        finally:
            conn.close()

    except ValueError:
        flash('Reading goal must be a valid number!', 'danger')

    return redirect(url_for('user.profile', username=current_user.username))

@user_blueprint.route('/update_email', methods=['POST'])
@login_required
def update_email():
    """Update user email via inline editing"""
    try:
        data = request.get_json()
        new_email = data.get('email', '').strip()

        if not new_email:
            return jsonify({'success': False, 'message': 'Email cannot be empty'}), 400

        conn = get_db_connection()
        try:
            # Check if email is already taken by another user
            existing_user = conn.execute('SELECT id FROM users WHERE email = ? AND id != ?',
                                        (new_email, current_user.id)).fetchone()
            if existing_user:
                return jsonify({'success': False, 'message': 'Email is already in use'}), 400

            # Update email
            conn.execute('UPDATE users SET email = ? WHERE id = ?', (new_email, current_user.id))
            conn.commit()

            return jsonify({'success': True, 'message': 'Email updated successfully'})

        finally:
            conn.close()

    except Exception as e:
        return jsonify({'success': False, 'message': 'An error occurred while updating email'}), 500

@user_blueprint.route('/update_username', methods=['POST'])
@login_required
def update_username():
    """Update username via inline editing"""
    try:
        data = request.get_json()
        new_username = data.get('username', '').strip()

        if not new_username:
            return jsonify({'success': False, 'message': 'Username cannot be empty'}), 400

        # Username validation
        if len(new_username) < 3:
            return jsonify({'success': False, 'message': 'Username must be at least 3 characters'}), 400

        conn = get_db_connection()
        try:
            # Check if username is already taken by another user
            existing_user = conn.execute('SELECT id FROM users WHERE username = ? AND id != ?',
                                        (new_username, current_user.id)).fetchone()
            if existing_user:
                return jsonify({'success': False, 'message': 'Username is already taken'}), 400

            # Update username
            conn.execute('UPDATE users SET username = ? WHERE id = ?', (new_username, current_user.id))
            conn.commit()

            # Update the current_user object
            current_user.username = new_username

            return jsonify({'success': True, 'message': 'Username updated successfully'})

        finally:
            conn.close()

    except Exception as e:
        return jsonify({'success': False, 'message': 'An error occurred while updating username'}), 500

@user_blueprint.route('/update_password', methods=['POST'])
@login_required
def update_password():
    """Update password via inline editing"""
    try:
        data = request.get_json()
        current_password = data.get('current_password', '')
        new_password = data.get('new_password', '')
        confirm_password = data.get('confirm_password', '')

        # Validation
        if not current_password or not new_password or not confirm_password:
            return jsonify({'success': False, 'message': 'All password fields are required'}), 400

        if new_password != confirm_password:
            return jsonify({'success': False, 'message': 'New passwords do not match'}), 400

        if len(new_password) < 6:
            return jsonify({'success': False, 'message': 'Password must be at least 6 characters long'}), 400

        conn = get_db_connection()
        try:
            # Get current user's password
            user = conn.execute('SELECT password FROM users WHERE id = ?', (current_user.id,)).fetchone()

            if not user:
                return jsonify({'success': False, 'message': 'User not found'}), 404

            # Verify current password
            if not bcrypt.checkpw(current_password.encode('utf-8'), user['password'].encode('utf-8')):
                return jsonify({'success': False, 'message': 'Current password is incorrect'}), 400

            # Hash new password
            hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())

            # Update password
            conn.execute('UPDATE users SET password = ? WHERE id = ?',
                        (hashed_password.decode('utf-8'), current_user.id))
            conn.commit()

            return jsonify({'success': True, 'message': 'Password updated successfully'})

        finally:
            conn.close()

    except Exception as e:
        return jsonify({'success': False, 'message': 'An error occurred while updating password'}), 500

@user_blueprint.route('/upload_avatar', methods=['POST'])
@login_required
def upload_avatar():
    """Upload and update user profile picture"""
    import logging
    logger = logging.getLogger(__name__)

    try:
        logger.info(f"Avatar upload request from user {current_user.id}")
        logger.info(f"Request files: {request.files}")
        logger.info(f"Request form: {request.form}")

        # Check if the post request has the file part
        if 'avatar' not in request.files:
            logger.error("No 'avatar' file in request")
            return jsonify({'success': False, 'message': 'No file uploaded'}), 400

        file = request.files['avatar']
        logger.info(f"File received: {file.filename}, content_type: {file.content_type}")

        # If user does not select file, browser submits empty file
        if file.filename == '':
            logger.error("Empty filename")
            return jsonify({'success': False, 'message': 'No file selected'}), 400

        if file and allowed_file(file.filename):
            # Secure the filename and create a unique name
            filename = secure_filename(file.filename)
            file_ext = filename.rsplit('.', 1)[1].lower()
            unique_filename = f"user_{current_user.id}_{int(os.urandom(4).hex(), 16)}.{file_ext}"
            logger.info(f"Generated unique filename: {unique_filename}")

            # Create uploads/avatars directory if it doesn't exist
            avatar_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], 'avatars')
            os.makedirs(avatar_folder, exist_ok=True)
            logger.info(f"Avatar folder: {avatar_folder}")

            filepath = os.path.join(avatar_folder, unique_filename)
            logger.info(f"Full filepath: {filepath}")

            # Process and resize image
            try:
                img = Image.open(file)
                logger.info(f"Image opened successfully, mode: {img.mode}, size: {img.size}")

                # Convert RGBA to RGB if necessary
                if img.mode in ('RGBA', 'LA', 'P'):
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                    img = background
                    logger.info(f"Converted image to RGB")

                # Resize to a reasonable size (400x400) while maintaining aspect ratio
                img.thumbnail((400, 400), Image.Resampling.LANCZOS)
                logger.info(f"Image resized to: {img.size}")

                # Save the image
                img.save(filepath, quality=85, optimize=True)
                logger.info(f"Image saved to: {filepath}")

            except Exception as e:
                logger.error(f"Error processing image: {str(e)}", exc_info=True)
                return jsonify({'success': False, 'message': f'Error processing image: {str(e)}'}), 500

            # Get relative path for database storage (use forward slashes for URLs)
            relative_path = f'uploads/avatars/{unique_filename}'
            logger.info(f"Relative path for DB: {relative_path}")

            conn = get_db_connection()
            try:
                # Get old avatar URL to delete old file
                old_avatar = conn.execute('SELECT avatar_url FROM users WHERE id = ?',
                                         (current_user.id,)).fetchone()
                logger.info(f"Old avatar: {old_avatar['avatar_url'] if old_avatar else None}")

                # Update database with new avatar URL
                conn.execute('UPDATE users SET avatar_url = ? WHERE id = ?',
                           (relative_path, current_user.id))
                conn.commit()
                logger.info(f"Database updated successfully")

                # Delete old avatar file if it exists
                if old_avatar and old_avatar['avatar_url']:
                    old_file_path = os.path.join(current_app.root_path, 'static', old_avatar['avatar_url'])
                    if os.path.exists(old_file_path):
                        try:
                            os.remove(old_file_path)
                            logger.info(f"Deleted old avatar: {old_file_path}")
                        except Exception as e:
                            logger.warning(f"Could not delete old avatar: {str(e)}")

                avatar_url = url_for('static', filename=relative_path)
                logger.info(f"Generated avatar URL: {avatar_url}")

                return jsonify({
                    'success': True,
                    'message': 'Profile picture updated successfully',
                    'avatar_url': avatar_url
                })

            finally:
                conn.close()
        else:
            logger.error(f"Invalid file type: {file.filename}")
            return jsonify({'success': False, 'message': 'Invalid file type. Allowed: png, jpg, jpeg, gif, webp'}), 400

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'message': f'An error occurred: {str(e)}'}), 500

def calculate_library_stats(conn):
   query = '''
       SELECT
           COUNT(DISTINCT b.id) as total_books,
           SUM(CAST(b.page_count AS INTEGER)) as total_pages,
           COUNT(DISTINCT c.book_id) as read_books,
           (SELECT COUNT(*) FROM (
               SELECT DISTINCT author FROM books
           )) as unique_authors,
           (SELECT title FROM books
            WHERE CAST(page_count AS INTEGER) = (
                SELECT MAX(CAST(page_count AS INTEGER)) FROM books
            )) as longest_book,
           (SELECT MAX(CAST(page_count AS INTEGER)) FROM books) as longest_pages,
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
                b.id as book_id,
                b.title,
                b.subtitle,
                b.author,
                b.publisher,
                b.publish_year,
                b.isbn,
                b.page_count,
                b.genre,
                c.status as reading_status,
                c.created_at as date_added_to_collection,
                r.rating,
                (SELECT MIN(date_started) FROM reading_sessions
                 WHERE book_id = b.id AND user_id = ?) as date_started,
                (SELECT MAX(date_completed) FROM reading_sessions
                 WHERE book_id = b.id AND user_id = ?) as date_completed,
                (SELECT COUNT(*) FROM reading_sessions
                 WHERE book_id = b.id AND user_id = ? AND date_completed IS NOT NULL) as reread_count,
                r.comment as review,
                GROUP_CONCAT(DISTINCT t.tag_name) as tags,
                GROUP_CONCAT(DISTINCT uc.name) as custom_collections
            FROM books b
            LEFT JOIN collections c ON b.id = c.book_id AND c.user_id = ?
            LEFT JOIN read_data r ON b.id = r.book_id AND r.user_id = ?
            LEFT JOIN book_tags t ON b.id = t.book_id AND t.user_id = ?
            LEFT JOIN collection_books cb ON b.id = cb.book_id
            LEFT JOIN user_collections uc ON cb.collection_id = uc.collection_id AND uc.user_id = ?
            GROUP BY b.id
            ORDER BY b.title
        '''
        books = conn.execute(query, (current_user.id, current_user.id, current_user.id,
                                     current_user.id, current_user.id, current_user.id,
                                     current_user.id)).fetchall()

        # Create CSV in memory
        si = StringIO()
        writer = csv.writer(si)

        # Write headers
        writer.writerow(['Book ID', 'Title', 'Subtitle', 'Author', 'Publisher', 'Year', 'ISBN', 'Pages',
                        'Genre', 'Reading Status', 'Date Added to Collection', 'Date Started',
                        'Date Completed', 'Reread Count', 'Rating', 'Review', 'Tags', 'Custom Collections'])

        # Write data
        for book in books:
            writer.writerow([
                book['book_id'],
                book['title'],
                book['subtitle'],
                book['author'],
                book['publisher'],
                book['publish_year'],
                book['isbn'],
                book['page_count'],
                book['genre'],
                book['reading_status'] or 'Untracked',
                book['date_added_to_collection'],
                book['date_started'],
                book['date_completed'],
                book['reread_count'] or 0,
                book['rating'],
                book['review'],
                book['tags'],
                book['custom_collections']
            ])

        # Create the response
        output = make_response(si.getvalue())
        output.headers["Content-Disposition"] = f"attachment; filename=library_export_{current_user.username}.csv"
        output.headers["Content-type"] = "text/csv"
        return output

    finally:
        conn.close()

        