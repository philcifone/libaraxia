from flask import Blueprint, render_template, redirect, url_for
from flask_login import current_user, login_required
from utils.database import get_db_connection
from models import User

# Initialize Blueprint
user_blueprint = Blueprint('user', __name__)

@user_blueprint.route('/<username>')
@login_required
def profile(username):
    # Ensure the current user is authenticated
    if not current_user.is_authenticated:
        return redirect(url_for('auth.login'))

    # Fetch the user details from the database
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    conn.close()

    if not user:
        return "User not found!", 404

    # Convert user data to dictionary format for easier use
    user = dict(user)

    return render_template('user.html', user=user)
