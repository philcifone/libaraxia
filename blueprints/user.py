from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import current_user, login_required
from utils.database import get_db_connection
from models import User
import bcrypt

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

        return render_template('user.html', user=user, stats=stats)
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