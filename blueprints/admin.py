from flask import render_template, redirect, url_for, request, flash, Blueprint, current_app, jsonify
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
import bcrypt
import os
from datetime import datetime
from utils.database import get_db_connection
from models import admin_required
from PIL import Image

admin_blueprint = Blueprint('admin', __name__, template_folder='templates')


@admin_blueprint.route("/settings")
@login_required
@admin_required
def settings():
    """Admin settings page - user management"""
    conn = get_db_connection()
    try:
        # Get all users with their stats
        users = conn.execute("""
            SELECT
                u.id,
                u.username,
                u.email,
                u.is_active,
                u.is_admin,
                u.avatar_url,
                COUNT(DISTINCT rd.book_id) as books_read,
                COUNT(DISTINCT c.book_id) as books_in_library
            FROM users u
            LEFT JOIN read_data rd ON u.id = rd.user_id
            LEFT JOIN collections c ON u.id = c.user_id
            GROUP BY u.id
            ORDER BY u.username ASC
        """).fetchall()

        # Get system stats
        stats = {
            'total_users': conn.execute('SELECT COUNT(*) FROM users').fetchone()[0],
            'active_users': conn.execute('SELECT COUNT(*) FROM users WHERE is_active = 1').fetchone()[0],
            'total_books': conn.execute('SELECT COUNT(*) FROM books').fetchone()[0],
            'admin_users': conn.execute('SELECT COUNT(*) FROM users WHERE is_admin = 1').fetchone()[0]
        }

        return render_template('admin_settings.html', users=users, stats=stats)
    finally:
        conn.close()


@admin_blueprint.route("/create_user", methods=["POST"])
@login_required
@admin_required
def create_user():
    """Create a new user account"""
    username = request.form.get('username', '').strip()
    email = request.form.get('email', '').strip()
    password = request.form.get('password', '').strip()
    is_admin = request.form.get('is_admin') == 'on'

    # Validation
    if not username or not email or not password:
        flash("All fields are required", "error")
        return redirect(url_for('admin.settings'))

    if len(password) < 6:
        flash("Password must be at least 6 characters", "error")
        return redirect(url_for('admin.settings'))

    conn = get_db_connection()
    try:
        # Check if username already exists
        existing_user = conn.execute(
            'SELECT id FROM users WHERE username = ?', (username,)
        ).fetchone()

        if existing_user:
            flash(f"Username '{username}' already exists", "error")
            return redirect(url_for('admin.settings'))

        # Check if email already exists
        existing_email = conn.execute(
            'SELECT id FROM users WHERE email = ?', (email,)
        ).fetchone()

        if existing_email:
            flash(f"Email '{email}' already exists", "error")
            return redirect(url_for('admin.settings'))

        # Create new user
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        conn.execute("""
            INSERT INTO users (username, email, password, is_active, is_admin)
            VALUES (?, ?, ?, 1, ?)
        """, (username, email, hashed_password.decode('utf-8'), 1 if is_admin else 0))

        conn.commit()
        flash(f"User '{username}' created successfully", "success")
        current_app.logger.info(f"Admin {current_user.username} created user: {username}")

    except Exception as e:
        current_app.logger.error(f"Error creating user: {str(e)}")
        flash("Error creating user", "error")
    finally:
        conn.close()

    return redirect(url_for('admin.settings'))


@admin_blueprint.route("/toggle_user", methods=["POST"])
@login_required
@admin_required
def toggle_user():
    """Toggle user active status"""
    user_id = request.form.get('user_id', type=int)

    # Prevent admin from deactivating themselves
    if user_id == current_user.id:
        flash("You cannot deactivate your own account", "error")
        return redirect(url_for('admin.settings'))

    conn = get_db_connection()
    try:
        user = conn.execute('SELECT username, is_active FROM users WHERE id = ?', (user_id,)).fetchone()

        if not user:
            flash("User not found", "error")
            return redirect(url_for('admin.settings'))

        new_status = 0 if user['is_active'] else 1
        conn.execute('UPDATE users SET is_active = ? WHERE id = ?', (new_status, user_id))
        conn.commit()

        status_text = "activated" if new_status else "deactivated"
        flash(f"User '{user['username']}' {status_text}", "success")
        current_app.logger.info(f"Admin {current_user.username} {status_text} user: {user['username']}")

    except Exception as e:
        current_app.logger.error(f"Error toggling user status: {str(e)}")
        flash("Error updating user status", "error")
    finally:
        conn.close()

    return redirect(url_for('admin.settings'))


@admin_blueprint.route("/delete_user", methods=["POST"])
@login_required
@admin_required
def delete_user():
    """Delete a user account"""
    user_id = request.form.get('user_id', type=int)

    # Prevent admin from deleting themselves
    if user_id == current_user.id:
        flash("You cannot delete your own account", "error")
        return redirect(url_for('admin.settings'))

    conn = get_db_connection()
    try:
        user = conn.execute('SELECT username, is_admin FROM users WHERE id = ?', (user_id,)).fetchone()

        if not user:
            flash("User not found", "error")
            return redirect(url_for('admin.settings'))

        # Prevent deleting the last admin
        if user['is_admin']:
            admin_count = conn.execute('SELECT COUNT(*) FROM users WHERE is_admin = 1').fetchone()[0]
            if admin_count <= 1:
                flash("Cannot delete the last admin user", "error")
                return redirect(url_for('admin.settings'))

        # Delete user and their associated data
        username = user['username']

        # Delete user's data (cascading delete)
        conn.execute('DELETE FROM read_data WHERE user_id = ?', (user_id,))
        conn.execute('DELETE FROM collections WHERE user_id = ?', (user_id,))
        conn.execute('DELETE FROM book_tags WHERE user_id = ?', (user_id,))
        conn.execute('DELETE FROM collection_books WHERE collection_id IN (SELECT collection_id FROM user_collections WHERE user_id = ?)', (user_id,))
        conn.execute('DELETE FROM user_collections WHERE user_id = ?', (user_id,))
        conn.execute('DELETE FROM users WHERE id = ?', (user_id,))

        conn.commit()
        flash(f"User '{username}' and all associated data deleted", "success")
        current_app.logger.warning(f"Admin {current_user.username} deleted user: {username}")

    except Exception as e:
        current_app.logger.error(f"Error deleting user: {str(e)}")
        flash("Error deleting user", "error")
    finally:
        conn.close()

    return redirect(url_for('admin.settings'))


@admin_blueprint.route("/toggle_admin", methods=["POST"])
@login_required
@admin_required
def toggle_admin():
    """Toggle user admin status"""
    user_id = request.form.get('user_id', type=int)

    # Prevent admin from removing their own admin status
    if user_id == current_user.id:
        flash("You cannot change your own admin status", "error")
        return redirect(url_for('admin.settings'))

    conn = get_db_connection()
    try:
        user = conn.execute('SELECT username, is_admin FROM users WHERE id = ?', (user_id,)).fetchone()

        if not user:
            flash("User not found", "error")
            return redirect(url_for('admin.settings'))

        # If removing admin status, check if they're the last admin
        if user['is_admin']:
            admin_count = conn.execute('SELECT COUNT(*) FROM users WHERE is_admin = 1').fetchone()[0]
            if admin_count <= 1:
                flash("Cannot remove admin status from the last admin", "error")
                return redirect(url_for('admin.settings'))

        new_status = 0 if user['is_admin'] else 1
        conn.execute('UPDATE users SET is_admin = ? WHERE id = ?', (new_status, user_id))
        conn.commit()

        status_text = "granted admin privileges to" if new_status else "revoked admin privileges from"
        flash(f"{status_text.capitalize()} user '{user['username']}'", "success")
        current_app.logger.info(f"Admin {current_user.username} {status_text}: {user['username']}")

    except Exception as e:
        current_app.logger.error(f"Error toggling admin status: {str(e)}")
        flash("Error updating admin status", "error")
    finally:
        conn.close()

    return redirect(url_for('admin.settings'))


@admin_blueprint.route("/update_user_email", methods=["POST"])
@login_required
@admin_required
def update_user_email():
    """Update a user's email address"""
    user_id = request.form.get('user_id', type=int)
    new_email = request.form.get('new_email', '').strip()

    if not new_email:
        flash("Email address is required", "error")
        return redirect(url_for('admin.settings'))

    conn = get_db_connection()
    try:
        # Check if user exists
        user = conn.execute('SELECT username FROM users WHERE id = ?', (user_id,)).fetchone()
        if not user:
            flash("User not found", "error")
            return redirect(url_for('admin.settings'))

        # Check if email is already in use
        existing = conn.execute('SELECT id FROM users WHERE email = ? AND id != ?', (new_email, user_id)).fetchone()
        if existing:
            flash(f"Email '{new_email}' is already in use", "error")
            return redirect(url_for('admin.settings'))

        # Update email
        conn.execute('UPDATE users SET email = ? WHERE id = ?', (new_email, user_id))
        conn.commit()

        flash(f"Email updated for user '{user['username']}'", "success")
        current_app.logger.info(f"Admin {current_user.username} updated email for user: {user['username']}")

    except Exception as e:
        current_app.logger.error(f"Error updating email: {str(e)}")
        flash("Error updating email address", "error")
    finally:
        conn.close()

    return redirect(url_for('admin.settings'))


@admin_blueprint.route("/reset_user_password", methods=["POST"])
@login_required
@admin_required
def reset_user_password():
    """Reset a user's password"""
    user_id = request.form.get('user_id', type=int)
    new_password = request.form.get('new_password', '').strip()

    if not new_password:
        flash("Password is required", "error")
        return redirect(url_for('admin.settings'))

    if len(new_password) < 6:
        flash("Password must be at least 6 characters", "error")
        return redirect(url_for('admin.settings'))

    conn = get_db_connection()
    try:
        # Check if user exists
        user = conn.execute('SELECT username FROM users WHERE id = ?', (user_id,)).fetchone()
        if not user:
            flash("User not found", "error")
            return redirect(url_for('admin.settings'))

        # Update password
        hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
        conn.execute('UPDATE users SET password = ? WHERE id = ?', (hashed_password.decode('utf-8'), user_id))
        conn.commit()

        flash(f"Password reset for user '{user['username']}'", "success")
        current_app.logger.info(f"Admin {current_user.username} reset password for user: {user['username']}")

    except Exception as e:
        current_app.logger.error(f"Error resetting password: {str(e)}")
        flash("Error resetting password", "error")
    finally:
        conn.close()

    return redirect(url_for('admin.settings'))


@admin_blueprint.route("/upload_user_avatar", methods=["POST"])
@login_required
@admin_required
def upload_user_avatar():
    """Upload avatar for a user (admin only)"""
    import logging
    logger = logging.getLogger(__name__)

    try:
        user_id = request.form.get('user_id', type=int)
        if not user_id:
            return jsonify({'success': False, 'message': 'User ID required'}), 400

        logger.info(f"Admin {current_user.username} uploading avatar for user {user_id}")

        # Check if the post request has the file part
        if 'avatar' not in request.files:
            return jsonify({'success': False, 'message': 'No file uploaded'}), 400

        file = request.files['avatar']

        if file.filename == '':
            return jsonify({'success': False, 'message': 'No file selected'}), 400

        # Validate file type
        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
        if '.' not in file.filename or file.filename.rsplit('.', 1)[1].lower() not in allowed_extensions:
            return jsonify({'success': False, 'message': 'Invalid file type'}), 400

        if file:
            # Secure the filename and create a unique name
            filename = secure_filename(file.filename)
            file_ext = filename.rsplit('.', 1)[1].lower()
            unique_filename = f"user_{user_id}_{int(os.urandom(4).hex(), 16)}.{file_ext}"

            # Create uploads/avatars directory if it doesn't exist
            avatar_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], 'avatars')
            os.makedirs(avatar_folder, exist_ok=True)

            filepath = os.path.join(avatar_folder, unique_filename)

            # Process and resize image
            try:
                img = Image.open(file)

                # Convert RGBA to RGB if necessary
                if img.mode in ('RGBA', 'LA', 'P'):
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                    img = background

                # Resize to a reasonable size (400x400) while maintaining aspect ratio
                img.thumbnail((400, 400), Image.Resampling.LANCZOS)

                # Save the image
                img.save(filepath, quality=85, optimize=True)
                logger.info(f"Image saved to: {filepath}")

            except Exception as e:
                logger.error(f"Error processing image: {str(e)}")
                return jsonify({'success': False, 'message': f'Error processing image: {str(e)}'}), 500

            # Get relative path for database storage (use forward slashes for URLs)
            relative_path = f'uploads/avatars/{unique_filename}'

            conn = get_db_connection()
            try:
                # Get old avatar URL to delete old file
                old_avatar = conn.execute('SELECT avatar_url, username FROM users WHERE id = ?', (user_id,)).fetchone()

                if not old_avatar:
                    return jsonify({'success': False, 'message': 'User not found'}), 404

                # Update database with new avatar URL
                conn.execute('UPDATE users SET avatar_url = ? WHERE id = ?', (relative_path, user_id))
                conn.commit()
                logger.info(f"Database updated for user {old_avatar['username']}")

                # Delete old avatar file if it exists
                if old_avatar['avatar_url']:
                    old_file_path = os.path.join(current_app.root_path, 'static', old_avatar['avatar_url'])
                    if os.path.exists(old_file_path):
                        try:
                            os.remove(old_file_path)
                            logger.info(f"Deleted old avatar: {old_file_path}")
                        except Exception as e:
                            logger.warning(f"Could not delete old avatar: {str(e)}")

                current_app.logger.info(f"Admin {current_user.username} uploaded avatar for user: {old_avatar['username']}")

                return jsonify({
                    'success': True,
                    'message': 'Avatar uploaded successfully',
                    'avatar_url': url_for('static', filename=relative_path)
                })

            finally:
                conn.close()

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'message': f'An error occurred: {str(e)}'}), 500


@admin_blueprint.route("/remove_user_avatar", methods=["POST"])
@login_required
@admin_required
def remove_user_avatar():
    """Remove avatar for a user (admin only)"""
    try:
        data = request.get_json()
        user_id = data.get('user_id', type=int) if data else None

        if not user_id:
            return jsonify({'success': False, 'message': 'User ID required'}), 400

        conn = get_db_connection()
        try:
            # Get user's current avatar
            user = conn.execute('SELECT username, avatar_url FROM users WHERE id = ?', (user_id,)).fetchone()

            if not user:
                return jsonify({'success': False, 'message': 'User not found'}), 404

            # Delete avatar file if it exists
            if user['avatar_url']:
                old_file_path = os.path.join(current_app.root_path, 'static', user['avatar_url'])
                if os.path.exists(old_file_path):
                    try:
                        os.remove(old_file_path)
                        current_app.logger.info(f"Deleted avatar file: {old_file_path}")
                    except Exception as e:
                        current_app.logger.warning(f"Could not delete avatar file: {str(e)}")

            # Update database to remove avatar URL
            conn.execute('UPDATE users SET avatar_url = NULL WHERE id = ?', (user_id,))
            conn.commit()

            current_app.logger.info(f"Admin {current_user.username} removed avatar for user: {user['username']}")

            return jsonify({
                'success': True,
                'message': 'Avatar removed successfully'
            })

        finally:
            conn.close()

    except Exception as e:
        current_app.logger.error(f"Error removing avatar: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'message': f'An error occurred: {str(e)}'}), 500
