from flask import Blueprint, render_template, redirect, url_for, request, flash, make_response, jsonify, current_app
from flask_login import current_user, login_required, logout_user
from utils.database import get_db_connection, get_db
from utils.accounts import removal_context, deactivate_account, delete_account, AccountError
from utils.export import library_csv, data_zip
from utils.rate_limiting import limiter
from models import User, admin_required, get_friendship_status, is_friends_with, shares_library_with, is_valid_username, USERNAME_RULES, THEME_STYLES, THEME_MODES
from werkzeug.utils import secure_filename
import bcrypt
import csv
import os
import re
from datetime import datetime
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
    """Reading statistics for one user.

    "Read" means the book is on the user's Read shelf (collections.status =
    'read'), so the numbers match the shelves page. Reading counts whoever's
    copy it was, so these aren't limited to the user's own library; only the
    read percentage is ("how much of my library have I read").
    """
    stats = conn.execute('''
        SELECT
            COUNT(*) AS books_read,
            SUM(CAST(b.page_count AS INTEGER)) AS pages_read,
            (SELECT AVG(r.rating) FROM read_data r
             WHERE r.user_id = :u AND r.rating IS NOT NULL) AS avg_rating
        FROM collections c
        JOIN books b ON b.id = c.book_id
        WHERE c.user_id = :u AND c.status = 'read'
    ''', {'u': user_id}).fetchone()
    result = dict(stats)

    # Year-to-date reading progress
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
    result['books_read_this_year'] = ytd_stats['books_read_this_year'] if ytd_stats else 0

    # Read percentage: books on the user's own shelf they've read, out of
    # the books on their shelf (not the whole database, not wishlist entries,
    # not books that have left the house)
    shelf = conn.execute('''
        SELECT
            COUNT(*) AS total_books,
            SUM(EXISTS (SELECT 1 FROM collections c
                        WHERE c.book_id = b.id AND c.user_id = :u AND c.status = 'read')) AS read_books
        FROM library_books b
        WHERE b.added_by = :u AND b.removed_at IS NULL
    ''', {'u': user_id}).fetchone()
    total_books = shelf['total_books'] or 0
    result['read_percentage'] = (round((shelf['read_books'] or 0) / total_books * 100, 1)
                                 if total_books else 0)

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
        FROM collections r
        JOIN books b ON r.book_id = b.id
        WHERE r.user_id = ? AND r.status = 'read' AND b.genre IS NOT NULL AND b.genre != ''
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
            COUNT(DISTINCT c.book_id) as books_count,
            ROUND(AVG(r.rating), 1) as avg_rating
        FROM collections c
        JOIN books b ON c.book_id = b.id
        LEFT JOIN read_data r ON r.user_id = c.user_id AND r.book_id = c.book_id
        WHERE c.user_id = ? AND c.status = 'read'
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

        # Get friendship status
        friendship_status = get_friendship_status(current_user.id, user['id'])

        # If viewing someone else's profile and not friends, show limited info
        is_own_profile = current_user.id == user['id']
        are_friends = friendship_status in ('self', 'friends')

        # Get user's reading stats (only if friends or own profile)
        stats = calculate_user_stats(conn, user['id']) if are_friends else None

        # Library stats (only if friends or own profile)
        library_stats = calculate_library_stats(conn, user['id']) if are_friends else None

        # Get pending friend request ID if applicable
        friend_request_id = None
        if friendship_status == 'request_received':
            friend_request = conn.execute('''
                SELECT id FROM friend_requests
                WHERE sender_id = ? AND receiver_id = ? AND status = 'pending'
            ''', (user['id'], current_user.id)).fetchone()
            if friend_request:
                friend_request_id = friend_request['id']

        # Get friends list (only if friends or own profile)
        friends = []
        if are_friends:
            friends_query = '''
                SELECT
                    u.id, u.username, u.avatar_url,
                    f.created_at as friends_since
                FROM friendships f
                JOIN users u ON (
                    CASE
                        WHEN f.user_id_1 = ? THEN f.user_id_2
                        ELSE f.user_id_1
                    END = u.id
                )
                WHERE f.user_id_1 = ? OR f.user_id_2 = ?
                ORDER BY u.username
            '''
            friends = [dict(f) for f in conn.execute(friends_query, (user['id'], user['id'], user['id'])).fetchall()]

        # Get current year for the reading goal section
        from datetime import datetime
        current_year = datetime.now().year

        # Get wishlist books for the user
        wishlist_books = []
        if are_friends:
            wishlist_query = """
                SELECT
                    b.id,
                    b.title,
                    b.author,
                    b.cover_image_url,
                    w.notes,
                    w.added_at
                FROM wishlist w
                JOIN books b ON w.book_id = b.id
                WHERE w.user_id = ?
                ORDER BY w.added_at DESC
                LIMIT 20
            """
            wishlist_books = [dict(row) for row in conn.execute(wishlist_query, (user['id'],)).fetchall()]

        # Get reading shelves data (like collections page)
        reading_lists = []
        reading_list_covers = {}
        if are_friends:
            # Get count for each reading status
            reading_lists = conn.execute("""
                SELECT status, COUNT(*) as book_count
                FROM collections
                WHERE user_id = ?
                GROUP BY status
            """, (user['id'],)).fetchall()
            reading_lists = [dict(row) for row in reading_lists]

            # Get cover previews for each status
            statuses = ['read', 'currently reading', 'want to read', 'did not finish']
            for status in statuses:
                covers = conn.execute("""
                    SELECT b.cover_image_url
                    FROM collections c
                    JOIN books b ON c.book_id = b.id
                    WHERE c.user_id = ? AND c.status = ?
                    ORDER BY c.created_at DESC
                    LIMIT 8
                """, (user['id'], status)).fetchall()
                reading_list_covers[status] = [row['cover_image_url'] for row in covers]

        # Check if this user is in current user's shared library
        in_shared_library = shares_library_with(current_user.id, user['id']) if not is_own_profile else False

        # Get recent reviews/ratings for the user
        recent_reviews = []
        if are_friends:
            reviews_query = """
                SELECT
                    r.book_id,
                    r.rating,
                    r.comment,
                    b.title,
                    b.author,
                    b.cover_image_url,
                    rs.date_completed
                FROM read_data r
                JOIN books b ON r.book_id = b.id
                LEFT JOIN reading_sessions rs ON r.user_id = rs.user_id AND r.book_id = rs.book_id
                WHERE r.user_id = ?
                ORDER BY rs.date_completed DESC, r.rowid DESC
                LIMIT 5
            """
            recent_reviews = [dict(row) for row in conn.execute(reviews_query, (user['id'],)).fetchall()]

        return render_template(
            'user.html',
            user=user,
            stats=stats,
            library_stats=library_stats,
            current_year=current_year,
            friendship_status=friendship_status,
            is_own_profile=is_own_profile,
            are_friends=are_friends,
            friend_request_id=friend_request_id,
            friends=friends,
            wishlist_books=wishlist_books,
            reading_lists=reading_lists,
            reading_list_covers=reading_list_covers,
            in_shared_library=in_shared_library,
            recent_reviews=recent_reviews,
            account_removal=(removal_context(conn, current_user.id, viewer_is_admin=False)
                             if is_own_profile else None),
        )
    finally:
        conn.close()

@user_blueprint.route('/update_reading_goal', methods=['POST'])
@login_required
@limiter.limit("20 per hour")
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
@limiter.limit("20 per hour")
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
@limiter.limit("20 per hour")
def update_username():
    """Update username via inline editing"""
    try:
        data = request.get_json()
        new_username = data.get('username', '').strip()

        if not new_username:
            return jsonify({'success': False, 'message': 'Username cannot be empty'}), 400

        # Username validation
        if not is_valid_username(new_username):
            return jsonify({'success': False, 'message': USERNAME_RULES}), 400

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

@user_blueprint.route('/update_bio', methods=['POST'])
@login_required
@limiter.limit("20 per hour")
def update_bio():
    """Update user bio via inline editing"""
    try:
        data = request.get_json()
        new_bio = data.get('bio', '').strip()

        # Bio can be empty, but limit length
        if len(new_bio) > 500:
            return jsonify({'success': False, 'message': 'Bio must be 500 characters or less'}), 400

        conn = get_db_connection()
        try:
            # Update bio
            conn.execute('UPDATE users SET bio = ? WHERE id = ?', (new_bio if new_bio else None, current_user.id))
            conn.commit()

            # Update the current_user object
            current_user.bio = new_bio if new_bio else None

            return jsonify({'success': True, 'message': 'Bio updated successfully'})

        finally:
            conn.close()

    except Exception as e:
        return jsonify({'success': False, 'message': 'An error occurred while updating bio'}), 500

@user_blueprint.route('/update_theme', methods=['POST'])
@login_required
@limiter.limit("60 per hour")
def update_theme():
    """Save the Appearance settings (style + light/dark mode)."""
    data = request.get_json(silent=True) or {}
    style = data.get('style', current_user.theme_style)
    mode = data.get('mode', current_user.theme_mode)
    if style not in THEME_STYLES or mode not in THEME_MODES:
        return jsonify({'success': False, 'message': 'Unknown theme setting'}), 400

    conn = get_db_connection()
    try:
        conn.execute('UPDATE users SET theme_style = ?, color_mode = ? WHERE id = ?',
                     (style, mode, current_user.id))
        conn.commit()
    except Exception:
        current_app.logger.exception('Error saving theme settings')
        return jsonify({'success': False, 'message': 'Could not save appearance settings'}), 500
    finally:
        conn.close()

    current_user.theme_style, current_user.theme_mode = style, mode
    return jsonify({'success': True, 'style': style, 'mode': mode})

@user_blueprint.route('/update_password', methods=['POST'])
@login_required
@limiter.limit("10 per hour")
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

        if len(new_password) < 8:
            return jsonify({'success': False, 'message': 'Password must be at least 8 characters long'}), 400

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
@limiter.limit("10 per hour")
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

        # Check file size (Flask's MAX_CONTENT_LENGTH handles this, but provide better error message)
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)  # Reset file pointer

        max_size = current_app.config.get('MAX_CONTENT_LENGTH', 20 * 1024 * 1024)
        if file_size > max_size:
            max_size_mb = max_size / (1024 * 1024)
            logger.error(f"File too large: {file_size} bytes")
            return jsonify({'success': False, 'message': f'File size must be less than {max_size_mb:.0f}MB'}), 400

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

                # Fix orientation based on EXIF data
                try:
                    from PIL import ImageOps
                    img = ImageOps.exif_transpose(img)
                    logger.info(f"Applied EXIF orientation correction")
                except Exception as e:
                    logger.warning(f"Could not apply EXIF orientation: {str(e)}")

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
                return jsonify({'success': False, 'message': 'Error processing the image.'}), 500

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
        return jsonify({'success': False, 'message': 'Something went wrong. Please try again.'}), 500

def calculate_library_stats(conn, user_id):
    """Statistics about one user's library: the books on their shelf now
    (owned, not wishlist entries, not removed)."""
    stats = dict(conn.execute('''
        WITH shelf AS (
            SELECT * FROM library_books
            WHERE added_by = :u AND removed_at IS NULL
        )
        SELECT
            (SELECT COUNT(*) FROM shelf) AS total_books,
            (SELECT SUM(CAST(page_count AS INTEGER)) FROM shelf) AS total_pages,
            (SELECT COUNT(*) FROM shelf s
             WHERE EXISTS (SELECT 1 FROM collections c
                           WHERE c.book_id = s.id AND c.user_id = :u AND c.status = 'read')) AS read_books,
            (SELECT COUNT(DISTINCT LOWER(author)) FROM shelf
             WHERE author IS NOT NULL AND author != '') AS unique_authors,
            (SELECT title FROM shelf
             ORDER BY CAST(page_count AS INTEGER) DESC LIMIT 1) AS longest_book,
            (SELECT MAX(CAST(page_count AS INTEGER)) FROM shelf) AS longest_pages,
            (SELECT genre FROM shelf
             WHERE genre IS NOT NULL AND genre != ''
             GROUP BY LOWER(genre) ORDER BY COUNT(*) DESC LIMIT 1) AS most_common_genre
    ''', {'u': user_id}).fetchone())
    if stats['total_books']:
        stats['read_percentage'] = round((stats['read_books'] / stats['total_books']) * 100)
        stats['total_pages'] = "{:,}".format(int(stats['total_pages'] or 0))
        stats['longest_pages'] = "{:,}".format(int(stats['longest_pages'] or 0))
    return stats

def _export_target():
    """Whose data to export: yourself, or (admins only) ?user_id=N."""
    target_id = request.args.get('user_id', type=int) or current_user.id
    if target_id != current_user.id and not current_user.is_admin:
        return None
    return get_db().execute('SELECT id, username FROM users WHERE id = ?', (target_id,)).fetchone()


@user_blueprint.route('/export_library')
@login_required
def export_library():
    """CSV of the books you own or have your own data on (status, review, sessions, tags)."""
    target = _export_target()
    if not target:
        return redirect(url_for('user.export_library'))
    output = make_response(library_csv(get_db(), target['id']))
    output.headers["Content-Disposition"] = f"attachment; filename=library_export_{target['username']}.csv"
    output.headers["Content-type"] = "text/csv; charset=utf-8"
    return output


@user_blueprint.route('/export_data')
@login_required
def export_data():
    """ZIP of CSVs with everything of yours: library, reviews, sessions, shelves, wishlist, profile."""
    target = _export_target()
    if not target:
        return redirect(url_for('user.export_data'))
    output = make_response(data_zip(get_db(), target['id']))
    output.headers["Content-Disposition"] = f"attachment; filename=libaraxia_{target['username']}_{datetime.now():%Y%m%d}.zip"
    output.headers["Content-type"] = "application/zip"
    return output


@user_blueprint.route('/delete_account', methods=['POST'])
@login_required
@limiter.limit("10 per hour")
def delete_account_self():
    """Deactivate or delete your own account (see utils/accounts.py)."""
    conn = get_db()
    ctx = removal_context(conn, current_user.id, viewer_is_admin=False)
    back = redirect(url_for('user.profile', username=current_user.username))
    if ctx['last_admin']:
        flash("You're the only admin. Make someone else an admin first.", "error")
        return back

    username = current_user.username
    if request.form.get('action') == 'deactivate':
        deactivate_account(conn, current_user.id)
        logout_user()
        current_app.logger.warning(f"User {username} deactivated their own account")
        flash("Your account is deactivated. Ask an admin if you want it back.", "success")
        return redirect(url_for('auth.login'))

    row = conn.execute('SELECT password FROM users WHERE id = ?', (current_user.id,)).fetchone()
    password = request.form.get('password', '')
    if not password or not bcrypt.checkpw(password.encode('utf-8'), row['password'].encode('utf-8')):
        flash("Password is incorrect; nothing was deleted.", "error")
        return back

    books_to = request.form.get('books_to')
    # Users can only hand books to their household (or nobody); admins choose anyone in the admin page.
    if books_to not in (None, '', 'none') and not (
            books_to.isdigit() and any(m['id'] == int(books_to) for m in ctx['household'])):
        flash("You can only give your books to a household member, or to no one.", "error")
        return back
    try:
        username, owned, new_owner, files = delete_account(conn, current_user.id, books_to)
    except AccountError as e:
        conn.rollback()
        flash(str(e), "error")
        return back

    logout_user()
    from utils.image_utils import delete_image_file
    for path in files:
        delete_image_file(path)
    current_app.logger.warning(f"User {username} deleted their own account (books -> {new_owner or 'none'})")
    flash("Your account has been deleted." + (f" Your books went to {new_owner}." if owned and new_owner else ""), "success")
    return redirect(url_for('auth.login'))


@user_blueprint.route('/import_goodreads_page')
@login_required
def import_goodreads_page():
    """Display the Goodreads import page with instructions"""
    return render_template('goodreads_import.html')

def format_goodreads_date(date_str):
    """Convert Goodreads date format (YYYY/MM/DD) to SQLite format (YYYY-MM-DD)"""
    if not date_str:
        return None
    # Replace forward slashes with dashes for proper SQLite date sorting
    return date_str.replace('/', '-')

def goodreads_review_text(review):
    """Goodreads exports reviews as HTML. Store plain text: <br> becomes a
    newline (so <br/><br/> is a paragraph break), other tags are dropped and
    entities like &amp; are decoded. Reviews are shown with pre-wrap."""
    import html
    text = (review or '').replace('\r\n', '\n')
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    text = html.unescape(text)
    return re.sub(r'\n{3,}', '\n\n', text).strip()


@user_blueprint.route('/import_goodreads', methods=['POST'])
@login_required
@limiter.limit("3 per hour")
def import_goodreads():
    """Import library data from Goodreads CSV export"""
    import logging
    logger = logging.getLogger(__name__)

    try:
        # Check if file was uploaded
        if 'goodreads_csv' not in request.files:
            return jsonify({'success': False, 'message': 'No file uploaded'}), 400

        file = request.files['goodreads_csv']

        if file.filename == '':
            return jsonify({'success': False, 'message': 'No file selected'}), 400

        if not file.filename.endswith('.csv'):
            return jsonify({'success': False, 'message': 'File must be a CSV'}), 400

        # Read CSV content
        csv_content = file.read().decode('utf-8')
        csv_reader = csv.DictReader(StringIO(csv_content))

        conn = get_db_connection()
        stats = {
            'books_added': 0,
            'wishlist_added': 0,
            'ratings_added': 0,
            'duplicates_skipped': 0,
            'collection_added': 0,
            'sessions_added': 0,
            'rows_processed': 0,
            'unknown_shelf': 0,
            'errors': []
        }

        try:
            for row in csv_reader:
                stats['rows_processed'] += 1
                try:
                    # Extract book data from Goodreads CSV
                    title = row.get('Title', '').strip()
                    author = row.get('Author', '').strip()
                    isbn = row.get('ISBN13', '').strip() or row.get('ISBN', '').strip()
                    isbn = isbn.replace('="', '').replace('"', '').strip()  # Clean ISBN formatting

                    publisher = row.get('Publisher', '').strip()
                    year = row.get('Year Published', '').strip() or row.get('Original Publication Year', '').strip()
                    pages = row.get('Number of Pages', '').strip()
                    my_rating = row.get('My Rating', '').strip()
                    # Format dates to use dashes instead of slashes for proper SQLite sorting
                    date_read = format_goodreads_date(row.get('Date Read', '').strip())
                    date_added = format_goodreads_date(row.get('Date Added', '').strip())
                    bookshelves = row.get('Bookshelves', '').strip()
                    exclusive_shelf = row.get('Exclusive Shelf', '').strip()
                    my_review = goodreads_review_text(row.get('My Review', ''))

                    # Skip if no title
                    if not title:
                        continue

                    # Determine shelf (use Exclusive Shelf first, then Bookshelves)
                    shelf = exclusive_shelf or bookshelves

                    # Debug logging
                    if stats['rows_processed'] <= 3:
                        logger.info(f"Row {stats['rows_processed']}: Title='{title}', Shelf='{shelf}', Exclusive='{exclusive_shelf}', Bookshelves='{bookshelves}'")

                    # Check if book already exists (by ISBN or title+author)
                    existing_book = None
                    if isbn:
                        existing_book = conn.execute(
                            'SELECT * FROM books WHERE isbn = ?', (isbn,)
                        ).fetchone()

                    if not existing_book and title and author:
                        existing_book = conn.execute(
                            'SELECT * FROM books WHERE LOWER(title) = LOWER(?) AND LOWER(author) = LOWER(?)',
                            (title, author)
                        ).fetchone()

                    # If book doesn't exist, create it
                    if not existing_book:
                        # For bulk import, use Goodreads data directly (API calls are too slow)
                        # Covers can be fetched later via separate feature
                        final_title = title
                        final_author = author
                        final_isbn = isbn
                        final_publisher = publisher
                        final_year = year
                        final_pages = pages
                        cover_url = ''  # Will fetch covers later
                        description = ''
                        subtitle = ''
                        genre = ''

                        # Insert book into database
                        cursor = conn.execute('''
                            INSERT INTO books (title, author, isbn, publisher, publish_year,
                                             page_count, cover_image_url, description, subtitle,
                                             genre, added_by)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (final_title, final_author, final_isbn, final_publisher,
                              final_year, final_pages, cover_url, description, subtitle,
                              genre, current_user.id))

                        book_id = cursor.lastrowid
                        stats['books_added'] += 1
                    else:
                        book_id = existing_book['id']

                    # Handle different shelves
                    if shelf in ['to-read', 'want-to-read']:
                        # Add to wishlist
                        existing_wishlist = conn.execute(
                            'SELECT * FROM wishlist WHERE user_id = ? AND book_id = ?',
                            (current_user.id, book_id)
                        ).fetchone()

                        if not existing_wishlist:
                            conn.execute('''
                                INSERT INTO wishlist (user_id, book_id, notes, added_at)
                                VALUES (?, ?, ?, ?)
                            ''', (current_user.id, book_id, my_review or '', date_added or None))
                            stats['wishlist_added'] += 1
                            logger.info(f"Added '{title}' to wishlist")

                    elif shelf in ['read', 'currently-reading']:
                        # Check if already in collections
                        existing_collection = conn.execute(
                            'SELECT * FROM collections WHERE user_id = ? AND book_id = ?',
                            (current_user.id, book_id)
                        ).fetchone()

                        if existing_collection:
                            stats['duplicates_skipped'] += 1
                            logger.info(f"Skipping '{title}' - already in collections")
                            continue

                        # Map shelf to collection status
                        if shelf == 'read':
                            status = 'read'
                        elif shelf == 'currently-reading':
                            status = 'currently reading'
                        else:
                            status = 'want to read'

                        # Add to collections (date_added is already formatted)
                        conn.execute('''
                            INSERT INTO collections (user_id, book_id, status, created_at)
                            VALUES (?, ?, ?, ?)
                        ''', (current_user.id, book_id, status, date_added))
                        stats['collection_added'] += 1
                        logger.info(f"Added '{title}' to collections with status '{status}'")

                        # Add rating and review if provided
                        if my_rating and my_rating != '0':
                            conn.execute('''
                                INSERT INTO read_data (user_id, book_id, rating, comment)
                                VALUES (?, ?, ?, ?)
                            ''', (current_user.id, book_id, int(my_rating), my_review or ''))
                            stats['ratings_added'] += 1

                        # Add reading session if date_read is provided (date_read is already formatted)
                        if date_read and shelf == 'read':
                            conn.execute('''
                                INSERT INTO reading_sessions (user_id, book_id, date_started, date_completed)
                                VALUES (?, ?, ?, ?)
                            ''', (current_user.id, book_id, None, date_read))
                            stats['sessions_added'] += 1
                    else:
                        stats['unknown_shelf'] += 1
                        if stats['unknown_shelf'] <= 5:
                            logger.warning(f"Unknown shelf '{shelf}' for book '{title}'")

                except Exception as row_error:
                    logger.error(f"Error processing row: {row_error}")
                    stats['errors'].append(f"Error with book '{title}': {str(row_error)}")
                    continue

            conn.commit()

            logger.info(f"Import completed: {stats}")

            # Return success with detailed stats
            result = {
                'success': True,
                **stats
            }

            # If nothing was added, include a warning
            if stats['books_added'] == 0 and stats['wishlist_added'] == 0 and stats['collection_added'] == 0:
                result['message'] = f"No items imported. Processed {stats['rows_processed']} rows. Unknown shelves: {stats['unknown_shelf']}. Check logs for details."

            return jsonify(result)

        except Exception as e:
            conn.rollback()
            logger.error(f"Import error: {str(e)}", exc_info=True)
            return jsonify({'success': False, 'message': 'The import failed. Check that the file is a Goodreads CSV export.'}), 500

        finally:
            conn.close()

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'message': 'The import failed. Check that the file is a Goodreads CSV export.'}), 500


@user_blueprint.route('/add_to_shared_library/<int:user_id>', methods=['POST'])
@login_required
@limiter.limit("20 per hour")
def add_to_shared_library(user_id):
    """Add a friend to your shared library"""
    conn = get_db_connection()
    try:
        # Get the friend's info
        friend = conn.execute(
            'SELECT username FROM users WHERE id = ?', (user_id,)
        ).fetchone()

        if not friend:
            flash('User not found', 'error')
            return redirect(request.referrer or url_for('base.index'))

        # Check if they are friends
        if not is_friends_with(current_user.id, user_id):
            flash('You can only add friends to your shared library', 'error')
            return redirect(request.referrer or url_for('base.index'))

        # Check if current user already in a library group
        existing_lib = conn.execute(
            'SELECT library_id FROM library_members WHERE user_id = ?',
            (current_user.id,)
        ).fetchone()

        if existing_lib:
            library_id = existing_lib['library_id']
        else:
            # Create new library group
            max_lib = conn.execute('SELECT MAX(library_id) as max_id FROM library_members').fetchone()
            library_id = (max_lib['max_id'] or 0) + 1

            # Add current user to new library
            conn.execute('''
                INSERT INTO library_members (library_id, user_id, role, added_by)
                VALUES (?, ?, 'owner', ?)
            ''', (library_id, current_user.id, current_user.id))

        # Don't silently pull someone out of a library they already belong to
        friend_lib = conn.execute(
            'SELECT library_id FROM library_members WHERE user_id = ?', (user_id,)
        ).fetchone()
        if friend_lib:
            if friend_lib['library_id'] != library_id:
                flash(f"{friend['username']} is already in another shared library. They need to leave it first.", 'error')
            else:
                flash(f"{friend['username']} is already in your shared library", 'info')
            conn.rollback()
            return redirect(request.referrer or url_for('user.profile', username=friend['username']))

        conn.execute('''
            INSERT INTO library_members (library_id, user_id, role, added_by)
            VALUES (?, ?, 'member', ?)
        ''', (library_id, user_id, current_user.id))

        conn.commit()
        flash(f"{friend['username']} added to your shared library!", 'success')
        current_app.logger.info(
            f"User {current_user.username} added {friend['username']} to shared library"
        )

    except Exception as e:
        current_app.logger.error(f"Error adding to shared library: {str(e)}")
        flash('Error adding to shared library', 'error')
    finally:
        conn.close()

    return redirect(request.referrer or url_for('user.profile', username=friend['username']))


@user_blueprint.route('/remove_from_shared_library/<int:user_id>', methods=['POST'])
@login_required
@limiter.limit("20 per hour")
def remove_from_shared_library(user_id):
    """Remove a user from your shared library"""
    conn = get_db_connection()
    try:
        # Get the user's info
        user = conn.execute(
            'SELECT username FROM users WHERE id = ?', (user_id,)
        ).fetchone()

        if not user:
            flash('User not found', 'error')
            return redirect(request.referrer or url_for('base.index'))

        # Check if they share a library
        if not shares_library_with(current_user.id, user_id):
            flash('This user is not in your shared library', 'error')
            return redirect(request.referrer or url_for('base.index'))

        # Remove from library
        conn.execute('DELETE FROM library_members WHERE user_id = ?', (user_id,))
        conn.commit()

        flash(f"{user['username']} removed from your shared library", 'success')
        current_app.logger.info(
            f"User {current_user.username} removed {user['username']} from shared library"
        )

    except Exception as e:
        current_app.logger.error(f"Error removing from shared library: {str(e)}")
        flash('Error removing from shared library', 'error')
    finally:
        conn.close()

    return redirect(request.referrer or url_for('user.profile', username=user['username']))

