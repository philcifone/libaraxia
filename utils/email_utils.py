"""
Email utility functions for sending verification emails and other notifications.
"""

from flask import current_app, url_for
from flask_mail import Message
from itsdangerous import URLSafeTimedSerializer
import secrets
from datetime import datetime, timedelta
from utils.database import get_db_connection


def get_serializer():
    """Get the URL-safe serializer for generating tokens"""
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'])


def generate_verification_token(user_id):
    """
    Generate a secure email verification token for the user.

    Args:
        user_id: The ID of the user to generate the token for

    Returns:
        str: The verification token
    """
    # Generate a secure random token
    token = secrets.token_urlsafe(32)

    # Calculate expiration time (24 hours from now)
    expires_at = (datetime.now() + timedelta(seconds=current_app.config['EMAIL_VERIFICATION_TOKEN_MAX_AGE'])).isoformat()

    # Store token in database
    conn = get_db_connection()
    try:
        conn.execute('''
            INSERT INTO email_verification_tokens (user_id, token, expires_at)
            VALUES (?, ?, ?)
        ''', (user_id, token, expires_at))
        conn.commit()
    finally:
        conn.close()

    return token


def send_verification_email(user_email, username, user_id):
    """
    Send an email verification email to the user.

    Args:
        user_email: The email address to send to
        username: The username of the user
        user_id: The ID of the user

    Returns:
        bool: True if email was sent successfully, False otherwise
    """
    # Check if email is configured
    if not current_app.config.get('MAIL_USERNAME'):
        current_app.logger.warning('Email verification requested but MAIL_USERNAME not configured')
        return False

    try:
        # Generate verification token
        token = generate_verification_token(user_id)

        # Generate verification URL
        verification_url = url_for('auth.verify_email', token=token, _external=True)

        # Create email message
        msg = Message(
            subject='Verify Your Email Address',
            sender=current_app.config['MAIL_DEFAULT_SENDER'],
            recipients=[user_email]
        )

        # Email body (plain text)
        msg.body = f'''
Hello {username},

Thank you for registering! Please verify your email address by clicking the link below:

{verification_url}

This link will expire in 24 hours.

If you did not create this account, please ignore this email.

Best regards,
The Libaraxia Team
        '''

        # Email body (HTML)
        msg.html = f'''
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{
            font-family: Arial, sans-serif;
            line-height: 1.6;
            color: #333;
        }}
        .container {{
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
        }}
        .button {{
            display: inline-block;
            padding: 12px 24px;
            background-color: #007bff;
            color: white;
            text-decoration: none;
            border-radius: 4px;
            margin: 20px 0;
        }}
        .footer {{
            margin-top: 30px;
            font-size: 12px;
            color: #666;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h2>Hello {username},</h2>
        <p>Thank you for registering! Please verify your email address by clicking the button below:</p>
        <a href="{verification_url}" class="button">Verify Email Address</a>
        <p>Or copy and paste this link into your browser:</p>
        <p><a href="{verification_url}">{verification_url}</a></p>
        <p>This link will expire in 24 hours.</p>
        <div class="footer">
            <p>If you did not create this account, please ignore this email.</p>
        </div>
    </div>
</body>
</html>
        '''

        # Send the email
        mail = current_app.mail
        mail.send(msg)

        # Update the user record with the timestamp of when verification was sent
        conn = get_db_connection()
        try:
            conn.execute('''
                UPDATE users
                SET email_verification_sent_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (user_id,))
            conn.commit()
        finally:
            conn.close()

        return True

    except Exception as e:
        current_app.logger.error(f'Error sending verification email: {str(e)}')
        return False


def verify_token(token):
    """
    Verify an email verification token.

    Args:
        token: The verification token to check

    Returns:
        dict: User data if token is valid, None otherwise
    """
    conn = get_db_connection()
    try:
        # Get the token from database
        token_data = conn.execute('''
            SELECT vt.*, u.id as user_id, u.username, u.email
            FROM email_verification_tokens vt
            JOIN users u ON vt.user_id = u.id
            WHERE vt.token = ? AND vt.used = 0
        ''', (token,)).fetchone()

        if not token_data:
            return None

        # Check if token has expired
        expires_at = datetime.fromisoformat(token_data['expires_at'])
        if datetime.now() > expires_at:
            return None

        # Mark token as used
        conn.execute('''
            UPDATE email_verification_tokens
            SET used = 1
            WHERE id = ?
        ''', (token_data['id'],))

        # Mark user's email as verified
        conn.execute('''
            UPDATE users
            SET email_verified = 1
            WHERE id = ?
        ''', (token_data['user_id'],))

        conn.commit()

        return dict(token_data)

    except Exception as e:
        current_app.logger.error(f'Error verifying token: {str(e)}')
        return None
    finally:
        conn.close()


def resend_verification_email(user_id):
    """
    Resend verification email to a user.

    Args:
        user_id: The ID of the user

    Returns:
        bool: True if email was sent successfully, False otherwise
    """
    conn = get_db_connection()
    try:
        user = conn.execute('''
            SELECT id, username, email, email_verified
            FROM users
            WHERE id = ?
        ''', (user_id,)).fetchone()

        if not user:
            return False

        if user['email_verified']:
            return False  # Already verified

        # Invalidate old tokens
        conn.execute('''
            UPDATE email_verification_tokens
            SET used = 1
            WHERE user_id = ? AND used = 0
        ''', (user_id,))
        conn.commit()

        # Send new verification email
        return send_verification_email(user['email'], user['username'], user['id'])

    finally:
        conn.close()
