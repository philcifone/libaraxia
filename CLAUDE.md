# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Libaraxia is a Flask-based personal library management web application that allows users to catalog books, track reading progress, and share collections with friends and household members. The application uses SQLite for data storage and integrates with the Google Books API for book metadata.

## Development Commands

### Environment Setup
```bash
# Install Python dependencies
pip install -r requirements.txt

# Install Node dependencies (for Tailwind CSS)
npm install

# Create environment file from example
cp .env.example .env
# Then edit .env to add SECRET_KEY and GOOGLE_BOOKS_API_KEY
```

### Database Management
```bash
# Initialize database from schema
sqlite3 library.db < create_database.sql

# Run migrations (check migrations/README.md for current list)
sqlite3 library.db < migrations/001_add_added_by_column.sql
# ... continue with other migrations in order

# Access database directly
sqlite3 library.db
```

### Running the Application
```bash
# Development server (HTTP)
python3 app.py

# Development server with HTTPS (required for camera/barcode features)
python3 app.py --cert certs/cert.pem --key certs/key.pem

# Generate SSL certificates for local HTTPS
./generate-cert.sh

# Production server (using gunicorn)
gunicorn -w 4 -b 0.0.0.0:5000 'app:create_app()'
```

### Docker
```bash
# Build and run with Docker
docker compose build --no-cache
docker compose up -d

# Find container IP (for headless access)
docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' libaraxia-web-1
```

### Frontend Development
```bash
# Tailwind CSS is configured via tailwind.config.js
# Watch for CSS changes during development
npx tailwindcss -i ./static/css/input.css -o ./static/css/output.css --watch
```

## Architecture Overview

### Application Structure
- **app.py**: Flask application factory pattern with blueprint registration, Flask-Login, CSRF protection, rate limiting
- **config.py**: Environment-specific configuration (Development, Production, Testing)
- **models.py**: User model and permission helpers (admin_required, friendship checks, privacy controls)

### Blueprints (Feature Modules)
All blueprints are in `/blueprints/` and registered with URL prefixes:
- **auth**: User authentication (login, register, logout, email verification)
- **base**: Home page, main library view with search/sort/filter
- **books**: CRUD operations for books, ISBN/title lookup, cover image management
- **collections**: Reading status management (read, currently reading, want to read, DNF)
- **user**: User profiles, settings, reading statistics, password/email updates
- **read**: Reading sessions tracking (date started/completed)
- **tags**: User-specific book tagging system
- **admin**: Admin-only features (user management, Goodreads import, system settings)
- **feed**: Activity feed showing recent reviews, updates from friends
- **wishlist**: Wishlist management with notes and purchase links
- **friends**: Friend requests, friend management, viewing friends' libraries

### Utilities
Located in `/utils/`:
- **database.py**: SQLite connection helper with Row factory for dict-like access
- **book_utils.py**: Google Books API integration, ISBN lookup, cover image fetching/processing
- **image_utils.py**: Image upload, resizing, optimization (PIL-based)
- **email_utils.py**: Email verification token generation and sending (Flask-Mail)
- **rate_limiting.py**: Rate limit decorators for sensitive endpoints
- **errors.py**: Custom error handlers

### Database Schema
Core tables (see `create_database.sql` for full schema):
- **books**: Shared book catalog (title, author, ISBN, cover, description, genre, added_by)
- **users**: User accounts (username, email, password hash, is_admin, avatar_url, bio)
- **collections**: User-specific reading status per book (read, currently reading, want to read, DNF)
- **read_data**: User ratings and comments per book
- **reading_sessions**: Track when users started/completed books
- **book_tags**: User-specific tags for books
- **user_collections**: Custom user-created collections
- **wishlist**: Books users want to acquire
- **friendships**: Friend relationships between users
- **friend_requests**: Pending friend requests
- **library_members**: Household library sharing (multiple users in same library)
- **activities**: Activity feed events (reviews, status changes)
- **notifications**: User notifications with read/unread status

### Privacy Model
The application implements a three-tier privacy system:
- **Private**: Only the owner (and library members) can see
- **Friends**: Owner, friends, and library members can see
- **Public**: Everyone can see

Library members (household sharing) can always see each other's content regardless of privacy settings. See `models.py` for `can_view_content()`, `shares_library_with()`, and `is_friends_with()` helper functions.

### Frontend
- **Templates**: Jinja2 templates in `/templates/` with partials (`_sidebar.html`, `_flash_messages.html`, `_search_sort_filter.html`, `_book_grid.html`)
- **Static assets**: `/static/` contains JavaScript, CSS, fonts, and user-uploaded cover images
- **Styling**: Tailwind CSS with custom theme (see `tailwind.config.js` for color palette and fonts)
- **JavaScript**: Vanilla JavaScript for interactive features (add_book.js, edit_book.js, script.js, wishlist.js, notifications.js)

### Key JavaScript Files
- **script.js**: Main library view interactions, filtering, sorting, book grid updates
- **add_book.js**: Book addition form, ISBN lookup, Google Books search results
- **edit_book.js**: Book editing interface
- **wishlist.js**: Wishlist management interface
- **notifications.js**: Real-time notification badge updates
- **sidebar.js**: Mobile-responsive sidebar behavior

## Important Development Notes

### Authentication & Security
- First user registered automatically becomes admin
- Admin-only routes use `@admin_required` decorator from models.py
- CSRF protection enabled globally via Flask-WTF (tokens in headers: X-CSRFToken, X-CSRF-Token)
- Rate limiting configured per-route (check blueprints for `@limiter.limit()` decorators)
- Passwords hashed with bcrypt via Flask-Bcrypt

### Image Handling
- Cover images can be uploaded or auto-fetched from Google Books API
- Images are resized to MAX_IMAGE_SIZE (500x1000) and optimized
- Stored in `/static/uploads/` directory
- Fallback to `no-cover.png` if no cover available

### Google Books API Integration
- Requires GOOGLE_BOOKS_API_KEY in .env
- Used for ISBN lookup and title/author search
- Fetches metadata: title, authors, publisher, page count, description, genre, cover images
- See `utils/book_utils.py` for `search_google_books()` and `fetch_book_details_from_isbn()`

### Database Migrations
- Manual SQL migrations in `/migrations/` directory
- Must be run in numerical order (001, 002, 003, etc.)
- See `migrations/README.md` for migration history and instructions
- Always check database location before running migrations

### Environment Variables
Required in `.env`:
- **SECRET_KEY**: Flask secret key for sessions (MUST change from default)
- **GOOGLE_BOOKS_API_KEY**: Get from https://console.cloud.google.com
- **FLASK_ENV**: development or production
- **DATABASE_URI**: SQLite database path (default: sqlite:///library.db)

Optional (for email verification):
- **EMAIL_VERIFICATION_REQUIRED**: True/False
- **MAIL_SERVER**, **MAIL_PORT**, **MAIL_USERNAME**, **MAIL_PASSWORD**: SMTP configuration

### Common Patterns

#### Adding a New Blueprint Feature
1. Create blueprint file in `/blueprints/`
2. Define blueprint: `my_blueprint = Blueprint('myfeature', __name__, template_folder='templates')`
3. Add routes with decorators: `@my_blueprint.route('/path')`
4. Register in `app.py`: `app.register_blueprint(my_blueprint, url_prefix='/myfeature')`
5. Create corresponding template(s) in `/templates/`

#### Database Queries
Always use the connection pattern:
```python
from utils.database import get_db_connection

conn = get_db_connection()
try:
    result = conn.execute('SELECT * FROM table WHERE id = ?', (id,)).fetchone()
    # ... use result
finally:
    conn.close()
```

#### API Response Pattern
```python
return jsonify({"success": True, "data": data}), 200
return jsonify({"success": False, "error": "Error message"}), 400
```

### Testing Notes
- First-time setup: Access localhost:5000, you'll be redirected to register the first admin user
- Camera/barcode features require HTTPS (use --cert and --key flags)
- Docker container may need to be accessed via localhost:5000 first before external IP works

### Known Issues/Future Features
- Barcode scanner still in development
- Admin & user settings pages incomplete
- Side scroll for books on collections page not implemented
- Separate recent books/reviews feed pending
