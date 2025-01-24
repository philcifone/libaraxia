from flask import Flask, redirect, url_for
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
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
from config import DevelopmentConfig, ProductionConfig
from models import User

def create_app():
    # Create the Flask app instance
    app = Flask(__name__)
    
    # App Configuration
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'fallback-secret-key')
    env = os.getenv('FLASK_ENV', 'development')

    # Load environment variables
    load_dotenv()

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
                is_admin=user_dict.get('is_admin', 0) == 1
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
    
    # Register Error Handlers
    app.register_error_handler(401, unauthorized)
    
    # Configure Logging
    logging.basicConfig(level=logging.DEBUG)
    
    return app

if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5000, debug=True)