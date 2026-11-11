# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Open work, known bugs and security follow-ups live in [ROADMAP.md](ROADMAP.md)**, as numbered phases worked through in order. Check it before starting a task and tick items off when they're done. Finished phases (0–8F, 10, 11–13b) are in [docs/ROADMAP-ARCHIVE.md](docs/ROADMAP-ARCHIVE.md) under their original numbers, which code comments cite ("ROADMAP 7.2b"): grep there, don't read it whole. The archive fork is out of scope (ROADMAP, Not planned); [FORK-SPEC.md](FORK-SPEC.md) keeps its plan and the original VHS design notes.

## Project Overview

Libaraxia is a Flask-based personal library management web application that allows users to catalog books, track reading progress, and share collections with friends and household members. The application uses SQLite (raw `sqlite3`, no ORM) for data storage and integrates with the Google Books and Open Library APIs for book metadata.

Production runs under **gunicorn directly (no Docker)**. The Docker files are kept for reference. Prod deploys itself: a systemd timer runs `deploy/deploy.sh`, which fast-forwards to `main` once its CI run has passed, migrates and restarts (see `deploy/README.md`). So a push to `main` with green CI reaches prod within about 5 minutes.

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
- **models.py**: `User` (Flask-Login), `admin_required`, username rules (`is_valid_username`), and friendship/library helpers (`is_friends_with`, `get_friendship_status`, `get_library_members`, `shares_library_with`, `circle_ids`, `can_view_book`).

### Blueprints (`/blueprints/`, URL prefix in brackets)
- **auth** (`/auth`): register, login (with remember-me), logout, email verification and resend. Registration can be closed with `ALLOW_REGISTRATION=False`.
- **base** (`/base`): main library view at `/base/index` with search/sort/filter and infinite scroll; shared (household) library; friends' libraries.
- **books** (`/books`): add, edit, `/books/thumbnail` (search-result cover proxy), remove from library / restore (deaccession), delete for mistakes (POST), detail page, ISBN/title lookup, cover fetching, ownership transfer within a household.
- **collections** (`/collections`): statuses (per type, `media.STATUSES`) and custom shelves, on Books / Movies / Music tabs (`?type=`, ROADMAP 8C). Custom shelves (`user_collections.media_type`, migration 027) belong to one section; the item page offers its section's shelves. Shelf cards everywhere (Collections, profile shelves and wishlist rows) are `_shelf_rows.html`, fed by `utils/shelves.py`.
- **user** (`/user`): profiles, stats, inline settings (email/username/bio/password/avatar), library CSV export and "export my data" ZIP, Profile → Account (deactivate/delete own account), **Goodreads CSV import** (available to every user, not admin-only; logic in `utils/goodreads.py`), household invite/accept/decline/remove/leave (logic in `utils/households.py`).
- **read** (`/read`): ratings/reviews and reading sessions (dates started/completed).
- **tags** (`/tags`): per-user tags.
- **admin** (`/admin`): user management (deactivate/delete dialog), avatar management, orphaned image cleanup, unowned books (reassign), bulk cover fetch, household (library) membership.
- **feed** (`/feed`): activity feed of friends' reviews/updates, likes, dismissals.
- **wishlist** (`/wishlist`): your wishlist (`/view`: books and movies, with Books / Movies / Both tabs, `?show=`), adding (`/add?type=book|video`: the shared `add_item.html` with a note field), moving items onto the shelf (Library or Movies), friends' wishlists.
- **friends** (`/friends`): friend requests, friend list, notifications page, user search API.
- **videos** (`/videos`) and **records** (`/records`): the Movies and Music sections (Phase 8; Music was "Vinyls" until 2026-11-08: vinyl, CDs and cassettes, one item is an "album", while code, URLs and the DB say "record"), both built by `blueprints/media_section.py` (a `Section` per type, `make_blueprint`; endpoints `videos.show_video`, `records.add_record`, ... via `media.item_endpoint`). Own / household (`/shared`) / friends' grids (`media_grid.html`; search and filters in the row under the tabs, `_search_sort_filter.html`), add (`add_item.html`, shared with Add Book), edit (`media_form.html`), detail (`book_detail.html` worded by `m`). Movies: TMDb title search `/videos/search`, barcode lookup `/videos/lookup`, scanner. Music: title search over vinyl, CD and cassette releases (`?format=` narrows to one), Discogs first when `DISCOGS_TOKEN` is set (`utils/discogs_lookup.py`), else or when busy MusicBrainz (`utils/music_lookup.py`): `/records/search`, `/records/lookup?discogs=`, `?mbid=` or `?barcode=` (barcodes and the scanner since 8B.12); reads `library_records`. For Movies: detail (`book_detail.html` with video wording; `/books/book/<id>` redirects videos here), barcode duplicate check. Reads the `library_videos` view. **The UI calls the section "Movies"** (sidebar, headings, flashes, feed) and shows the VHS format as **"Cartridge"** (`media.format_label`, the `format_label` template filter; a novel reference, Phil's choice). Code, URLs and the DB keep "video" and `format = 'VHS'`; a DVD is a video row with `format = 'DVD'`. Wording per type comes from `media.media_labels()`.
- **reviews** (`/reviews`, ROADMAP 13): the sidebar's Reviews. `/reviews/?type=` has three rows per type (your reviews, friends' reviews, finished not reviewed yet; `_shelf_rows.html` with stars), `/reviews/all/<mine|friends|unreviewed>` the "See all" cards (`?by=<friend>`), `/reviews/find?type=&q=` the floating [+ Review] search (your view rows and your household's, never others'). Writes nothing: every link goes to `read.rate_review` with `?from=reviews` (crumb and save go back to Reviews). "Add it as not owned" opens the type's add page with `?not_owned=1&then=review&title=`, and saving lands on the review page. Queries in `utils/reviews.py`.
- **have** (`/have`): Do I have this? (ROADMAP 8E): scan or type a barcode, ISBN or title; answers own / household / wishlist / not owned / removed / not here with your status and rating. Matching and scope in `utils/have.py`; `static/have.js` reloads the page with `?q=<code>`. On "Not here" (13b) `have.js` asks `/have/online?q=` (60/hour per user; re-checks locally and calls out only on a miss): `utils/have_online.py` asks Google Books / Open Library, TMDb (UPCitemdb for a barcode) and Discogs (MusicBrainz backup) in parallel with one 5 s deadline, ranks the candidates (`score_text`: word coverage, exact-title and creator bonuses) and gives each add links carrying its id. The add pages look `?tmdb_id=`, `?discogs=`, `?mbid=` up on load (`Section.lookup_url` -> `data-lookup-url`), `?isbn=` / `?barcode=` as before, and take `?title=` / `?author=` (`media.add_prefill`).
- **covers** (`/covers`): background "fetch missing covers" jobs: start (scope `own`, or `all` for admins), status, stop, dismiss. Started from the Goodreads import result, the profile page and admin → placeholder covers. Also the cover crop tool's two POST routes (ROADMAP 15.3): `/covers/crop/source` stages a picked photo, `/covers/crop/preview` renders geometry to a JPEG (nothing stored).
- **bulk** (`/bulk`, ROADMAP 14a): bulk edit, the routes over `utils/bulk.py`. `POST /plan` (writes nothing; `{action, params, ids}` or a view selection `{view, args}`, resolved here and returned as the plan's `ids`), `POST /apply` (409 with the fresh plan when the fingerprint is stale), `POST /<id>/undo` (`{banner: false}` from Profile), `POST /selection` (the sheet's list of what each selected item has now), `GET /genres`, `GET /options`. Rate-limited per user. The result banner comes from `session['bulk_result']` via `pop_bulk_result()`.

### Utilities (`/utils/`)
- **database.py**: `get_db()` (request-scoped connection, closed at teardown), `get_db_connection()` (a new connection: `sqlite3.Row`, `PRAGMA foreign_keys = ON`), `database_path()`.
- **book_utils.py**: Google Books / Open Library lookups (the Goodreads-scraping BookCover API was dropped 2026-11-08: slow, often timed out), ISBN helpers, cover search and download (`save_best_cover`: tries candidates in order, keeps the largest real cover, through an SSRF guard that only fetches public hosts; `google_cover_candidates` turns a Google link into its 800x1200 and 128 px versions, ROADMAP 8F), `process_image` for uploads, `get_filter_options`.
- **cover_crop.py**: the cover crop / perspective tool's server side (ROADMAP 15.3): `parse_geometry` (the JSON the browser sends: fractions of the image, never pixels), `render` (rect crop, or a perspective warp whose coefficients `perspective_coeffs` solves in pure Python), staged uploads (`stage_upload`, `is_staged`, `sweep_staged`) and `apply_form_crop` / `crop_or_flash` for the four add/edit routes plus the wishlist's add (priority: valid crop > upload > fetched cover > existing). Only staged files are deleted because the browser named them.
- **image_utils.py**: `is_safe_upload_path`, `delete_image_file` (refuses paths outside `static/uploads/`), and orphaned image detection/cleanup.
- **goodreads.py**: the Goodreads CSV import. One SAVEPOINT per row; returns a report with exactly one outcome per row, which the result screen lists.
- **cover_jobs.py**: the background cover fetcher. A `cover_jobs` row (migration 022) is the job and its progress; a daemon thread per process works through it one book at a time (`book_utils.fetch_cover_for_book`). `worker` + `heartbeat_at` let another gunicorn worker take over a job whose process died; the next `/covers/status` poll restarts it. Tests never start the thread: they call `run_pending()`.
- **search.py**: the grid search boxes' matching (ROADMAP 7.2b): `fold()` (an SQL function on every connection, registered in `get_db_connection`) and `match(term, columns, viewer_id)`: every word, accent- and punctuation-free, in any column or the viewer's tags.
- **reviews.py**: the Reviews section's lists (`reviews_by`, `unreviewed`, `list_rows`, `shelves`), the [+ Review] search (`find`) and the add pages' `then_review_values`. "Newest first" = latest finished date, then rowid (read_data has no timestamp). Also feeds the profile's recent reviews.
- **stats.py**: the profile's statistics (ROADMAP 12.1): `type_stats(conn, user_id, kind)`, the same numbers for books, movies and music (owned vs finished, pages or hours, chart `by_month`, genres, creators, ratings, decades), drawn by `_profile_stats.html`.
- **sorting.py**: the grids' sort orders (ROADMAP 11.4): `choice(args, type)` and `order_by(sort_by, order, viewer_id)` (nulls last, title/id tiebreak; date read and rating are the viewer's). The sort menu `_view_bar.html` is built from `BY_TYPE`.
- **grid_query.py**: the ids a grid shows (ROADMAP 14a): `books_query` (the Books grid's WHERE, used by `base.library_page`), `search_query` (Search's, used by `books.search`; slightly different on purpose, see its docstring) and `view_ids(conn, user, view, args)` for the whitelisted views in `VIEWS` (`book|video|record:mine|household`, `book:search`). Movies and Music go through `Section.filtered`. Change a grid's filters here, or bulk edit's "select all in this view" stops matching the page.
- **bulk.py**: bulk edit (ROADMAP 14a, `docs/BULK-EDIT-SPEC.md`). No Flask: `plan` / `apply` / `undo` / `history` / `recent` / `selection` / `genres` / `options`, and `ACTIONS`, the whitelist (genre, format, owned, remove, restore: owner or admin; status, shelf_add/shelf_remove (custom collections; the UI says "collection"), tag_add/tag_remove: anything `can_view_book` allows). Every write repeats the plan's before-value and the permission in its WHERE; one SAVEPOINT per item with its journal row; a SHA-256 fingerprint of the plan makes a stale apply a 409. Undo writes back only items still as the edit left them. Journals last 30 days (swept on apply); 500 items per edit.
- **media.py**: books, videos and records (Phase 8): media types, formats per type, views and endpoints per type (`VIEWS`, `item_endpoint`; templates get `item_url(row)` and `labels_for(row)`), statuses per type, wording per type (`media_labels()`, passed to templates as `m`), barcode helpers (`classify_code`, `normalize_barcode`, the server twin of `scanner.js`) and `only(type, column)` for queries on `read_data`/`collections`/`reading_sessions`.
- **music_lookup.py**: Add Vinyl pre-fill from MusicBrainz (User-Agent with contact, 1 request/s per process, 6 h cache, `Busy` on 503) and Cover Art Archive covers.
- **media_lookup.py**: Add Video pre-fill: UPCitemdb (barcode) then TMDb (title), through the SSRF guard; `clean_title` strips tape noise. Optional; manual entry is the main path.
- **have_online.py**: Do I have this?'s online candidates on "Not here" (ROADMAP 13b): the three sources at once in a small thread pool (a source past `DEADLINE` is left out, its thread fills the caches), `score_text` / `rank`, and each candidate's add links. Downloads nothing; thumbnails go through `coverSrc`.
- **book_matching.py**: finding an existing book to attach a user's data to (`BookIndex`, `own_book_for_wishlist`). Only the user's own books and their household's shelf are searched, never anyone else's.
- **households.py**: household invites, joining, leaving and owner hand-over (see Access Model).
- **email_utils.py**: verification tokens (random, stored in `email_verification_tokens`) and sending via Flask-Mail.
- **rate_limiting.py**: shared `limiter` instance.
- **errors.py**: 401 handler that redirects to login.

### Database Schema
Tables after all migrations:
- **Books and reading:** `books` (shared catalog, `added_by` = owner), `collections` (per-user reading status), `read_data` (rating/comment), `reading_sessions`, `book_tags`, `user_collections` (custom shelves, one `media_type` each, names unique per section) + `collection_books`, `wishlist`.
- **Goals:** `reading_goals` (one per user and year, migration 029; `users.reading_goal` is the old single goal, unused).
- **Jobs:** `cover_jobs` (background cover fetching, see `utils/cover_jobs.py`).
- **Bulk edit:** `bulk_edits` (one per edit: action, params JSON, summary, `undone_at`) and `bulk_edit_items` (before/after JSON per item), migration 031. `collections.quiet = 1` marks a status set in bulk: the feed skips it, and setting the status by hand resets it to 0.
- **Users and social:** `users` (incl. `is_admin`, `is_active`, `avatar_url`, `bio`, `reading_goal`, `email_verified`), `friendships` (stored with `user_id_1 < user_id_2`), `friend_requests`, `notifications`, `activity_likes`, `dismissed_activities`, `email_verification_tokens`.
- **Households:** `library_members` (one library per user; `library_id` groups members; exactly one `owner` per household), `household_invites` (pending invites).

There is no `activities` table; the feed is built from `read_data`/`collections`/`wishlist` at query time. Some rows are positional (`book[0]`, `book[1]`) in templates, so be careful reordering `SELECT *` columns.

Gotchas:
- **Foreign keys are enforced** (`get_db_connection()` runs `PRAGMA foreign_keys = ON`; needs migrations 014/015). Every FK has a deliberate `ON DELETE` rule: user and book children `CASCADE`, but `books.added_by` is `SET NULL`, so deleting a user never deletes books. A book is a record other people's reviews hang on: hard delete is refused while another user has data on it (`models.other_users_with_book_data`). Don't delete `books` rows anywhere else without that check.
- **Unowned books** (`added_by IS NULL`) are allowed but appear in no library view, since those filter by owner. Handle `None` wherever `added_by` is used.
- **Removed (deaccessioned) books** have `books.removed_at` set: a copy you had that left. "Remove from library" is the normal way a book leaves; hard delete is only for mistakes.
- **Not owned** (`books.owned = 0`, migration 025, ROADMAP 8B.3): read/watched/listened to but never had (an audiobook from the library, a movie seen on TV). Still the user's row (`added_by`), so reviews and statuses hang on it. Separate from removed. **Anything that shows a shelf or counts owned items uses `book_utils.on_shelf()` (`owned = 1 AND removed_at IS NULL`) or `shelf_filter(request.args)`** (the filter panel's Show: shelf / not owned / removed / everything; `?show_removed=` still accepted). Reading stats, reviews and exports keep both kinds.
- **Book formats** (8B.2): a plain book has `format` NULL, an audiobook `'Audiobook'` (`media.book_format`). Audiobooks never count toward page totals.
- **Accounts:** deactivate/delete logic lives in `utils/accounts.py` (shared by admin and self-delete). Exports are in `utils/export.py`, scoped to one user.
- **Videos and records are rows in `books`** (`media_type = 'video'` / `'record'`, migrations 023 and 024). `library_books` is books only, `library_videos` is the Movies section's view and `library_records` the Music section's, so pages on any of the views need nothing else. Allowed types and statuses are rows in the `media_types` and `statuses` lookup tables (foreign keys, not CHECKs, so adding one is an INSERT migration; keep `utils/media.py` in step, a test checks). A query that reads `books`, `read_data`, `collections` or `reading_sessions` directly for a book feature (stats, counts, matching, covers) must add `b.media_type = 'book'` or `media.only(BOOK, ...)`. Statuses differ by type (`media.STATUSES`) and the status route checks them. Movies can be on the wishlist (8.6); the cover fetcher and Goodreads import are books only.
- **Wishlist entries are rows in `books`** (plus a `wishlist` row). Library queries, counts and stats select `FROM library_books b` (a view, migration 018: owned books that aren't the owner's own wishlist entry) instead of `books`, or they'll count wishlist books as owned. The view keeps removed and not-owned books, so still add `on_shelf()` / `shelf_filter()`. A table rebuild of `books` or `wishlist` must drop and recreate the view.

### Access Model (what the code actually does)
Decided and enforced in Phase 4; `tests/test_access.py` and `tests/test_households.py` assert it. A user's **circle** is themselves, their household members and their friends (`models.circle_ids`). Admins see everything.

| Page / action | Who | Where enforced |
|---|---|---|
| Own library, collections, tags, reading history, settings, exports | the user | queries filter on `current_user.id` |
| Shared (household) library | household members | `base.shared_library` via `get_library_members` |
| Profile, stats, reviews, wishlist, reading lists, friend's library | the user and their friends | `get_friendship_status` / `is_friends_with` in `user.py`, `wishlist.py`, `collections.py`, `base.py` |
| Feed | friends' activity (and your own) | `feed.py` |
| Reviews section: friends' reviews | friends only (`models.friend_ids`), never household-only members | `utils/reviews.py`, `blueprints/reviews.py` |
| Book detail `/books/book/<id>` | admins; or someone in your circle owns the book or has data on it (review, status, session, tag, wishlist, collection). 404 otherwise | `models.can_view_book` |
| Attaching your data to a book id (status, review/session, tag, custom collection, wishlist quick-add) | same as book detail, so attaching data can't grant access | `can_view_book` in `read.py`, `collections.py`, `tags.py`, `wishlist.py` |
| Another user's wishlist note on a book page | only from your circle | `books.show_book` |
| Edit, remove/restore, delete, transfer a book | owner or admin (delete also refused while others have data on it) | `books.py` |
| Join a household | by invite only, from the household owner (or someone not in one) to a friend; the invitee accepts or declines on the notifications page | `utils/households.py` |
| Remove from a household | the owner removes anyone; anyone can leave. Owner leaving hands ownership to the longest-standing member; a household of one is dissolved | `utils/households.py` (admin and account deletion use it too) |
| Change email | needs the current password; re-verification if `EMAIL_VERIFICATION_REQUIRED` | `user.update_email` |
| Log out | POST with CSRF (sidebar form) | `auth.logout` |
| Admin pages | admins | `@admin_required` |

There are no per-item privacy settings (private/friends/public); the unused columns from migration 012 were dropped in 020. Household members who aren't also friends see each other's books (shared library, book pages) but not each other's profiles or feed activity.

### Frontend
- **Layout:** every page `{% extends 'base.html' %}` (blocks `title`, `html_class`, `body_class`, `head`, `sidebar`, `content`, `scripts`; auth pages override `sidebar` with nothing). `base.html` includes `_sidebar.html` and `_flash_messages.html` and sets `<meta name="csrf-token">`; pages include `_search_sort_filter.html`, `_book_grid.html` and `_add_fab.html` (the floating `+`, menu items passed as `fab_items`) where relevant. `tests/test_pages.py` fails if a page stops extending it.
- **Shelves and Friends** (ROADMAP 11.1, 11.3): the sidebar has one Shelves entry (`base.shelves`, back to the last section via the `shelf_section` cookie) and a Friends page (`friends.index`); The sidebar's welcome line ends with the Notifications bell (with a count, `notification_count()`); under it Admin Settings (gear, admins only) and a Light/Dark toggle (sun/moon, `data-mode-toggle`); the nav is Feed, Shelves, Reviews, Friends, Do I Have This?, Wishlist, Collections, Profile, Log out. Every grid page starts with `shelf_header(type, scope[, username])` from `_shelves.html` (the heading, whose house icon toggles Mine / Household: grey on yours, accent on the household's (`page_heading(toggle=)`); crumbs above the heading on a friend's; on Household pages a row of member chips, `_household_members.html`, with `?member=` from `households.member_choice`; then the Books | Movies | Music switch); links come from `shelf_url()` and `media.SHELF_ENDPOINTS` (or `section_switch(..., urls={type: url})` on a page that isn't a shelf, as Reviews). UI wording: "shelf" is what you own, "collection" a status or custom list. On a friend's shelves, filters, sorts and list view use the friend's statuses, ratings and tags (the entries in view: `data_user` in `base.library_page` and `media_section` `grid_page`, `marks_user` in `_book_grid.html`); yours everywhere else.
- **Headings and crumbs** (`_icons.html`): a page's title is `page_heading(icon, name, subtitle)` (grids use `section_heading`); pages you drill into (item, review, edit, add, search, shelves, admin sub-pages) start with `crumbs([(label, url), ...], here)` instead of a "Back to" link. Sidebar pages need neither. Sidebar icons come from the same `icon()` macro.
- **Themes:** two per-user settings on `<html data-style=… data-mode=…>` (injected by a context processor in `app.py`, edited at Profile → Appearance, stored in `users.theme_style` / `users.color_mode`). Style `house` (shown as "Negative Earth") = Gruvbox, Courier Prime, square, strong borders; `classic` (shown as "OG") = the original look (Outfit, rounded, soft shadows); `outrun` = 80s neon, dark only, fixed fonts (VT323 body, Audiowide headings and page titles; neon grid and glow; the Mode and Font pickers carry `data-mode-picker` / `data-font-picker` and hide). `shelf` = iBooks-style bookcase (warm neutrals over House's accents; grids marked `shelf-grid` become covers on ledges, no title label (`.book-info` visually hidden, for screen readers) (every cover a 3D box, `.cover-box` round the `<img>`; on the Movies grid the egg button next to grid/list switches on an all-white video-store rack, `<html data-rack="store">`, each movie in a white case with the poster inset or its title printed on it), `.shelf-row` and `.cover-stand` get ledges too; the two Shelf blocks at the end of `styles.css`). An accent (`users.accent`, `data-accent`) applies to all of them, and a font (`users.font`, `data-font`: theme, baskerville, garamond, literata, jost; `models.FONTS`) overrides the style's fonts (`--acc-l` in OG, `--acc-n` neon shades in Outrun). Mode `system|light|dark`. Every colour, radius, shadow and the body font are CSS variables in `static/styles.css`; `tailwind.config.js` maps Tailwind names onto them. Use the semantic classes (`bg-secondary`, `text-content-primary`, `bg-accent text-on-accent`, `border-card` for card outlines, `rounded-pill` for badges) rather than raw colours. Fonts are served from `static/fonts/`.
- **Vanilla JS in `/static/`:**
  - `static/vendor/`: vendored third-party JS (quagga2 for barcode decoding), with source and hashes in its README (`tests/test_csp.py` checks the hashes). Don't load scripts from CDNs.
  - `scanner.js`: the barcode scanner of the add page (`add_item.html`: Add Book, Add Movie, the wishlist's add) (`createBarcodeScanner`): camera, camera picker, target box, check digits and read confirmation. The decoder sits behind a small interface (`quaggaDecoder`). Its pure helpers are tested under node in `tests/test_scanner_js.py`.
  - `common.js`: loaded in `<head>` by `base.html` on every page. `getCSRFToken`, `getCSRFHeaders`, `addCSRFToFormData`, `escapeHtml`, `coverSrc`, `showFlashMessage`, `dismissFlash`, `postForm`, and the `data-click`/`data-change`/`data-submit`/`data-confirm`/`data-fallback-src` dispatcher (`registerActions`). Don't redefine these in page scripts.
  - One file per page that needs script: `user.js`, `admin_settings.js`, `book_detail.js`, `rate_review.js`, `goodreads_import.js`, `activity_feed.js`, `orphaned_images.js`, `fab.js` (the add-book button partial), loaded in the page's `{% block scripts %}`.
  - `script.js`: library grid, filters, infinite scroll, status updates (and a few book-page helpers). Grid and list view are the same cards (`_book_grid.html`, `createBookCard`); `switchView` only sets `data-view` on `#book-container` (and drops `.grid` in list view), and list view is CSS ("List view" in `styles.css`). Infinite-scroll JSON comes from `book_utils.card_json`.
  - `add_item.js`: the add page for books and movies (`add_item.html`, fields in `_item_fields.html`): Search / ISBN-or-Barcode / Scan tabs, one adapter per media type, lookups that never overwrite what you typed, the duplicate notice.
  - `cover_crop.js`: the crop / perspective dialog (`_cover_crop.html`, included by `_item_fields.html`) on Add and Edit: pointer-event dragging with one `requestAnimationFrame` per frame, a loupe, Undo as a stack of geometries. Its pure helpers are tested under node in `tests/test_cover_crop_js.py`. Other cover scripts announce a changed cover with a `cover-changed` document event, which clears a pending crop.
  - `cover_finder.js`: "Find a better cover" on Edit Book and Add Book (books only): reads the NDJSON progress stream of `/books/fetch_cover` (any signed-in user, 30/hour), shows a progress bar and each cover as it downloads.
  - `edit_book.js`: Edit Book's upload preview (the fields are `_item_fields.html`).
  - `wishlist.js`: the wishlist page's filter (adding is `add_item.js`).
  - `tags.js`: tag add/remove.
  - `sidebar.js`: hamburger menu, loaded by `_sidebar.html`; also the appearance pickers (`setAppearance`) and the sidebar's sun/moon toggle. There is no header search: each grid page has a search box and a filter button in one row under its tabs (`_search_sort_filter.html`; the panel is `toggleFilters` in `script.js`), the wishlist a filter box under its tabs.
  - `shelf.js`: loaded by `base.html` in `<head>` (not deferred) on every page: the Shelf style's movie-rack easter egg (`toggleRack`, `data-rack` on `<html>`, localStorage `shelfRack`).
  - `cover_jobs.js`: the floating cover-fetch progress panel, loaded by `_sidebar.html`; it only shows and polls when the user has a job (`cover_job`, from a context processor in `app.py`).
  - `bulk.js`: bulk edit on the grids (`_bulk_select.html` = `_bulk_bar.html` + `_bulk_sheet.html` + this script; a page sets `bulk_select` before `_book_grid.html`, and `bulk_view` on a paged grid; the banner is `_bulk_result.html`). Select mode is `data-select="on"` on `#book-container` (listbox / options, roving tabindex; long-press a cover on grids marked `data-bulkable`); new cards arrive through `script.js`'s `cards-added` event. The sheet: choose (one panel per action, the selected items with their current values), then the review from `/bulk/plan`, then apply. Pure helpers at the top are tested under node in `tests/test_bulk_js.py`. Never on a friend's grids.

## Product direction (from Phil, 2026-11-05)

Not scheduled and not to be worked on until Phil picks them up; they belong in a future ROADMAP phase.

- **The catalog is for physical books Phil owns.** Audiobooks don't really belong in it: either leave them out of imports, or later integrate with Phil's Audiobookshelf server, which tracks audiobooks better than this project should.
  - **Settled 2026-11-08 (ROADMAP 8B.2/8B.3):** audiobooks are books with format Audiobook, usually not owned (`books.owned = 0`): in reading stats and reviewable, never on the shelf unless owned, never in page totals. The Goodreads `audiobook` shelf imports that way. Audiobookshelf integration stays a later idea.
- **Revisit book info and cover fetching.** Today it's clunky (many sources), slow, and covers still aren't always right. Now ROADMAP Phase 8F (cover quality).
- **Granular Goodreads import:** a selection grid with sorting, so the user picks which rows to import and where they go. Now ROADMAP Phase 13, with bulk edit. Ideally covers would come with the import, if that's possible at all (the export has no cover URLs).
- Goodreads `to-read` rows go to the wishlist on purpose, not the library with *Want to Read*: that would add books Phil doesn't own. (Rows for books he or his household already own do get *Want to Read*.)

## Important Development Notes

### Authentication & Security
- The first registered user becomes admin. Admin routes use `@admin_required` from models.py.
- Passwords are hashed with the raw `bcrypt` module (not Flask-Bcrypt).
- Usernames must match `^[A-Za-z0-9_.-]{3,30}$` (`models.is_valid_username`); this is enforced on register, rename and admin create.
- CSRF: Flask-WTF `CSRFProtect` is global. Forms include `csrf_token()`; fetch calls send the `X-CSRFToken` header (both `X-CSRFToken` and `X-CSRF-Token` are accepted) using `getCSRFToken()` from `common.js`, which reads a hidden `csrf_token` input or the `<meta name="csrf-token">` that `base.html` puts on every page.
- Session and remember-me cookies are HttpOnly and SameSite=Lax. They are `Secure` only in production; remember-me lasts 30 days.
- `after_request` sets a **Content-Security-Policy** (`script-src 'self'`, `img-src 'self' data: blob:`, `connect-src 'self'`, `worker-src 'self'`; inline `style=` allowed), plus `X-Content-Type-Options`, `X-Frame-Options: SAMEORIGIN` and `Referrer-Policy`. `CSP_REPORT_ONLY=true` makes it report-only.
- Rate limiting:
  - No global default (it caused 429s while browsing). Per-route `@limiter.limit()` on auth, profile updates, friend and household requests, and imports (`utils/rate_limiting.py`).
  - Storage is in memory, so each gunicorn worker counts separately (effective limit = limit x workers). Redis is the fix if that ever matters.
  - Behind a reverse proxy, set `TRUSTED_PROXY_COUNT` so limits use the real client IP.

### Security conventions (follow these in new code)
- **Image paths from the browser** (hidden form fields such as `existing_cover_url` and `fetched_cover_url`) must pass `is_safe_upload_path()` before being stored. Never call `os.remove` on a DB path without going through `delete_image_file()`.
- **Server-side fetches of URLs** must go through `book_utils._get_public()` / `_fetch_image()` (public-IP check on every redirect).
- **No inline JS** (the CSP blocks it): no `<script>` without `src`, no `onclick=`/`onchange=`/`onerror=` in templates or in HTML built by JS. Use `data-click` / `data-change` / `data-submit="name"` with `registerActions({name: (el, event) => ...})`, `data-confirm="..."` for confirmations, `data-fallback-src` for image fallbacks (all in `common.js`). Pass server values to page scripts in `data-` attributes, not Jinja inside JS. `tests/test_csp.py` enforces this.
- **Remote images** (search-result covers) go through `coverSrc(url)` → `/books/thumbnail`, never straight into `img.src`.
- **Never put data into `innerHTML`/template literals unescaped.** Use `escapeHtml()` (or `textContent`), and `encodeURIComponent` for URL path segments.
- **State-changing routes are POST-only** with CSRF. Check ownership in the SQL (`WHERE ... AND user_id = ?`) for anything addressed by id.
- **Reusing an existing book record** (by ISBN or title) goes through `utils/book_matching.py`. Never match against all of `books`: your data would hang on a stranger's copy that never shows in your library.
- Don't return `str(e)` to clients in new code; log it and return a generic message.

### Image Handling
- Covers are uploaded or auto-fetched, resized to MAX_IMAGE_SIZE (500x1000), and stored under `static/uploads/` as `uploads/...` paths relative to `static/`. Avatars go in `static/uploads/avatars/`.
- Fallback image (JS, when a cover fails to load): `static/no-cover.svg`. Templates show a themed "No Image Available" box instead.
- `app.py` sets `UPLOAD_FOLDER = static/uploads` (relative to the working dir), overriding the paths in config.py.

### Database Migrations
- SQL files in `/migrations/` (`NNN_name.sql`), applied in order by `manage.py migrate`, tracked in `schema_migrations`. See `migrations/README.md`.
- When adding a migration, either fold it into `create_database.sql` (and add its name to the ledger INSERT there) or leave it for `migrate` to apply after the schema.

### Environment Variables
Read via python-dotenv from `.env`:
- **SECRET_KEY**: required in production. A warning is logged if it's still the `.env.example` placeholder.
- **GOOGLE_BOOKS_API_KEY**: Google Books lookups.
- **TMDB_API_KEY**: optional, film details for video lookups (v4 read access token preferred, or v3 key). Without it, UPCitemdb only.
- **DISCOGS_TOKEN**: optional, Discogs personal access token (discogs.com/settings/developers) for Add Album's search (`utils/discogs_lookup.py`). Without it, MusicBrainz only.
- **MUSICBRAINZ_CONTACT**: contact in the MusicBrainz User-Agent (an email is best; default the GitHub URL).
- **FLASK_ENV**: `development` or `production`.
- **DATABASE_PATH**: SQLite file used by `utils/database.py` and `manage.py` (default `library.db` in the project directory).
- **ALLOW_REGISTRATION**: `False` closes self-registration once the first user exists (default `True`).
- **TRUSTED_PROXY_COUNT**: number of reverse proxies to trust for `X-Forwarded-*` (default 0 = off).
- **EMAIL_VERIFICATION_REQUIRED** and **MAIL_SERVER / MAIL_PORT / MAIL_USE_TLS / MAIL_USERNAME / MAIL_PASSWORD / MAIL_DEFAULT_SENDER**: email verification.
- **PORT**: dev server port.
- **CSP_REPORT_ONLY**: `true` sends the Content-Security-Policy as report-only (escape hatch; default enforced).

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
Never call `conn.close()` on it. Outside a request (`manage.py`, scripts, the `cover_jobs` thread) use `get_db_connection()` in try/finally and close it. Never use `with get_db_connection() as conn:` (it commits but doesn't close).

#### API Response Pattern
```python
return jsonify({"success": True, "data": data}), 200
return jsonify({"success": False, "error": "Error message"}), 400
```

### Testing Notes
- **Tests:** `pip install -r requirements-dev.txt`, then `pytest` (about a second). CI (`.github/workflows/basic-tests.yml`) runs them on every push/PR to `main` with Python 3.12, after a syntax check and a `create_app()` start check.
- `tests/conftest.py` builds one DB with `manage.py migrate` and gives each test its own copy via `DATABASE_PATH`; it sets the env before importing the app (so `.env` can't interfere), disables CSRF and rate limits, and blocks network calls. Seed helpers: `people` fixture (alice = admin, alice + bob share a household, carol is alice's friend), `add_user`, `add_book`, `add_review`, `login`, `scalar`, `fk_violations`.
- Add a test with every bug fix or new route. `test_every_page_loads` hits every GET route automatically; a new route with URL arguments needs its argument name in that test's `filled` dict.
- For manual checks, use a copy of the DB: `DATABASE_PATH=/tmp/test.db python3 app.py`.
- First-time setup: visit `/` and you'll be redirected to register the admin user.
- Camera/barcode scanning needs HTTPS (`--cert`/`--key`, see `docs/HTTPS-SETUP.md`).

### Repo Layout Notes
- `docs/`: HTTPS setup, flash message notes. `docs/archive/`: old AI-generated implementation summaries and one-off scripts, kept for history and possibly stale.
- `node_modules/`, `venv/`, `.env`, `*.db` and `static/uploads/` are git-ignored.
