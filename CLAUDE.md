# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Open work, known bugs and security follow-ups live in [ROADMAP.md](ROADMAP.md)**, as numbered phases worked through in order. Check it before starting a task and tick items off when they're done. Phases 0–8 are core Libaraxia work (Phase 0, the Gruvbox/house-style design refresh, comes first). The archive fork is parked; its plan and the original VHS design notes are in [FORK-SPEC.md](FORK-SPEC.md).

## Project Overview

Libaraxia is a Flask-based personal library management web application that allows users to catalog books, track reading progress, and share collections with friends and household members. The application uses SQLite (raw `sqlite3`, no ORM) for data storage and integrates with the Google Books and Open Library APIs for book metadata.

Production runs under **gunicorn directly (no Docker)**. The Docker files are kept for reference.

## Development Commands

### Environment Setup
```bash
pip install -r requirements.txt   # Python deps
npm install                       # Tailwind (dev only)
cp .env.example .env              # then set SECRET_KEY and GOOGLE_BOOKS_API_KEY
```

### Database Management
Use `manage.py` (see `migrations/README.md`):
```bash
python3 manage.py migrate             # new DB: built from create_database.sql; existing: backup + pending migrations
python3 manage.py status              # applied / pending
python3 manage.py --db /tmp/x.db migrate   # any other file
```
`create_database.sql` is the complete schema for a **new** database (every migration so far folded in, plus the `schema_migrations` ledger). A database created before the runner needs `manage.py migrate --baseline` once; plain `migrate` refuses a DB with tables but no ledger. Migration files must not contain BEGIN/COMMIT; each runs in its own transaction with FKs off and is rolled back if it adds `foreign_key_check` violations. Always check which DB file you're touching.

### Running the Application
```bash
python3 app.py                                              # dev server, debug follows FLASK_ENV
python3 app.py --cert certs/cert.pem --key certs/key.pem    # HTTPS (camera/barcode on mobile)
./generate-cert.sh                                          # self-signed certs for the above
gunicorn -w 4 -b 0.0.0.0:5000 'app:create_app()'            # production
```

### Frontend (Tailwind)
The Tailwind **input** file is `static/styles.css` (not `static/css/input.css`). The built `static/css/output.css` is committed, so rebuild it after adding new utility classes:
```bash
npm run build:css    # one-off build
npm run watch:css    # rebuild on change
```

## Architecture Overview

### Application Structure
- **app.py**: application factory `create_app()`. Loads `.env`, picks the config, sets up CSRF, Flask-Limiter, Flask-Mail and Flask-Login, adds security headers, optional ProxyFix, and registers the blueprints. `/` redirects to registration when there are no users, otherwise to `/base/`.
- **config.py**: `DevelopmentConfig` / `ProductionConfig` / `TestingConfig`, chosen by `FLASK_ENV` (cookies, mail, email verification).
- **manage.py**: database CLI: `migrate`, `status`, `backup` (see Database Management).
- **models.py**: `User` (Flask-Login), `admin_required`, username rules (`is_valid_username`), and friendship/library helpers (`is_friends_with`, `get_friendship_status`, `get_library_members`, `shares_library_with`, `can_view_content`).

### Blueprints (`/blueprints/`, URL prefix in brackets)
- **auth** (`/auth`): register, login (with remember-me), logout, email verification and resend. Registration can be closed with `ALLOW_REGISTRATION=False`.
- **base** (`/base`): main library view at `/base/index` with search/sort/filter and infinite scroll; shared (household) library; friends' libraries.
- **books** (`/books`): add, edit, remove from library / restore (deaccession), delete for mistakes (POST), detail page, ISBN/title lookup, cover fetching, ownership transfer within a household.
- **collections** (`/collections`): reading status (read, currently reading, want to read, did not finish) and custom user collections.
- **user** (`/user`): profiles, stats, inline settings (email/username/bio/password/avatar), library CSV export and "export my data" ZIP, Profile → Account (deactivate/delete own account), **Goodreads CSV import** (available to every user, not admin-only), adding/removing household members.
- **read** (`/read`): ratings/reviews and reading sessions (dates started/completed).
- **tags** (`/tags`): per-user tags.
- **admin** (`/admin`): user management (deactivate/delete dialog), avatar management, orphaned image cleanup, unowned books (reassign), bulk cover fetch, household (library) membership.
- **feed** (`/feed`): activity feed of friends' reviews/updates, likes, dismissals.
- **wishlist** (`/wishlist`): wishlist with notes, moving items into the library, viewing friends' wishlists.
- **friends** (`/friends`): friend requests, friend list, notifications page, user search API.

### Utilities (`/utils/`)
- **database.py**: `get_db()` (request-scoped connection, closed at teardown), `get_db_connection()` (a new connection: `sqlite3.Row`, `PRAGMA foreign_keys = ON`), `database_path()`.
- **book_utils.py**: Google Books / Open Library / bookcover API lookups, ISBN helpers, cover search and download (`download_and_save_cover`, with an SSRF guard that only fetches public hosts), `process_image` for uploads, `get_filter_options`.
- **image_utils.py**: `is_safe_upload_path`, `delete_image_file` (refuses paths outside `static/uploads/`), and orphaned image detection/cleanup.
- **email_utils.py**: verification tokens (random, stored in `email_verification_tokens`) and sending via Flask-Mail.
- **rate_limiting.py**: shared `limiter` instance.
- **errors.py**: 401 handler that redirects to login.

### Database Schema
Tables after all migrations:
- **Books and reading:** `books` (shared catalog, `added_by` = owner), `collections` (per-user reading status), `read_data` (rating/comment), `reading_sessions`, `book_tags`, `user_collections` + `collection_books` (custom collections), `wishlist`.
- **Users and social:** `users` (incl. `is_admin`, `is_active`, `avatar_url`, `bio`, `reading_goal`, `email_verified`, `default_privacy`), `friendships` (stored with `user_id_1 < user_id_2`), `friend_requests`, `notifications`, `activity_likes`, `dismissed_activities`, `email_verification_tokens`.
- **Households:** `library_members` (one library per user; `library_id` groups members).

There is no `activities` table; the feed is built from `read_data`/`collections`/`wishlist` at query time. Some rows are positional (`book[0]`, `book[1]`) in templates, so be careful reordering `SELECT *` columns.

Gotchas:
- **Foreign keys are enforced** (`get_db_connection()` runs `PRAGMA foreign_keys = ON`; needs migrations 014/015). Every FK has a deliberate `ON DELETE` rule: user and book children `CASCADE`, but `books.added_by` is `SET NULL`, so deleting a user never deletes books. A book is a record other people's reviews hang on: hard delete is refused while another user has data on it (`models.other_users_with_book_data`). Don't delete `books` rows anywhere else without that check.
- **Unowned books** (`added_by IS NULL`) are allowed but appear in no library view, since those filter by owner. Handle `None` wherever `added_by` is used.
- **Removed (deaccessioned) books** have `books.removed_at` set. Library views must add `AND b.removed_at IS NULL` unless `show_removed` is asked for; reading history, reviews and exports keep them. "Remove from library" is the normal way a book leaves; hard delete is only for mistakes.
- **Accounts:** deactivate/delete logic lives in `utils/accounts.py` (shared by admin and self-delete). Exports are in `utils/export.py`, scoped to one user.
- **Wishlist entries are rows in `books`** (plus a `wishlist` row). Library queries must exclude them with `AND NOT EXISTS (SELECT 1 FROM wishlist w WHERE w.book_id = b.id ...)`, or they'll count wishlist books as owned.

### Access Model (what the code actually does)
- **Friends-gated:** profiles, stats, wishlists, reviews and friends' libraries are shown only to the owner and their friends (`get_friendship_status` in `user.py`, `wishlist.py`, `base.py`).
- **Household members** (`library_members`) see each other's books in the shared library view.
- **Privacy columns are not enforced.** Migration 012 added `privacy` columns (`collections`, `wishlist`, `reading_sessions`, `user_collections`) and `users.default_privacy`, and `models.can_view_content()` implements a private/friends/public check, but nothing calls it yet. Treat the three-tier privacy model as planned, not live (see ROADMAP.md Phase 4).
- **Book detail** (`/books/book/<id>`) has no access check; any logged-in user can open any book by id.
- Only the owner or an admin can edit, delete or transfer a book.

### Frontend
- **No base layout.** Each page template is standalone and `{% include %}`s `_sidebar.html`, `_flash_messages.html`, and where relevant `_search_sort_filter.html`, `_book_grid.html` and `_add_book_fab.html`.
- **Themes:** two per-user settings on `<html data-style=… data-mode=…>` (injected by a context processor in `app.py`, edited at Profile → Appearance, stored in `users.theme_style` / `users.color_mode`). Style `house` = Gruvbox, Courier Prime, square, strong borders; `classic` = the original look (Outfit, rounded, soft shadows). Mode `system|light|dark`. Every colour, radius, shadow and the body font are CSS variables in `static/styles.css`; `tailwind.config.js` maps Tailwind names onto them. Use the semantic classes (`bg-secondary`, `text-content-primary`, `bg-accent text-on-accent`, `border-card` for card outlines, `rounded-pill` for badges) rather than raw colours. Fonts are served from `static/fonts/`.
- **Vanilla JS in `/static/`:**
  - `script.js`: library grid, filters, infinite scroll, status updates; defines `escapeHtml()` and `getCSRFToken()`.
  - `add_book.js`: add form, ISBN/title search, barcode scanning via Quagga from cdnjs.
  - `edit_book.js`: edit form, cover fetching.
  - `wishlist.js`: wishlist add/search/barcode.
  - `tags.js`: tag add/remove.
  - `sidebar.js`: legacy sidebar toggle, only loaded by `notifications.html`.
- Large inline `<script>` blocks also live in `user.html`, `admin_settings.html`, `rate_review.html`, `goodreads_import.html` and `book_detail.html`.

## Important Development Notes

### Authentication & Security
- The first registered user becomes admin. Admin routes use `@admin_required` from models.py.
- Passwords are hashed with the raw `bcrypt` module (not Flask-Bcrypt).
- Usernames must match `^[A-Za-z0-9_.-]{3,30}$` (`models.is_valid_username`); this is enforced on register, rename and admin create.
- CSRF: Flask-WTF `CSRFProtect` is global. Forms include `csrf_token()`; fetch calls send the `X-CSRFToken` header (both `X-CSRFToken` and `X-CSRF-Token` are accepted) using the per-file `getCSRFToken()` helper, which reads a hidden `csrf_token` input or a `<meta name="csrf-token">`.
- Session and remember-me cookies are HttpOnly and SameSite=Lax. They are `Secure` only in production; remember-me lasts 30 days.
- `after_request` sets `X-Content-Type-Options`, `X-Frame-Options: SAMEORIGIN` and `Referrer-Policy`. There is no CSP yet.
- Rate limiting:
  - Flask-Limiter applies a **global default of 200/day and 50/hour per IP** on every route (`utils/rate_limiting.py`), plus per-route `@limiter.limit()` on auth, profile updates, friend requests and imports.
  - Storage is in memory, so each gunicorn worker counts separately.
  - Behind a reverse proxy, set `TRUSTED_PROXY_COUNT` so limits use the real client IP.

### Security conventions (follow these in new code)
- **Image paths from the browser** (hidden form fields such as `existing_cover_url` and `fetched_cover_url`) must pass `is_safe_upload_path()` before being stored. Never call `os.remove` on a DB path without going through `delete_image_file()`.
- **Server-side fetches of URLs** must go through `book_utils._get_public()` / `_fetch_image()` (public-IP check on every redirect).
- **Never put data into `innerHTML`/template literals unescaped.** Use `escapeHtml()` (or `textContent`), and `encodeURIComponent` for URL path segments.
- **Jinja values inside JS** must use `|tojson`. In inline handlers, use a single-quoted attribute: `onclick='return confirm({{ msg|tojson }})'`.
- **State-changing routes are POST-only** with CSRF. Check ownership in the SQL (`WHERE ... AND user_id = ?`) for anything addressed by id.
- Don't return `str(e)` to clients in new code; log it and return a generic message.

### Image Handling
- Covers are uploaded or auto-fetched, resized to MAX_IMAGE_SIZE (500x1000), and stored under `static/uploads/` as `uploads/...` paths relative to `static/`. Avatars go in `static/uploads/avatars/`.
- Fallback image: `static/no-cover.png`.
- `app.py` sets `UPLOAD_FOLDER = static/uploads` (relative to the working dir), overriding the paths in config.py.

### Database Migrations
- SQL files in `/migrations/` (`NNN_name.sql`), applied in order by `manage.py migrate`, tracked in `schema_migrations`. See `migrations/README.md`.
- When adding a migration, either fold it into `create_database.sql` (and add its name to the ledger INSERT there) or leave it for `migrate` to apply after the schema.

### Environment Variables
Read via python-dotenv from `.env`:
- **SECRET_KEY**: required in production. A warning is logged if it's still the `.env.example` placeholder.
- **GOOGLE_BOOKS_API_KEY**: Google Books lookups.
- **FLASK_ENV**: `development` or `production`.
- **DATABASE_PATH**: SQLite file used by `utils/database.py` and `manage.py` (default `library.db` in the project directory).
- **ALLOW_REGISTRATION**: `False` closes self-registration once the first user exists (default `True`).
- **TRUSTED_PROXY_COUNT**: number of reverse proxies to trust for `X-Forwarded-*` (default 0 = off).
- **EMAIL_VERIFICATION_REQUIRED** and **MAIL_SERVER / MAIL_PORT / MAIL_USE_TLS / MAIL_USERNAME / MAIL_PASSWORD / MAIL_DEFAULT_SENDER**: email verification.
- **PORT**: dev server port.

**Load order:** `app.py` calls `load_dotenv()` at import, before `config.py` is imported, and `utils/database.database_path()` reads `DATABASE_PATH` on every call. So every setting works from `.env` or the real environment (real env wins). A relative `DATABASE_PATH` is relative to the project directory, not the cwd. The app logs the DB path at startup and warns if the file doesn't exist.

### Common Patterns

#### Adding a New Blueprint Feature
1. Create `blueprints/myfeature.py` with `my_blueprint = Blueprint('myfeature', __name__, template_folder='templates')`.
2. Add routes with `@my_blueprint.route(...)`, plus `@login_required` (and `@admin_required` / `@limiter.limit` as needed).
3. Register it in `app.py`: `app.register_blueprint(my_blueprint, url_prefix='/myfeature')`.
4. Add templates in `/templates/` (copy the head/sidebar/flash includes from an existing page).

#### Database Queries
In routes (and helpers called from routes), use the request-scoped connection. It is opened on first use and closed at teardown (`app.teardown_appcontext(close_db)`), and anything not committed is rolled back:
```python
from utils.database import get_db

conn = get_db()
row = conn.execute('SELECT * FROM table WHERE id = ?', (id,)).fetchone()
conn.execute('UPDATE ...', (...))
conn.commit()          # explicit; roll back in an except that swallows a failed write
```
Outside a request (manage.py, scripts) use `get_db_connection()` in try/finally and close it. Many older routes still open their own connection that way; that's correct, just verbose, and can move to `get_db()` once there are tests (ROADMAP 2.8). Never use `with get_db_connection() as conn:` (it commits but doesn't close).

#### API Response Pattern
```python
return jsonify({"success": True, "data": data}), 200
return jsonify({"success": False, "error": "Error message"}), 400
```

### Testing Notes
- There is no automated test suite. CI (`.github/workflows/basic-tests.yml`) only syntax-checks and imports modules.
- For manual checks, use a copy of the DB: `DATABASE_PATH=/tmp/test.db python3 app.py`, or Flask's `app.test_client()` with `WTF_CSRF_ENABLED=False`.
- First-time setup: visit `/` and you'll be redirected to register the admin user.
- Camera/barcode scanning needs HTTPS (`--cert`/`--key`, see `docs/HTTPS-SETUP.md`).

### Repo Layout Notes
- `docs/`: HTTPS setup, flash message notes. `docs/archive/`: old AI-generated implementation summaries and one-off scripts, kept for history and possibly stale.
- `node_modules/`, `venv/`, `.env`, `*.db` and `static/uploads/` are git-ignored.
