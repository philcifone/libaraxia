# CLAUDE.md

Guidance for Claude Code in this repository. Kept short on purpose: it is loaded into every session.

- **Open work** lives in [ROADMAP.md](ROADMAP.md), numbered phases worked in order. Check it before a task; tick items when done.
- **Finished phases** are in [docs/ROADMAP-ARCHIVE.md](docs/ROADMAP-ARCHIVE.md) under their original numbers, which code comments cite ("ROADMAP 7.2b"). Grep it, don't read it whole.
- **The module map** (every blueprint, utility, table, template partial, script, theme, env var) is [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Read the section you need before working in an unfamiliar area, and update it when you add or rename a module.

## Project

Libaraxia is a Flask app for cataloguing books, movies and music, tracking reading, and sharing with friends and a household. SQLite through raw `sqlite3` (no ORM); Google Books / Open Library, TMDb, Discogs / MusicBrainz for metadata. Vanilla JS, Tailwind.

**Prod deploys itself.** It runs under gunicorn (no Docker; the Docker files are reference only). A systemd timer runs `deploy/deploy.sh`, which fast-forwards to `main` once CI passes, migrates and restarts (`deploy/README.md`). A push to `main` with green CI is live in about 5 minutes.

## Commands

```bash
pip install -r requirements.txt -r requirements-dev.txt; npm install; cp .env.example .env
python3 manage.py migrate                 # new DB from create_database.sql; existing: backup + pending migrations
python3 manage.py status
python3 manage.py --db /tmp/x.db migrate  # any other file
python3 app.py                            # dev server (HTTPS for the camera: --cert certs/cert.pem --key certs/key.pem)
DATABASE_PATH=/tmp/test.db python3 app.py # manual checks on a copy of the DB
npm run build:css                         # after adding Tailwind classes; input is static/styles.css, output.css is committed
pytest                                    # about a second; CI runs it on every push/PR to main (Python 3.12)
```

## Data model gotchas

- **Migrations:** `migrations/NNN_name.sql`, applied by `manage.py migrate`, tracked in `schema_migrations` (`migrations/README.md`). No BEGIN/COMMIT in a migration; each runs in its own transaction with FKs off and is rolled back if it adds `foreign_key_check` violations. Fold a new one into `create_database.sql` (and its ledger INSERT) or leave it for `migrate`. A pre-runner DB needs `migrate --baseline` once. Always check which DB file you're touching.
- **Foreign keys are enforced** (`PRAGMA foreign_keys = ON` in `get_db_connection()`). User and book children `CASCADE`; `books.added_by` is `SET NULL`, so deleting a user never deletes books. Hard-deleting a book is refused while another user has data on it (`models.other_users_with_book_data`); don't delete `books` rows anywhere without that check.
- **Videos, records and wishlist entries are all rows in `books`** (`media_type` = `book` / `video` / `record`; wishlist entries also have a `wishlist` row). Query the views: `library_books` (books only, not the owner's wishlist entries), `library_videos`, `library_records`. A query on `books`, `read_data`, `collections` or `reading_sessions` directly for a book feature must add `b.media_type = 'book'` or `media.only(BOOK, ...)`. A table rebuild of `books` or `wishlist` must drop and recreate the views.
- **Media types and statuses** are rows in the `media_types` and `statuses` lookup tables (FKs, not CHECKs: adding one is an INSERT migration). Keep `utils/media.py` in step; a test checks. Statuses differ by type (`media.STATUSES`).
- **On the shelf vs not:** `books.removed_at` = deaccessioned (the normal way an item leaves; hard delete is for mistakes). `books.owned = 0` = read/watched but never had (still the user's row, reviews hang on it). Anything that shows a shelf or counts owned items uses `book_utils.on_shelf()` or `shelf_filter(request.args)`; the views keep removed and not-owned rows. Reading stats, reviews and exports keep both.
- **Unowned books** (`added_by IS NULL`) appear in no library view. Handle `None` wherever `added_by` is used.
- **Audiobooks** are `format = 'Audiobook'` (a plain book is NULL), usually not owned, never in page totals.
- **Grid filters** live in `utils/grid_query.py` (Books) and `Section.filtered` (Movies, Music). Change them there, or bulk edit's "select all in this view" stops matching the page.
- **Goodreads provenance:** `goodreads_rows` records what each imported CSV line did to which book (`book_id` SET NULL). It drives the From Goodreads filter, the book page note and the next import's Book Id match, so keep it when merging or deleting books. Imports undo through the bulk journal (`bulk_edits.action = 'goodreads'`).
- There is no `activities` table; the feed is built from `read_data` / `collections` / `wishlist` at query time (`collections.quiet = 1`, set by bulk edit, hides a status from it). Some templates read rows positionally (`book[0]`), so don't reorder `SELECT *` columns.
- **UI names vs code names:** the UI says "Movies" (VHS shown as "Cartridge") and "Music" (an item is an "album"); code, URLs and the DB say `video`, `VHS` and `record`. Wording per type comes from `media.media_labels()` (`m` in templates). "Shelf" is what you own; "collection" is a status or custom list.

## Access model

A user's **circle** is themselves, their household and their friends (`models.circle_ids`). Admins see everything. `tests/test_access.py` and `tests/test_households.py` assert this.

| Page / action | Who | Where enforced |
|---|---|---|
| Own library, collections, tags, history, settings, exports | the user | queries filter on `current_user.id` |
| Shared (household) library | household members | `get_library_members` |
| Profile, stats, reviews, wishlist, friend's library, feed | the user and their friends | `get_friendship_status` / `is_friends_with` |
| Reviews section: friends' reviews | friends only (`models.friend_ids`), never household-only members | `utils/reviews.py` |
| Book detail; attaching your data (status, review, tag, collection, wishlist) to a book id | admins, or someone in your circle owns it or has data on it; 404 otherwise | `models.can_view_book` |
| Another user's wishlist note on a book page | your circle | `books.show_book` |
| Edit, remove/restore, delete, transfer a book; bulk genre/format/owned/remove | owner or admin | `books.py`, `utils/bulk.py` |
| Join / leave a household | invite from the owner to a friend; anyone can leave, owner leaving hands over to the longest member | `utils/households.py` |
| Change email | current password (plus re-verification if required) | `user.update_email` |
| Admin pages | admins | `@admin_required` |

No per-item privacy settings. Household members who aren't friends see each other's books but not profiles or feed.

## Security conventions (follow in new code)

- **No inline JS** (CSP `script-src 'self'`): no `<script>` without `src`, no `onclick=` etc., in templates or JS-built HTML. Use `data-click` / `data-change` / `data-submit` with `registerActions`, `data-confirm`, `data-fallback-src` (`common.js`). Pass server values in `data-` attributes. No CDNs; third-party JS goes in `static/vendor/` with hashes. `tests/test_csp.py` enforces this.
- **State-changing routes are POST-only** with CSRF (global `CSRFProtect`; fetch sends `X-CSRFToken` via `getCSRFToken()`). Check ownership in the SQL (`WHERE ... AND user_id = ?`).
- **Image paths from the browser** must pass `is_safe_upload_path()`. Never `os.remove` a DB path except through `delete_image_file()`.
- **Server-side URL fetches** go through `book_utils._get_public()` / `_fetch_image()` (public-IP check on every redirect). **Remote images** in the browser go through `coverSrc(url)`.
- **Escape everything** put into `innerHTML` (`escapeHtml()` or `textContent`; `encodeURIComponent` for URL segments).
- **Reusing an existing book record** goes through `utils/book_matching.py`; never match against all of `books`.
- **User-chosen values never share a namespace with the site.** No route segment, element id, URL hash, query key or storage key may be both fixed by code and choosable by a user (a user called `settings` vs `/user/settings`). Build ids from numeric ids or fixed keys, never names; a new fixed route beside `<username>` is reserved automatically. Tests assert on markers (`data-*`, hrefs), not on words a user's data could also contain.
- Don't return `str(e)` to clients; log it and return a generic message.
- Passwords use raw `bcrypt`. Usernames go through `models.username_error` (rules, not a page name, unique ignoring case). Rate limits are per-route `@limiter.limit()` (no global default), in-memory per worker.

## Code conventions

- **DB in a request:** `conn = get_db()` (request-scoped, closed at teardown; uncommitted work rolls back). Commit explicitly; never `conn.close()` it. Outside a request use `get_db_connection()` in try/finally. Never `with get_db_connection() as conn:` (commits but doesn't close).
- **JSON responses:** `{"success": True, ...}` / `{"success": False, "error": "..."}` with a status code.
- **New blueprint:** `Blueprint(...)`, `@login_required` (plus `@admin_required` / `@limiter.limit`), register in `app.py`.
- **Templates:** every page extends `base.html` (`tests/test_pages.py` checks). Titles with `page_heading`, drill-down pages start with `crumbs(...)` (`_icons.html`). Shelf grids start with `shelf_header(...)` (`_shelves.html`). Covers and avatars: test `x|upload_exists`, not the bare column.
- **Styling:** every colour, radius and font is a CSS variable in `static/styles.css`, mapped in `tailwind.config.js`. Use the semantic classes (`bg-secondary`, `text-content-primary`, `bg-accent text-on-accent`, `border-card`, `rounded-pill`), never raw colours, so all four styles (house, classic, outrun, shelf) and the accents work.
- **JS:** `common.js` (loaded on every page) has `getCSRFToken`, `escapeHtml`, `coverSrc`, `showFlashMessage`, `postForm` and the `data-*` dispatcher; don't redefine them. One script per page that needs one, in `{% block scripts %}`. Pure helpers in `scanner.js`, `cover_crop.js` and `bulk.js` are tested under node.
- **Tests:** add one with every bug fix or new route. `tests/conftest.py` gives each test its own DB copy, disables CSRF and rate limits, blocks the network, and seeds `people` (alice = admin, alice + bob share a household, carol is alice's friend). `test_every_page_loads` hits every GET route; a new route with URL arguments needs its argument name in that test's `filled` dict.
