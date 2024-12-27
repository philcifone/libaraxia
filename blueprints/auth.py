from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
import bcrypt
import sqlite3
from utils.database import get_db_connection  # Replace with your actual import for the `get_db_connection` function
from models import admin_required, User  # Replace with your actual import for `admin_required`

auth_blueprint = Blueprint('auth', __name__, template_folder='templates')

@auth_blueprint.route('/register', methods=['GET', 'POST'])
@admin_required
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']  # Capture password from the form

        # Ensure password is hashed using bcrypt
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                'INSERT INTO users (username, email, password) VALUES (?, ?, ?)',
                (username, email, hashed_password.decode('utf-8'))  # Decode hashed password for storage
            )
            conn.commit()
            flash('Registration successful!', 'success')
            return redirect(url_for('auth.login'))
        except sqlite3.IntegrityError:
            flash('Email or username already registered!', 'danger')
        finally:
            conn.close()
    return render_template('register.html')

@auth_blueprint.route('/login', methods=['GET', 'POST'])
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
                # Password matches
                user_obj = User(
                    id=user_dict['id'],
                    username=user_dict['username'],
                    email=user_dict['email'],
                    is_active=user_dict.get('is_active', 0) == 1,
                    is_admin=user_dict.get('is_admin', 0) == 1
                )
                login_user(user_obj)
                flash(f"Welcome, {user_obj.username}!", 'success')
                return redirect(url_for('base.index'))
        flash('Invalid email or password!', 'danger')
    return render_template('login.html')

@auth_blueprint.route('/logout')
def logout():
    logout_user()
    flash('Logged out successfully!', 'success')
    return redirect(url_for('auth.login'))