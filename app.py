from flask import Flask, redirect, url_for
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from flask_wtf.csrf import CSRFProtect
import os, logging, bcrypt
from dotenv import load_dotenv

# Custom imports
from utils.database import get_db_connection
from utils.errors import unauthorized
from blueprints.auth import auth_blueprint
from blueprints.base import base_blueprint
from blueprints.books import books_blueprint
from blueprints.collections import collections_blueprint
from blueprints.user import user_blueprint
from blueprints.read import read_blueprint
from blueprints.tags import tags_blueprint
from blueprints.admin import admin_blueprint
from blueprints.feed import feed_blueprint
from blueprints.wishlist import wishlist_blueprint
from config import DevelopmentConfig, ProductionConfig
from models import User

def create_app():
    # Create the Flask app instance
    app = Flask(__name__)

    # Load environment variables first
    load_dotenv()

    # App Configuration
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'fallback-secret-key')
    env = os.getenv('FLASK_ENV', 'development')

    # Initialize CSRF Protection
    csrf = CSRFProtect(app)

    # Configure CSRF to accept tokens from headers (for AJAX requests)
    app.config['WTF_CSRF_CHECK_DEFAULT'] = True
    app.config['WTF_CSRF_HEADERS'] = ['X-CSRFToken', 'X-CSRF-Token']

    @app.after_request
    def set_csrf_cookie(response):
        """Make CSRF token available for JavaScript"""
        return response

    # Initialize Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    
    # Define the login view to redirect unauthenticated users
    login_manager.login_view = 'auth.login'  # 'auth.login' is the login route name

    @login_manager.user_loader
    def load_user(user_id):
        logging.debug(f"Loading user with ID: {user_id}")
        conn = get_db_connection()
        logging.debug("Database connections successful")
        user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        conn.close()
        if user:
            user_dict = dict(user)
            return User(
                id=user_dict['id'],
                username=user_dict['username'],
                email=user_dict['email'],
                is_active=user_dict.get('is_active', 0) == 1,
                is_admin=user_dict.get('is_admin', 0) == 1,
                avatar_url=user_dict.get('avatar_url')
            )
        return None

    env = os.getenv('FLASK_ENV', 'development')
    if env == 'production':
        app.config.from_object(ProductionConfig)
    else:
        app.config.from_object(DevelopmentConfig)

    # FOR HOME PAGE LANDING & REDIRECTS
    @app.route("/")
    def root():
        # Check if any users exist in the database
        conn = get_db_connection()
        user_count = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        conn.close()
        
        # If no users exist, redirect to registration page for first-time setup
        if user_count == 0:
            return redirect(url_for("auth.register"))
        
        # Otherwise, proceed to normal home page
        return redirect(url_for("base.home"))

    # Image upload configuration
    UPLOAD_FOLDER = os.path.join('static', 'uploads')
    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
    
    # Register Blueprints
    app.register_blueprint(auth_blueprint, url_prefix='/auth')
    app.register_blueprint(base_blueprint, url_prefix='/base')
    app.register_blueprint(books_blueprint, url_prefix='/books')
    app.register_blueprint(collections_blueprint, url_prefix='/collections')
    app.register_blueprint(user_blueprint, url_prefix='/user')
    app.register_blueprint(read_blueprint, url_prefix='/read')
    app.register_blueprint(tags_blueprint, url_prefix='/tags')
    app.register_blueprint(admin_blueprint, url_prefix='/admin')
    app.register_blueprint(feed_blueprint, url_prefix='/feed')
    app.register_blueprint(wishlist_blueprint, url_prefix='/wishlist')
    
    # Register Error Handlers
    app.register_error_handler(401, unauthorized)
    
    # Configure Logging
    logging.basicConfig(level=logging.DEBUG)
    
    return app

if __name__ == "__main__":
    import sys
    app = create_app()

    # Check for SSL certificate arguments
    use_ssl = False
    ssl_context = None

    # Simple command-line SSL support
    if '--cert' in sys.argv and '--key' in sys.argv:
        cert_idx = sys.argv.index('--cert')
        key_idx = sys.argv.index('--key')

        if cert_idx + 1 < len(sys.argv) and key_idx + 1 < len(sys.argv):
            cert_file = sys.argv[cert_idx + 1]
            key_file = sys.argv[key_idx + 1]
            ssl_context = (cert_file, key_file)
            use_ssl = True
            print(f"🔒 Running with HTTPS using cert: {cert_file}")

    if use_ssl:
        app.run(host="0.0.0.0", port=5000, debug=True, ssl_context=ssl_context)
    else:
        print("⚠️  Running without HTTPS - camera features may not work on mobile")
        print("   To enable HTTPS, generate certificates and run:")
        print("   python3 app.py --cert certs/cert.pem --key certs/key.pem")
        app.run(host="0.0.0.0", port=5000, debug=True)