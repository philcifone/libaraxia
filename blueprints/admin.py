from flask import render_template, redirect, url_for, request, flash, Blueprint, current_app, jsonify
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
import bcrypt
import os
from datetime import datetime
from utils.database import get_db
from utils import households
from utils.book_utils import missing_cover_sql
from models import admin_required, is_valid_username, USERNAME_RULES
from utils.accounts import removal_context, deactivate_account, delete_account, AccountError
from PIL import Image

admin_blueprint = Blueprint('admin', __name__, template_folder='templates')


@admin_blueprint.route("/settings")
@login_required
@admin_required
def settings():
    """Admin settings page - user management"""
    conn = get_db()
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
        'total_books': conn.execute('SELECT COUNT(*) FROM library_books WHERE removed_at IS NULL').fetchone()[0],
        'admin_users': conn.execute('SELECT COUNT(*) FROM users WHERE is_admin = 1').fetchone()[0],
        'unowned_books': conn.execute('SELECT COUNT(*) FROM books WHERE added_by IS NULL').fetchone()[0],
    }

    # Get library membership info
    library_members = conn.execute("""
        SELECT
            lm.id,
            lm.library_id,
            lm.user_id,
            lm.role,
            lm.added_at,
            u.username,
            u.avatar_url,
            adder.username as added_by_username
        FROM library_members lm
        JOIN users u ON lm.user_id = u.id
        LEFT JOIN users adder ON lm.added_by = adder.id
        ORDER BY lm.library_id, lm.added_at
    """).fetchall()

    # Group members by library_id
    libraries = {}
    for member in library_members:
        lib_id = member['library_id']
        if lib_id not in libraries:
            libraries[lib_id] = []
        libraries[lib_id].append(dict(member))

    return render_template('admin_settings.html',
                         users=users,
                         stats=stats,
                         libraries=libraries)


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

    if not is_valid_username(username):
        flash(USERNAME_RULES, "error")
        return redirect(url_for('admin.settings'))

    conn = get_db()
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

    conn = get_db()
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

    return redirect(url_for('admin.settings'))


@admin_blueprint.route("/users/<int:user_id>/removal")
@login_required
@admin_required
def user_removal_dialog(user_id):
    """Dialog content (HTML fragment) for deactivating/deleting a user."""
    if user_id == current_user.id:
        return '<p class="text-content-primary">To leave, use Profile → Account on your own profile.</p>' \
               '<div class="flex justify-end pt-4"><button type="button" class="account-removal-cancel px-4 py-2 border border-card">Close</button></div>'
    ctx = removal_context(get_db(), user_id, viewer_is_admin=True)
    if not ctx:
        return '<p class="text-content-primary">User not found.</p>', 404
    return render_template('_account_removal.html', ctx=ctx, is_self=False,
                           action_url=url_for('admin.delete_user'),
                           export_url=url_for('user.export_data', user_id=user_id))


@admin_blueprint.route("/delete_user", methods=["POST"])
@login_required
@admin_required
def delete_user():
    """Deactivate or permanently delete another user (see utils/accounts.py)."""
    user_id = request.form.get('user_id', type=int)
    action = request.form.get('action', 'delete')

    if user_id == current_user.id:
        flash("Use Profile → Account to deactivate or delete your own account.", "error")
        return redirect(url_for('admin.settings'))

    conn = get_db()
    ctx = removal_context(conn, user_id, viewer_is_admin=True)
    if not ctx:
        flash("User not found", "error")
        return redirect(url_for('admin.settings'))
    if ctx['last_admin']:
        flash("Cannot remove the last admin user", "error")
        return redirect(url_for('admin.settings'))

    username = ctx['user']['username']
    if action == 'deactivate':
        deactivate_account(conn, user_id)
        flash(f"'{username}' deactivated. Everything is kept; reactivate them any time.", "success")
        current_app.logger.warning(f"Admin {current_user.username} deactivated user: {username}")
        return redirect(url_for('admin.settings'))

    try:
        username, owned, new_owner, files = delete_account(conn, user_id, request.form.get('books_to'))
    except AccountError as e:
        conn.rollback()
        flash(str(e), "error")
        return redirect(url_for('admin.settings'))

    from utils.image_utils import delete_image_file
    for path in files:
        delete_image_file(path)
    if owned:
        flash(f"User '{username}' deleted. Their {owned} book(s) went to {new_owner or 'no owner'}.", "success")
    else:
        flash(f"User '{username}' and their data deleted.", "success")
    current_app.logger.warning(
        f"Admin {current_user.username} deleted user: {username} (books -> {new_owner or 'none'})")
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

    conn = get_db()
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

    conn = get_db()
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

    conn = get_db()
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

        # Check file size
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)  # Reset file pointer

        max_size = current_app.config.get('MAX_CONTENT_LENGTH', 20 * 1024 * 1024)
        if file_size > max_size:
            max_size_mb = max_size / (1024 * 1024)
            logger.error(f"File too large: {file_size} bytes")
            return jsonify({'success': False, 'message': f'File size must be less than {max_size_mb:.0f}MB'}), 400

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

                # Resize to a reasonable size (400x400) while maintaining aspect ratio
                img.thumbnail((400, 400), Image.Resampling.LANCZOS)

                # Save the image
                img.save(filepath, quality=85, optimize=True)
                logger.info(f"Image saved to: {filepath}")

            except Exception as e:
                logger.error(f"Error processing image: {str(e)}")
                return jsonify({'success': False, 'message': 'Error processing the image.'}), 500

            # Get relative path for database storage (use forward slashes for URLs)
            relative_path = f'uploads/avatars/{unique_filename}'

            conn = get_db()
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


    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'message': 'Something went wrong. Please try again.'}), 500


@admin_blueprint.route("/remove_user_avatar", methods=["POST"])
@login_required
@admin_required
def remove_user_avatar():
    """Remove avatar for a user (admin only)"""
    try:
        data = request.get_json()
        user_id = data.get('user_id') if data else None

        if not user_id:
            return jsonify({'success': False, 'message': 'User ID required'}), 400

        # Convert to int if needed
        try:
            user_id = int(user_id)
        except (ValueError, TypeError):
            return jsonify({'success': False, 'message': 'Invalid user ID'}), 400

        conn = get_db()
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


    except Exception as e:
        current_app.logger.error(f"Error removing avatar: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'message': 'Something went wrong. Please try again.'}), 500


@admin_blueprint.route("/unowned_books")
@login_required
@admin_required
def unowned_books():
    """Books with no owner (their owner's account was deleted with "no owner",
    or they predate ownership). They show in no library until reassigned."""
    conn = get_db()
    books = conn.execute('''
        SELECT b.id, b.title, b.author, b.cover_image_url, b.removed_at,
               (SELECT COUNT(*) FROM read_data r WHERE r.book_id = b.id
                  AND (r.rating IS NOT NULL OR r.comment IS NOT NULL)) AS reviews,
               EXISTS (SELECT 1 FROM wishlist w WHERE w.book_id = b.id) AS wishlisted
        FROM books b WHERE b.added_by IS NULL
        ORDER BY LOWER(b.title)
    ''').fetchall()
    users = conn.execute('SELECT id, username FROM users ORDER BY username').fetchall()
    return render_template('admin/unowned_books.html', books=books, users=users)


@admin_blueprint.route("/reassign_books", methods=["POST"])
@login_required
@admin_required
def reassign_books():
    """Give unowned books to a user: one (book_id) or all of them (all=1)."""
    conn = get_db()
    new_owner = conn.execute('SELECT id, username FROM users WHERE id = ?',
                             (request.form.get('new_owner_id', type=int),)).fetchone()
    if not new_owner:
        flash("Choose a user to give the books to.", "error")
        return redirect(url_for('admin.unowned_books'))
    if request.form.get('all') == '1':
        n = conn.execute('UPDATE books SET added_by = ? WHERE added_by IS NULL', (new_owner['id'],)).rowcount
    else:
        n = conn.execute('UPDATE books SET added_by = ? WHERE id = ? AND added_by IS NULL',
                         (new_owner['id'], request.form.get('book_id', type=int))).rowcount
    conn.commit()
    flash(f"{n} book(s) given to {new_owner['username']}.", "success" if n else "error")
    current_app.logger.info(f"Admin {current_user.username} reassigned {n} unowned book(s) to {new_owner['username']}")
    return redirect(url_for('admin.unowned_books'))


@admin_blueprint.route("/orphaned_images")
@login_required
@admin_required
def orphaned_images():
    """Display orphaned images that can be cleaned up"""
    conn = get_db()
    from utils.image_utils import find_orphaned_images
    orphaned_data = find_orphaned_images(conn)

    return render_template(
        'admin/orphaned_images.html',
        orphaned_files=orphaned_data['orphaned_files'],
        total_size_mb=orphaned_data['total_size_mb'],
        count=orphaned_data['count']
    )


@admin_blueprint.route("/cleanup_orphaned_images", methods=["POST"])
@login_required
@admin_required
def cleanup_orphaned_images():
    """Delete selected orphaned image files"""
    try:
        # Get list of files to delete from form
        files_to_delete = request.form.getlist('files[]')

        if not files_to_delete:
            flash("No files selected for deletion", "warning")
            return redirect(url_for('admin.orphaned_images'))

        from utils.image_utils import cleanup_orphaned_images
        result = cleanup_orphaned_images(files_to_delete)

        if result['deleted'] > 0:
            flash(f"Successfully deleted {result['deleted']} orphaned image(s)", "success")

        if result['failed'] > 0:
            flash(f"Failed to delete {result['failed']} file(s)", "error")
            for error in result['errors']:
                current_app.logger.error(error)

        current_app.logger.info(f"Admin {current_user.username} cleaned up {result['deleted']} orphaned images")

        return redirect(url_for('admin.orphaned_images'))

    except Exception as e:
        current_app.logger.error(f"Error cleaning up orphaned images: {str(e)}", exc_info=True)
        flash("Something went wrong deleting the files; see the server log.", "error")
        return redirect(url_for('admin.orphaned_images'))


@admin_blueprint.route("/placeholder_covers")
@login_required
@admin_required
def placeholder_covers():
    """Books whose cover is a downloaded placeholder ("image not available")."""
    from utils.book_utils import find_placeholder_covers
    conn = get_db()
    missing = conn.execute("SELECT COUNT(*) " + MISSING_COVER_SQL).fetchone()[0]
    return render_template('admin/placeholder_covers.html',
                           books=find_placeholder_covers(conn),
                           missing=missing)


@admin_blueprint.route("/clear_placeholder_covers", methods=["POST"])
@login_required
@admin_required
def clear_placeholder_covers():
    from utils.book_utils import clear_placeholder_covers as clear
    result = clear(get_db())
    current_app.logger.info(f"Admin {current_user.username} cleared {result['books']} placeholder covers "
                            f"({result['files']} files deleted)")
    flash(f"Cleared {result['books']} placeholder cover(s) and deleted {result['files']} file(s). "
          "Run the bulk cover fetch to look for real ones.", "success")
    return redirect(url_for('admin.placeholder_covers'))


MISSING_COVER_SQL = missing_cover_sql()
# Fetching them is a background job: the button on placeholder_covers.html
# posts to covers.start with scope=all (blueprints/covers.py).


@admin_blueprint.route("/add_library_member", methods=["POST"])
@login_required
@admin_required
def add_library_member():
    """Add a user to a library (household)"""
    user_id = request.form.get('user_id', type=int)
    library_id = request.form.get('library_id', type=int)

    if not user_id:
        flash("User ID is required", "error")
        return redirect(url_for('admin.settings'))

    conn = get_db()
    try:
        # Check if user exists
        user = conn.execute('SELECT username FROM users WHERE id = ?', (user_id,)).fetchone()
        if not user:
            flash("User not found", "error")
            return redirect(url_for('admin.settings'))

        # Check if user is already in a library
        existing = conn.execute(
            'SELECT library_id FROM library_members WHERE user_id = ?', (user_id,)
        ).fetchone()

        if existing:
            flash(f"User '{user['username']}' is already in a library group", "warning")
            return redirect(url_for('admin.settings'))

        # If no library_id provided, create a new library, with this user as
        # its owner (every household has one; see utils/households.py)
        role = 'member'
        if not library_id:
            # Find the next available library_id
            max_lib = conn.execute('SELECT MAX(library_id) as max_id FROM library_members').fetchone()
            library_id = (max_lib['max_id'] or 0) + 1
            role = 'owner'

        # Add user to library
        conn.execute("""
            INSERT INTO library_members (library_id, user_id, role, added_by)
            VALUES (?, ?, ?, ?)
        """, (library_id, user_id, role, current_user.id))
        # Any invites they had are moot now that they're in a household
        conn.execute('DELETE FROM household_invites WHERE invitee_id = ?', (user_id,))

        conn.commit()
        flash(f"User '{user['username']}' added to library group {library_id}", "success")
        current_app.logger.info(
            f"Admin {current_user.username} added user {user['username']} to library {library_id}"
        )

    except Exception as e:
        current_app.logger.error(f"Error adding library member: {str(e)}")
        flash("Error adding user to library", "error")

    return redirect(url_for('admin.settings'))


@admin_blueprint.route("/remove_library_member", methods=["POST"])
@login_required
@admin_required
def remove_library_member():
    """Remove a user from their library (household)"""
    user_id = request.form.get('user_id', type=int)

    if not user_id:
        flash("User ID is required", "error")
        return redirect(url_for('admin.settings'))

    conn = get_db()
    try:
        # Get user info
        user = conn.execute(
            'SELECT username FROM users WHERE id = ?', (user_id,)
        ).fetchone()

        if not user:
            flash("User not found", "error")
            return redirect(url_for('admin.settings'))

        # Remove from library (hands ownership on / dissolves a household of one)
        if households.leave(conn, user_id):
            conn.commit()
            flash(f"User '{user['username']}' removed from library group", "success")
            current_app.logger.info(
                f"Admin {current_user.username} removed user {user['username']} from library"
            )
        else:
            flash(f"User '{user['username']}' was not in any library group", "info")

    except Exception as e:
        current_app.logger.error(f"Error removing library member: {str(e)}")
        flash("Error removing user from library", "error")

    return redirect(url_for('admin.settings'))

