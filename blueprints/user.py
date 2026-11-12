from flask import Blueprint, render_template, redirect, url_for, request, flash, make_response, jsonify, current_app
from flask_login import current_user, login_required, logout_user
from utils.database import get_db
from utils.accounts import removal_context, deactivate_account, delete_account, AccountError
from utils.export import library_csv, data_zip
from utils import households
from utils.email_utils import send_verification_email
from utils.book_utils import missing_cover_sql
from utils import bulk, media, reviews, shelves, personal_backups
from utils.stats import type_stats as stats_for_type, reading_goals, all_stats
from utils.media import BOOK, VIDEO, RECORD, only
from utils.rate_limiting import limiter
from models import User, admin_required, get_friendship_status, is_friends_with, shares_library_with, is_valid_username, USERNAME_RULES, THEME_STYLES, THEME_MODES, ACCENTS, FONTS
from werkzeug.utils import secure_filename
import bcrypt
import os
from datetime import datetime
from PIL import Image

# Initialize Blueprint
user_blueprint = Blueprint('user', __name__)

# Allowed extensions for profile pictures
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@user_blueprint.route('/<username>')
@login_required
def profile(username):
    # Ensure the current user is authenticated
    if not current_user.is_authenticated:
        return redirect(url_for('auth.login'))

    # Fetch the user details from the database
    conn = get_db()
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

    # Stats (12.1, utils/stats.py): the same numbers for every type, books
    # always (the reading goal hangs on them), movies and music when the
    # user has any. A list of (labels, stats), for friends and yourself only.
    type_stats = []
    if are_friends:
        for kind in (BOOK, VIDEO, RECORD):
            kind_stats = stats_for_type(conn, user['id'], kind)
            if kind_stats:
                type_stats.append((media.media_labels(kind), kind_stats))
    stats = type_stats[0][1] if type_stats else None
    # The All tab (12.2) and its Year by year, which also holds past years'
    # reading goals; with books only it shows on the Books tab instead
    everything = all_stats(conn, user['id'], {m['type']: s for m, s in type_stats}) if type_stats else None
    # This year's reading goal and past years (12.3), under the bio
    goals = reading_goals(conn, user['id']) if are_friends else None

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

    # Shelves (8C) and wishlist rows (8D) for friends and yourself, drawn
    # by _shelf_rows.html: per section, only the statuses in use
    profile_shelves, wishlist_shelves = [], []
    if are_friends:
        link_user = None if is_own_profile else user['username']
        for media_type in shelves.SECTION_NAMES:
            rows = shelves.status_shelves(conn, user['id'], media_type, username=link_user,
                                          keep_empty=False)
            if rows:
                profile_shelves.append((shelves.SECTION_NAMES[media_type], rows))
        wishlist_shelves = shelves.wishlist_shelves(conn, user['id'], username=link_user)

    # Check if this user is in current user's shared library
    in_shared_library = shares_library_with(current_user.id, user['id']) if not is_own_profile else False
    # Which household button to show on someone else's profile
    household = None
    if not is_own_profile:
        mine = households.membership(conn, current_user.id)
        household = {
            'i_am_owner': bool(mine and mine['role'] == 'owner'),
            'can_invite': households.can_invite(conn, current_user.id),
            'sent': households.pending_invite(conn, current_user.id, user['id']),
            'received': households.pending_invite(conn, user['id'], current_user.id),
            'they_are_in_one': households.membership(conn, user['id']) is not None,
        }

    # Recent reviews, the same list and order as the Reviews section's
    # (utils/reviews.py), which "View all" opens. One row per review: the old
    # query joined every reading session and listed a re-read book twice.
    recent_reviews = []
    if are_friends:
        recent_reviews = [dict(r, book_id=r['id'], date_completed=r['finished'])
                          for r in reviews.reviews_by(conn, [user['id']], media.BOOK, limit=5)]

    return render_template(
        'user.html',
        user=user,
        stats=stats,
        type_stats=type_stats,
        all_stats=everything,
        goals=goals,
        current_year=current_year,
        friendship_status=friendship_status,
        is_own_profile=is_own_profile,
        are_friends=are_friends,
        friend_request_id=friend_request_id,
        friends=friends,
        profile_shelves=profile_shelves,
        wishlist_shelves=wishlist_shelves,
        in_shared_library=in_shared_library,
        household=household,
        recent_reviews=recent_reviews,
        account_removal=(removal_context(conn, current_user.id, viewer_is_admin=False)
                         if is_own_profile else None),
        # Recent bulk edits (ROADMAP 14), yours only, with their Undo
        bulk_history=bulk.recent(conn, current_user) if is_own_profile else [],
        library_backups=personal_backups.list_backups(current_user.id) if is_own_profile else [],
        backups_max=personal_backups.MAX_MANUAL,
    )

@user_blueprint.route('/update_reading_goal', methods=['POST'])
@login_required
@limiter.limit("20 per hour")
def update_reading_goal():
    """Set this year's reading goal (a reading_goals row, ROADMAP 12.3);
    0 or empty clears it. Past years' goals are kept as they were."""
    try:
        goal = int(request.form.get('reading_goal') or 0)
    except ValueError:
        flash('Reading goal must be a whole number.', 'danger')
        return redirect(url_for('user.profile', username=current_user.username))
    if goal < 0 or goal > 10000:
        flash('Reading goal must be between 0 and 10,000.', 'danger')
        return redirect(url_for('user.profile', username=current_user.username))

    year = datetime.now().year
    conn = get_db()
    try:
        if goal:
            conn.execute('''INSERT INTO reading_goals (user_id, year, goal) VALUES (?, ?, ?)
                            ON CONFLICT (user_id, year) DO UPDATE SET goal = excluded.goal''',
                         (current_user.id, year, goal))
        else:
            conn.execute('DELETE FROM reading_goals WHERE user_id = ? AND year = ?', (current_user.id, year))
        conn.commit()
        flash(f'{year} reading goal set to {goal}.' if goal else f'{year} reading goal cleared.', 'success')
    except Exception:
        conn.rollback()
        current_app.logger.exception('Reading goal update failed')
        flash('An error occurred while updating your reading goal.', 'danger')
    return redirect(url_for('user.profile', username=current_user.username))

@user_blueprint.route('/update_email', methods=['POST'])
@login_required
@limiter.limit("20 per hour")
def update_email():
    """Change the account email (inline editing). Needs the current password,
    so a hijacked session can't take over the account via a reset to a new
    address. With EMAIL_VERIFICATION_REQUIRED on, the new address has to be
    verified again before the next login."""
    data = request.get_json(silent=True) or {}
    new_email = (data.get('email') or '').strip()
    password = data.get('current_password') or ''
    if not new_email:
        return jsonify({'success': False, 'message': 'Email cannot be empty'}), 400
    if not password:
        return jsonify({'success': False, 'message': 'Enter your current password to change your email'}), 400

    conn = get_db()
    try:
        user = conn.execute('SELECT password, email FROM users WHERE id = ?', (current_user.id,)).fetchone()
        if not bcrypt.checkpw(password.encode('utf-8'), user['password'].encode('utf-8')):
            return jsonify({'success': False, 'message': 'Current password is incorrect'}), 400
        if new_email == user['email']:
            return jsonify({'success': True, 'message': 'Email unchanged'})
        if conn.execute('SELECT 1 FROM users WHERE email = ? AND id != ?',
                        (new_email, current_user.id)).fetchone():
            return jsonify({'success': False, 'message': 'Email is already in use'}), 400

        reverify = current_app.config.get('EMAIL_VERIFICATION_REQUIRED', False)
        conn.execute('UPDATE users SET email = ?, email_verified = CASE WHEN ? THEN 0 ELSE email_verified END '
                     'WHERE id = ?', (new_email, reverify, current_user.id))
        conn.commit()
    except Exception:
        conn.rollback()
        current_app.logger.exception('Error updating email')
        return jsonify({'success': False, 'message': 'An error occurred while updating email'}), 500

    message = 'Email updated successfully'
    if reverify:
        if send_verification_email(new_email, current_user.username, current_user.id):
            message = 'Email updated. Check the new address for a verification link before you next log in.'
        else:
            message = ('Email updated, but the verification email could not be sent. '
                       'Use "resend verification" on the login page.')
    return jsonify({'success': True, 'message': message})

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

        conn = get_db()
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

        conn = get_db()
        # Update bio
        conn.execute('UPDATE users SET bio = ? WHERE id = ?', (new_bio if new_bio else None, current_user.id))
        conn.commit()

        # Update the current_user object
        current_user.bio = new_bio if new_bio else None

        return jsonify({'success': True, 'message': 'Bio updated successfully'})


    except Exception as e:
        return jsonify({'success': False, 'message': 'An error occurred while updating bio'}), 500

@user_blueprint.route('/update_theme', methods=['POST'])
@login_required
# The header's cyclers (14c) save on every click, so a few rounds through
# the styles and fonts would have hit 60: it only writes the user's own row
@limiter.limit("300 per hour")
def update_theme():
    """Save the Appearance settings (style, light/dark mode, accent colour, font)."""
    data = request.get_json(silent=True) or {}
    style = data.get('style', current_user.theme_style)
    mode = data.get('mode', current_user.theme_mode)
    accent = data.get('accent', current_user.accent)
    font = data.get('font', current_user.font)
    if (style not in THEME_STYLES or mode not in THEME_MODES or accent not in ACCENTS
            or font not in FONTS):
        return jsonify({'success': False, 'message': 'Unknown theme setting'}), 400

    conn = get_db()
    try:
        conn.execute('UPDATE users SET theme_style = ?, color_mode = ?, accent = ?, font = ? WHERE id = ?',
                     (style, mode, accent, font, current_user.id))
        conn.commit()
    except Exception:
        current_app.logger.exception('Error saving theme settings')
        return jsonify({'success': False, 'message': 'Could not save appearance settings'}), 500

    current_user.theme_style, current_user.theme_mode, current_user.accent = style, mode, accent
    current_user.font = font
    return jsonify({'success': True, 'style': style, 'mode': mode, 'accent': accent, 'font': font})

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

        conn = get_db()
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

            conn = get_db()
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

        else:
            logger.error(f"Invalid file type: {file.filename}")
            return jsonify({'success': False, 'message': 'Invalid file type. Allowed: png, jpg, jpeg, gif, webp'}), 400

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'message': 'Something went wrong. Please try again.'}), 500

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


# --- Personal library backups (utils/personal_backups.py) --------------------
# Your own data only; the site backups are the admin's (blueprints/admin.py).

def _backups_back():
    """The Goodreads import page offers "Back up my library" too."""
    if request.form.get('back') == 'goodreads':
        return redirect(url_for('user.import_goodreads_page'))
    return redirect(url_for('user.profile', username=current_user.username) + '#library-backups')


@user_blueprint.route('/backups/create', methods=['POST'])
@login_required
@limiter.limit("10 per hour")
def personal_backup_create():
    from utils import personal_backups
    try:
        made = personal_backups.create(get_db(), current_user.id, current_user.username)
    except personal_backups.PersonalBackupError as e:
        flash(str(e), 'error')
        return _backups_back()
    c = made['counts']
    flash(f"Library backed up: {c['books']} items, {c['statuses']} statuses, {c['reviews']} reviews, "
          f"{c['sessions']} sessions, {c['wishlist']} wishlist entries.", 'success')
    return _backups_back()


@user_blueprint.route('/backups/<name>/restore', methods=['POST'])
@login_required
@limiter.limit("10 per hour")
def personal_backup_restore(name):
    from utils import personal_backups
    try:
        r = personal_backups.restore(get_db(), current_user.id, name)
    except personal_backups.PersonalBackupError as e:
        current_app.logger.exception(f'Personal restore {name} for {current_user.username} failed')
        flash(str(e), 'error')
        return _backups_back()
    current_app.logger.warning(f"{current_user.username} restored their library from {name}")
    when = r['restored']['created_at'].strftime('%-d %b %Y, %H:%M')
    parts = [f"Your library is back to {when}."]
    if r['books_removed']:
        parts.append(f"{r['books_removed']} item(s) added since were removed.")
    if r['books_back']:
        parts.append(f"{r['books_back']} deleted item(s) came back.")
    if r['kept']:
        parts.append("Kept, because others have data on them: " + '; '.join(
            f"{title} ({', '.join(users)})" for title, users in r['kept'][:5])
            + (f" and {len(r['kept']) - 5} more" if len(r['kept']) > 5 else '') + '.')
    if r['given_away']:
        parts.append(f"{len(r['given_away'])} item(s) you've given to someone since stay with them.")
    if r['skipped']:
        parts.append(f"{r['skipped']} status(es), review(s) or session(s) couldn't come back: their book is gone.")
    flash(' '.join(parts), 'success')
    return _backups_back()


@user_blueprint.route('/backups/<name>/delete', methods=['POST'])
@login_required
def personal_backup_delete(name):
    from utils import personal_backups
    try:
        personal_backups.delete(current_user.id, name)
    except personal_backups.PersonalBackupError as e:
        flash(str(e), 'error')
        return _backups_back()
    flash('Backup deleted.', 'success')
    return _backups_back()


# --- Goodreads import (ROADMAP 14b, utils/goodreads_plan.py) -----------------
# Upload -> review (nothing written) -> choose per row -> apply -> result,
# with undo through the bulk journal (POST /bulk/<id>/undo).

def _wants_json():
    return request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest'


@user_blueprint.route('/import_goodreads_page')
@login_required
def import_goodreads_page():
    """The upload page, with how the import works. Says so if an upload is
    still waiting for its review."""
    from utils import goodreads_plan, personal_backups
    return render_template('goodreads_import.html',
                           waiting=goodreads_plan.has_staging(get_db(), current_user),
                           last_backup=personal_backups.latest(current_user.id))


@user_blueprint.route('/import_goodreads/plan', methods=['POST'])
@login_required
@limiter.limit("10 per hour")
def import_goodreads_plan():
    """Read an uploaded export into the review's staging. Writes nothing else."""
    from utils import goodreads_plan
    from utils.goodreads import decode_csv, ImportFileError

    def refuse(message, status=400):
        if _wants_json():
            return jsonify({'success': False, 'error': message}), status
        flash(message, 'error')
        return redirect(url_for('user.import_goodreads_page'))

    file = request.files.get('goodreads_csv')
    if not file or not file.filename:
        return refuse('Choose your Goodreads export first.')
    if not file.filename.lower().endswith('.csv'):
        return refuse('The file must be a .csv export.')
    text, encoding = decode_csv(file.read())
    conn = get_db()
    try:
        count = goodreads_plan.stage(conn, current_user, text, secure_filename(file.filename) or 'export.csv')
    except ImportFileError as e:
        conn.rollback()
        return refuse(str(e))                   # written for the user
    except Exception:
        conn.rollback()
        current_app.logger.exception('Goodreads upload failed')
        return refuse('That file could not be read. Check that it is a Goodreads CSV export.', 500)
    current_app.logger.info(f'Goodreads upload by {current_user.username}: {count} rows ({encoding})')
    if encoding != 'utf-8-sig' and encoding != 'utf-8':
        flash(f"The file wasn't UTF-8; it was read as {encoding}. Check accented titles.", 'warning')
    review = url_for('user.import_goodreads_review')
    if _wants_json():
        return jsonify({'success': True, 'url': review, 'rows': count, 'encoding': encoding})
    return redirect(review)


@user_blueprint.route('/import_goodreads/review')
@login_required
def import_goodreads_review():
    """The review: every row of the upload in its box, with its choice."""
    from utils import goodreads_plan
    plan = goodreads_plan.plan(get_db(), current_user)
    if plan is None:
        flash('Upload your export first.', 'info')
        return redirect(url_for('user.import_goodreads_page'))
    return render_template('goodreads_review.html', plan=plan, boxes=goodreads_plan.BOXES,
                           choices=goodreads_plan.CHOICES)


def _plan_counts(plan):
    """What the page updates after a choice: the Import button and the fingerprint."""
    return {'fingerprint': plan.fingerprint, 'will_write': plan.will_write, 'undecided': plan.undecided}


@user_blueprint.route('/import_goodreads/choose', methods=['POST'])
@login_required
def import_goodreads_choose():
    """Save a choice for some rows: JSON {lines: [...], choice}."""
    from utils import goodreads_plan
    body = request.get_json(silent=True) or {}
    conn = get_db()
    try:
        result = goodreads_plan.choose(conn, current_user, body.get('lines'), body.get('choice'))
    except goodreads_plan.PlanError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception:
        conn.rollback()
        current_app.logger.exception('Goodreads choice failed')
        return jsonify({'success': False, 'error': 'That choice could not be saved.'}), 500
    plan = result['plan']
    saved = set(result['saved'])
    rows = {r.line: {'choice': r.choice, 'adds': r.adds, 'writes': r.writes, 'preview': r.preview}
            for r in plan.rows if r.line in saved}
    return jsonify({'success': True, 'saved': result['saved'], 'refused': result['refused'],
                    'rows': rows, **_plan_counts(plan)})


@user_blueprint.route('/import_goodreads/apply', methods=['POST'])
@login_required
@limiter.limit("3 per hour")
def import_goodreads_apply():
    """Import what the review shows: JSON {fingerprint}. Returns the result,
    one outcome per row of the file."""
    from utils import goodreads_plan, personal_backups
    body = request.get_json(silent=True) or {}
    conn = get_db()
    # Your library, as it is, before the import writes (utils/personal_backups.py).
    # No backup, no import: it's the way back if the undo isn't enough.
    try:
        personal_backups.create(conn, current_user.id, current_user.username, 'goodreads')
    except personal_backups.PersonalBackupError:
        current_app.logger.exception('Backup before the Goodreads import failed')
        return jsonify({'success': False, 'error': "Couldn't back up your library before importing, so "
                        "nothing was imported. Try again; if it keeps failing, tell your admin."}), 500
    try:
        report = goodreads_plan.apply(conn, current_user, body.get('fingerprint'))
    except goodreads_plan.StalePlan as e:
        conn.rollback()
        flash(str(e), 'warning')
        return jsonify({'success': False, 'stale': True, 'error': str(e)}), 409
    except goodreads_plan.PlanError as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception:
        conn.rollback()
        current_app.logger.exception('Goodreads import failed')
        return jsonify({'success': False, 'error': 'The import failed. Nothing was saved.'}), 500
    current_app.logger.info(f"Goodreads import by {current_user.username}: "
                            f"{report['total_rows']} rows, {report['outcomes']}")
    # Books only, as the result words it; the job it starts does all types
    covers = conn.execute("SELECT COUNT(*) " + missing_cover_sql(owner=True, types=('book',)),
                          (current_user.id,)).fetchone()[0]
    return jsonify({'success': True, 'covers_missing': covers, **report})


@user_blueprint.route('/import_goodreads/discard', methods=['POST'])
@login_required
def import_goodreads_discard():
    """Start over: the waiting upload goes."""
    from utils import goodreads_plan
    goodreads_plan.discard(get_db(), current_user)
    flash('Upload discarded. Nothing was imported.', 'info')
    return redirect(url_for('user.import_goodreads_page'))


# --- households: invite / accept / decline / remove (utils/households.py) ----

@user_blueprint.route('/household/invite/<int:user_id>', methods=['POST'])
@login_required
@limiter.limit("20 per hour")
def household_invite(user_id):
    """Invite a friend to share your library. They have to accept."""
    conn = get_db()
    friend = conn.execute('SELECT username FROM users WHERE id = ?', (user_id,)).fetchone()
    if not friend:
        flash('User not found', 'error')
        return redirect(request.referrer or url_for('base.index'))
    try:
        households.invite(conn, current_user.id, user_id)
        conn.commit()
        flash(f"Invite sent. {friend['username']} will join once they accept.", 'success')
    except households.HouseholdError as e:
        conn.rollback()
        flash(str(e), 'error')
    return redirect(request.referrer or url_for('user.profile', username=friend['username']))


@user_blueprint.route('/household/accept/<int:invite_id>', methods=['POST'])
@login_required
def household_accept(invite_id):
    conn = get_db()
    try:
        inviter = households.accept(conn, invite_id, current_user.id, current_user.username)
        conn.commit()
        flash(f"You now share a library with {inviter}.", 'success')
    except households.HouseholdError as e:
        # accept() deletes the used-up invite before refusing; keep that
        conn.commit()
        flash(str(e), 'error')
    return redirect(request.referrer or url_for('friends.notifications_page'))


@user_blueprint.route('/household/decline/<int:invite_id>', methods=['POST'])
@login_required
def household_decline(invite_id):
    """Decline an invite you received, or cancel one you sent."""
    conn = get_db()
    try:
        households.decline(conn, invite_id, current_user.id)
        conn.commit()
        flash('Invite withdrawn.' if request.form.get('cancel') else 'Invite declined.', 'info')
    except households.HouseholdError as e:
        flash(str(e), 'error')
    return redirect(request.referrer or url_for('friends.notifications_page'))


@user_blueprint.route('/household/remove/<int:user_id>', methods=['POST'])
@login_required
@limiter.limit("20 per hour")
def household_remove(user_id):
    """The owner removes a member, or anyone leaves (user_id = themselves)."""
    conn = get_db()
    user = conn.execute('SELECT username FROM users WHERE id = ?', (user_id,)).fetchone()
    if not user:
        flash('User not found', 'error')
        return redirect(request.referrer or url_for('base.index'))
    try:
        households.remove(conn, current_user.id, user_id)
        conn.commit()
        flash('You left the household.' if user_id == current_user.id
              else f"{user['username']} removed from your household.", 'success')
        current_app.logger.info(f"Household: {current_user.username} removed {user['username']}")
    except households.HouseholdError as e:
        conn.rollback()
        flash(str(e), 'error')
    return redirect(request.referrer or url_for('user.profile', username=user['username']))

