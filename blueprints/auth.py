from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from functools import wraps
import bcrypt
import sqlite3
from utils.database import get_db_connection
from utils.email_utils import send_verification_email, verify_token, resend_verification_email
from models import admin_required, User

auth_blueprint = Blueprint('auth', __name__, template_folder='templates')

def rate_limit_post(limit_string):
    """
    Decorator to apply rate limiting only to POST requests.

    Args:
        limit_string: Rate limit specification (e.g., "10 per hour")
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if request.method == 'POST':
                # Get the limiter from app extensions
                limiter = current_app.extensions.get('limiter')
                if limiter:
                    # Check the rate limit
                    limiter.limit(limit_string)(lambda: None)()
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@auth_blueprint.route('/register', methods=['GET', 'POST'])
@rate_limit_post("5 per hour")
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']

        # Ensure password is hashed using bcrypt
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            # Check if this is the first user being created
            user_count = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
            is_first_user = user_count == 0
            
            # Check if email verification is required
            email_verification_required = current_app.config.get('EMAIL_VERIFICATION_REQUIRED', False)

            # If this is the first user, make them an admin and mark as verified
            if is_first_user:
                cursor.execute(
                    'INSERT INTO users (username, email, password, is_admin, email_verified) VALUES (?, ?, ?, 1, 1)',
                    (username, email, hashed_password.decode('utf-8'))
                )
                conn.commit()
                user_id = cursor.lastrowid
                flash('Admin account created successfully!', 'success')
            else:
                # Create the user account
                email_verified = 0 if email_verification_required else 1
                cursor.execute(
                    'INSERT INTO users (username, email, password, email_verified) VALUES (?, ?, ?, ?)',
                    (username, email, hashed_password.decode('utf-8'), email_verified)
                )
                conn.commit()
                user_id = cursor.lastrowid

                # Send verification email if required
                if email_verification_required:
                    success = send_verification_email(email, username, user_id)
                    if success:
                        flash('Registration successful! Please check your email to verify your account.', 'success')
                    else:
                        flash('Registration successful! However, we could not send the verification email. Please contact support.', 'warning')
                else:
                    flash('Registration successful!', 'success')

            return redirect(url_for('auth.login'))
        except sqlite3.IntegrityError:
            flash('Email or username already registered!', 'danger')
        finally:
            conn.close()
            
    # Check if any users exist - if not, show a special message
    conn = get_db_connection()
    user_count = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    conn.close()
    
    first_run = user_count == 0
    return render_template('register.html', first_run=first_run)

@auth_blueprint.route('/login', methods=['GET', 'POST'])
@rate_limit_post("10 per hour")
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        conn.close()

        if user:
            user_dict = dict(user)
            if bcrypt.checkpw(password.encode('utf-8'), user_dict['password'].encode('utf-8')):
                # Check if email verification is required and if email is verified
                email_verification_required = current_app.config.get('EMAIL_VERIFICATION_REQUIRED', False)
                email_verified = user_dict.get('email_verified', 1) == 1

                if email_verification_required and not email_verified:
                    flash('Please verify your email address before logging in. Check your inbox for the verification link.', 'warning')
                    return render_template('login.html', show_resend_link=True, user_email=user_dict['email'])

                # Password matches and email is verified (or not required)
                user_obj = User(
                    id=user_dict['id'],
                    username=user_dict['username'],
                    email=user_dict['email'],
                    is_active=user_dict.get('is_active', 0) == 1,
                    is_admin=user_dict.get('is_admin', 0) == 1,
                    email_verified=email_verified
                )
                login_user(user_obj)
                flash(f"Welcome, {user_obj.username}!", 'success')

                # Check for unread notifications and display them
                conn = get_db_connection()
                try:
                    unread_notifications = conn.execute("""
                        SELECT message, created_at FROM notifications
                        WHERE user_id = ? AND is_read = 0
                        ORDER BY created_at DESC
                        LIMIT 5
                    """, (user_obj.id,)).fetchall()

                    # Flash each notification
                    for notif in unread_notifications:
                        flash(notif['message'], 'info')

                    # Mark all as read
                    if unread_notifications:
                        conn.execute("""
                            UPDATE notifications
                            SET is_read = 1
                            WHERE user_id = ? AND is_read = 0
                        """, (user_obj.id,))
                        conn.commit()
                finally:
                    conn.close()

                return redirect(url_for('base.index'))
        flash('Invalid email or password!', 'danger')
    return render_template('login.html')

@auth_blueprint.route('/logout')
def logout():
    logout_user()
    flash('Logged out successfully!', 'success')
    return redirect(url_for('auth.login'))

@auth_blueprint.route('/verify_email/<token>')
def verify_email(token):
    """Verify email address using the token from the verification email"""
    result = verify_token(token)

    if result:
        flash(f'Email verified successfully! You can now log in.', 'success')
        return redirect(url_for('auth.login'))
    else:
        flash('Invalid or expired verification link. Please request a new verification email.', 'danger')
        return redirect(url_for('auth.resend_verification'))

@auth_blueprint.route('/resend_verification', methods=['GET', 'POST'])
@rate_limit_post("3 per hour")
def resend_verification():
    """Resend verification email"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip()

        if not email:
            flash('Please provide an email address.', 'danger')
            return render_template('resend_verification.html')

        # Get user by email
        conn = get_db_connection()
        try:
            user = conn.execute('SELECT id, username, email, email_verified FROM users WHERE email = ?', (email,)).fetchone()

            if not user:
                # Don't reveal if email exists or not for security
                flash('If an account with that email exists and is not verified, a verification email has been sent.', 'info')
                return render_template('resend_verification.html')

            if user['email_verified']:
                flash('This email address is already verified. You can log in.', 'info')
                return redirect(url_for('auth.login'))

            # Resend verification email
            success = resend_verification_email(user['id'])
            if success:
                flash('Verification email sent! Please check your inbox.', 'success')
            else:
                flash('Could not send verification email. Please try again later or contact support.', 'danger')

        finally:
            conn.close()

        return render_template('resend_verification.html')

    # GET request
    return render_template('resend_verification.html')