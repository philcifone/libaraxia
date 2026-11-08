from flask import Flask, redirect, url_for
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_login import LoginManager, current_user as _current_user
from flask_wtf.csrf import CSRFProtect
from flask_mail import Mail
import os, logging
from dotenv import load_dotenv

# Load .env before anything below reads the environment (config.py reads it at
# import time). Real environment variables (e.g. from systemd) still win.
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

# Custom imports
from utils.database import get_db, database_path, close_db
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
from blueprints.friends import friends_blueprint
from blueprints.covers import covers_blueprint
from blueprints.videos import videos_blueprint
from blueprints.records import records_blueprint
from config import DevelopmentConfig, ProductionConfig
from models import User, DEFAULT_THEME_STYLE, DEFAULT_THEME_MODE, THEME_STYLES, THEME_MODES
from utils.rate_limiting import limiter

def create_app():
    # Create the Flask app instance
    app = Flask(__name__)

    env = os.getenv('FLASK_ENV', 'development')

    # Load environment-specific configuration
    if env == 'production':
        app.config.from_object(ProductionConfig)
    else:
        app.config.from_object(DevelopmentConfig)

    # Get SECRET_KEY - REQUIRE it in production
    secret_key = os.environ.get('SECRET_KEY')

    if env == 'production' and not secret_key:
        raise RuntimeError("SECRET_KEY must be set in production! Add it to your .env file.")

    if not secret_key:
        print("WARNING: No SECRET_KEY set, using fallback (dev only)")
        secret_key = 'fallback-secret-key'
    elif 'CHANGE-ME' in secret_key:
        print("WARNING: SECRET_KEY is still the placeholder from .env.example - generate a real one!")

    app.config['SECRET_KEY'] = secret_key

    # Open self-registration (the very first account can always register)
    app.config['ALLOW_REGISTRATION'] = os.getenv('ALLOW_REGISTRATION', 'True').lower() == 'true'

    # Behind a reverse proxy (nginx etc.), trust X-Forwarded-* from this many proxies
    # so rate limiting and logs see the real client IP instead of the proxy's
    trusted_proxies = int(os.getenv('TRUSTED_PROXY_COUNT', '0') or 0)
    if trusted_proxies > 0:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=trusted_proxies, x_proto=trusted_proxies,
                                x_host=trusted_proxies, x_prefix=trusted_proxies)

    # Initialize CSRF Protection
    CSRFProtect(app)

    # Configure CSRF to accept tokens from headers (for AJAX requests)
    app.config['WTF_CSRF_CHECK_DEFAULT'] = True
    app.config['WTF_CSRF_HEADERS'] = ['X-CSRFToken', 'X-CSRF-Token']

    # Content-Security-Policy: scripts only from our own files (no inline
    # <script> or onclick=; page scripts are in static/ and markup uses the
    # data-click/data-change hooks from static/common.js). Inline style=""
    # attributes are still allowed: there are a handful, and injected CSS is
    # far less dangerous than injected script. Images are ours too: remote
    # search-result covers go through /books/thumbnail. data: is for upload
    # previews. No worker-src blob: the barcode scanner (static/scanner.js)
    # decodes on the main thread, so it starts no workers.
    # CSP_REPORT_ONLY=true sends it as Report-Only (logged in the browser
    # console, not enforced), an escape hatch if something turns out blocked.
    csp = '; '.join([
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: blob:",
        "font-src 'self'",
        "connect-src 'self'",
        "worker-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'self'",
    ])
    csp_header = ('Content-Security-Policy-Report-Only'
                  if os.getenv('CSP_REPORT_ONLY', '').lower() in ('1', 'true', 'yes')
                  else 'Content-Security-Policy')

    @app.after_request
    def set_security_headers(response):
        response.headers.setdefault(csp_header, csp)
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
        response.headers.setdefault('Referrer-Policy', 'same-origin')
        return response

    # Initialize Rate Limiter (shared instance from utils/rate_limiting.py)
    limiter.init_app(app)

    # Initialize Flask-Mail
    mail = Mail(app)
    app.mail = mail

    # Initialize Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)

    # Define the login view to redirect unauthenticated users
    login_manager.login_view = 'auth.login'  # 'auth.login' is the login route name

    @login_manager.user_loader
    def load_user(user_id):
        logging.debug(f"Loading user with ID: {user_id}")
        conn = get_db()
        logging.debug("Database connections successful")
        user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        if user and not user['is_active']:
            # Deactivated: end any existing session / remember-me login too
            return None
        if user:
            user_dict = dict(user)
            return User(
                id=user_dict['id'],
                username=user_dict['username'],
                email=user_dict['email'],
                is_active=user_dict.get('is_active', 0) == 1,
                is_admin=user_dict.get('is_admin', 0) == 1,
                avatar_url=user_dict.get('avatar_url'),
                email_verified=user_dict.get('email_verified', 1) == 1,
                bio=user_dict.get('bio'),
                theme_style=user_dict.get('theme_style'),
                theme_mode=user_dict.get('color_mode'),
            )
        return None

    # FOR HOME PAGE LANDING & REDIRECTS
    @app.route("/")
    def root():
        # Check if any users exist in the database
        conn = get_db()
        user_count = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        
        # If no users exist, redirect to registration page for first-time setup
        if user_count == 0:
            return redirect(url_for("auth.register"))
        
        # Otherwise, proceed to normal home page
        return redirect(url_for("base.home"))

    # Image upload configuration
    UPLOAD_FOLDER = os.path.join('static', 'uploads')
    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

    # Close the per-request connection from utils.database.get_db()
    app.teardown_appcontext(close_db)

    # Say which database this process opens (the "which library.db?" trap).
    db_path = database_path()
    if os.path.exists(db_path):
        app.logger.info("Database: %s", db_path)
    else:
        app.logger.warning("Database %s does not exist yet; run `python3 manage.py migrate`", db_path)
    
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
    app.register_blueprint(friends_blueprint, url_prefix='/friends')
    app.register_blueprint(covers_blueprint, url_prefix='/covers')
    app.register_blueprint(videos_blueprint, url_prefix='/videos')
    app.register_blueprint(records_blueprint, url_prefix='/records')

    # "VHS" is shown as "Cartridge" (utils/media.py)
    from utils import media
    app.add_template_filter(media.format_label, 'format_label')

    # Pages that list several media types (feed, wishlist, collections) word
    # and link each row by its own type: labels_for(row).by, item_url(row).
    def item_url(row, action='show'):
        return url_for(media.item_endpoint(media.media_type_of(row), action), id=row['id'])
    app.add_template_global(item_url, 'item_url')
    app.add_template_global(lambda row: media.media_labels(media.media_type_of(row)), 'labels_for')

    # Register Error Handlers
    app.register_error_handler(401, unauthorized)

    # Appearance: every template puts these on <html data-style data-mode>
    @app.context_processor
    def inject_theme():
        user = _current_user
        signed_in = getattr(user, 'is_authenticated', False)
        return {
            'theme_style': user.theme_style if signed_in else DEFAULT_THEME_STYLE,
            'theme_mode': user.theme_mode if signed_in else DEFAULT_THEME_MODE,
            'theme_styles': THEME_STYLES,
            'theme_modes': THEME_MODES,
        }

    @app.context_processor
    def inject_cover_job():
        # The cover-fetch progress panel in _sidebar.html renders only when
        # the user has a job to show, so nobody else pays for polling.
        user = _current_user
        if not getattr(user, 'is_authenticated', False):
            return {'cover_job': None}
        from utils import cover_jobs
        return {'cover_job': cover_jobs.as_dict(cover_jobs.current_job(get_db(), user.id))}
    
    # Configure Logging
    logging.basicConfig(level=logging.DEBUG if app.config.get('DEBUG') else logging.INFO)
    
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

    # Get port from environment variable or default to 5000
    port = int(os.environ.get('PORT', 5000))

    if use_ssl:
        app.run(host="0.0.0.0", port=port, debug=app.config['DEBUG'], ssl_context=ssl_context)
    else:
        print("⚠️  Running without HTTPS - camera features may not work on mobile")
        print("   To enable HTTPS, generate certificates and run:")
        print("   python3 app.py --cert certs/cert.pem --key certs/key.pem")
        app.run(host="0.0.0.0", port=port, debug=app.config['DEBUG'])