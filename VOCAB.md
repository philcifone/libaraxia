# Vocabulary

The proper names for the things in and around Libaraxia: product features,
code, architecture and infrastructure. Read it at your own pace. Each entry
says what the term means here, and where it lives when that helps.

"You might say" lines give an everyday word and the term it usually maps to,
so the proper one is easy to find next time. They aren't corrections; plenty
of everyday words are fine in conversation.

Started 2026-11-26. New terms are added as the work brings them up.

## You might say

| You might say | Proper term | Note |
|---|---|---|
| theme | **style**, **mode**, **accent** | Three separate settings: the style (House, Classic, Outrun, Shelf, Cyberpunk), light/dark mode, and the accent colour. "Theme" covers all three loosely. |
| loading screen (Cyberpunk) | **boot screen** | `static/cyberpunk.js`. Plays at login in Cyberpunk. |
| loading screen (home-screen app) | **launch splash**, **splash screen** | `static/splash.js`. Plays once per launch of the installed app. |
| add the app to my Home Screen | **install the PWA** | See *Progressive web app* below. |
| drop-down hidden toggle | **collapsible section**, **disclosure** | A block that opens and closes when you click its header. HTML has one built in: `<details>` / `<summary>`. A **drop-down** is usually a menu or `<select>`. |
| the CD/DVD transparency (crop tool) | **Disc shape**, a **mask** or **cutout** | The crop tool's round shape makes the outside see-through by writing an **alpha channel**. |
| the heading (an item's page) | **item heading**, **cover stand** | Same word as the code: `_item_heading.html` is the top of the item page; the cover stands on its ledge in `.cover-stand`. |
| the 3D box effect | **cover box** | `.cover-box` in Shelf style, its sides drawn by **pseudo-elements**. |
| the 3D view | **3D item** | The dialog that turns an item in 3D (`utils/item3d.py`, `.item3d-*`). |
| placeholder (for a missing photo) | **placeholder face** | An admin-uploaded stand-in for a spine, side, back and so on (`utils/faces.py`). |
| merge with main (already on main) | nothing to merge | A **merge** joins one branch into another. Work done straight on `main` is just **committed**. |
| push it live | **push**, then **deploy** | You push to GitHub; the server **deploys** it once CI passes. |
| delete (an item off the shelf) | **deaccession**, **remove** | Libaraxia's normal way out: `removed_at` is set, history and reviews stay. **Hard delete** is for mistakes. |

## Product and UI

- **Shelf**: a media section you own: the bookshelf, the movie shelf, the music shelf. "On the shelf" means owned and not removed.
- **Collection**: a status (Read, Watched, and so on) or a custom list you make. Never called a shelf.
- **Media type**: book, movie, album. The UI says Movies and Music; the code and database say `video` and `record` (VHS shows as "Cartridge").
- **Format**: the physical form within a media type: DVD, Blu-ray, CD, vinyl, Audiobook.
- **Circle**: you, your household and your friends. It decides who can see what (`models.circle_ids`).
- **Household**: users who share one library, like two people in one home.
- **Deaccession**: a library term for formally taking an item out of a collection. Here it sets `removed_at`.
- **Wishlist entry**: an item you want; stored as a row in `books` with a `wishlist` row beside it.
- **Feed**: friends' activity, built at request time from statuses and the wishlist, not stored as its own table.
- **Easter egg**: a hidden feature found by exploring. Cyberpunk is one: it isn't in the sidebar cycler, only in Settings.
- **Bare disc**: a DVD or CD kept without its case. Its cover is cut with the Disc shape; it draws no box and turns in 3D as a disc.

## Architecture (the app itself)

- **Flask**: the Python web framework the app is built on.
- **Route**: a URL the app answers, and the function that answers it (a **view function**).
- **Blueprint**: a group of related routes in its own file, registered on the app (`blueprints/`).
- **Request context**: the state Flask keeps while it answers one request: the user, the DB connection (`get_db()`), `g`.
- **`g`**: Flask's per-request scratch space. A value computed once per page is kept there (for example `g.disc_fronts`).
- **Template**: an HTML file with placeholders, filled in by **Jinja**, the templating language.
- **Partial** / **include**: a piece of template reused by others, named with a leading underscore (`_covers.html`).
- **Macro**: a Jinja function that outputs HTML (`cover_box(...)`, `face_choice(...)`).
- **Autoescaping**: Jinja turns `<` and quotes into safe codes so data can't inject HTML. Why some values need `|safe` or a separate field.
- **JS twin**: a JavaScript function that builds the same HTML as a Jinja macro, for pages that add cards without reloading (infinite scroll). Kept in step by tests.
- **Infinite scroll**: the grid loads more cards as you scroll, as JSON from `card_json`, drawn by the JS twins.
- **Raw SQL** / **no ORM**: queries are written by hand with `sqlite3`. An **ORM** (object-relational mapper) would generate them from Python classes.

## Database

- **SQLite**: the database, one file (`library.db` in prod, `dev/dev.db` in dev).
- **Schema**: the shape of the database: its tables, columns and rules. `create_database.sql` builds a fresh one.
- **Migration**: a numbered SQL file that changes an existing database's schema (`migrations/049_disc_faces.sql`).
- **Ledger**: the record of which migrations have run (`schema_migrations`), so each runs once.
- **Table rebuild**: SQLite can't change some rules in place, so a migration creates a new table, copies the rows, drops the old one and renames the new one.
- **CHECK constraint**: a rule on a column the database enforces, such as "kind must be one of spine, side, ...". Changing one needs a table rebuild.
- **Foreign key (FK)**: a column that points at a row in another table. **CASCADE** deletes the children along with the parent; **SET NULL** blanks the pointer instead.
- **Lookup table**: a small table of allowed values (`media_types`, `statuses`), pointed at by foreign keys. Adding a value is an INSERT, not a rebuild.
- **View** (SQL): a saved query that reads like a table (`library_books`, `library_videos`).
- **AUTOINCREMENT** / **sqlite_sequence**: SQLite's counter for new ids, so a deleted id is never reused. A table rebuild must carry it over.
- **Transaction**: a group of changes that all happen or none do. Each migration runs in one.

## Front end

- **CSS custom property** (a CSS variable): a named value like `--box-shadow`, set once and used everywhere. Every colour, radius and font here is one.
- **Design token**: the general name for those shared values: colours, radii, spacing.
- **Tailwind**: the utility-class CSS framework (`bg-secondary`, `rounded-pill`). `npm run build:css` compiles `styles.css` into `output.css`.
- **Pseudo-element**: `::before` / `::after`, extra boxes CSS draws without extra HTML. The cover box's sides are these.
- **Specificity**: how CSS decides which of two matching rules wins. The more precise selector beats the general one, which is why the grid's shadow beat the disc rule until the variable was cleared.
- **CSS 3D transform**: `rotateY`, `perspective`, `transform-style: preserve-3d`, which turn flat faces into a solid in the browser.
- **`drop-shadow` vs `box-shadow`**: `box-shadow` follows the element's rectangle; the `drop-shadow()` filter follows the visible pixels, so a round image gets a round shadow.
- **Data attribute**: `data-*` on an HTML element (`data-shape="disc"`), used to pass values to CSS and JS.
- **Event delegation**: one listener catches clicks for the whole page and acts on `data-click` and friends, instead of a handler on each element (`common.js`).
- **Headless browser**: a browser with no window, run from the command line to take screenshots.

## Images

- **Alpha channel**: the per-pixel transparency layer of an image. 0 is fully see-through.
- **AVIF**: the compact image format uploads are saved in. It keeps transparency.
- **Corner test**: how a disc cover is recognised: all four corners see-through (`image_utils.is_disc`).
- **Memoization** / **cache**: remembering a function's answer so the same question isn't worked out twice. `lru_cache` keeps the most recent answers; keyed by file path and modified time so a changed file is checked again.
- **Path traversal**: a file path like `../etc/passwd` that escapes the uploads folder. `is_safe_upload_path()` refuses them.

## Progressive web app (PWA)

- **PWA**: a website that can be installed like an app: its own icon, no browser bars.
- **Web app manifest**: a JSON file naming the app, its icons and how it opens (`static/icons/manifest.webmanifest`).
- **Standalone display mode**: the installed app's window, with no address bar. `splash.js` detects it with the media query `(display-mode: standalone)`.
- **Apple touch icon**: the icon iOS uses on the Home Screen.
- **Maskable icon**: an icon with padding, so Android can crop it into a circle or squircle.
- **`theme-color`**: the colour the phone paints its status bar.
- **sessionStorage**: browser storage that lasts while the app or tab stays open, used for "once per launch". **localStorage** lasts until cleared.
- **Service worker**: a background script for offline use and push notifications. Libaraxia doesn't have one; Home Screen install works without it.

## Security

- **CSP** (Content Security Policy): a header telling the browser which scripts may run. Here only files from the site, never inline `<script>` or `onclick=`.
- **CSRF** (cross-site request forgery): another site tricking your browser into sending a request to this one. Every POST carries a token to prove it came from these pages.
- **Referer check**: over HTTPS, Flask-WTF also checks that a POST says it came from this site. Why scripts that log in must send a Referer header.
- **Rate limit**: a cap on how often a route can be hit (`@limiter.limit()`).
- **bcrypt**: the password hashing scheme.

## Infrastructure and workflow

- **Dev server**: the copy of the app you test on, `https://192.168.1.239:5000`, run by the user service `libaraxia-dev`.
- **systemd unit**: a service definition systemd runs and restarts. A **user service** (`systemctl --user`) runs as you, not root. A **timer** runs a unit on a schedule.
- **gunicorn**: the production web server that runs the Flask app with several workers.
- **mkcert**: makes a local certificate authority so the dev server's HTTPS is trusted on your devices.
- **LAN**: your local network. The dev server binds to `0.0.0.0` so other devices on it can reach it.
- **CI** (continuous integration): GitHub runs the tests on every push to `main`.
- **Continuous deployment**: prod updates itself when CI passes (`deploy/deploy.sh`, about 5 minutes after a push).
- **Fast-forward**: moving a branch ahead to a newer commit when nothing has diverged, with no merge commit. What the deploy does to `main`.
- **Commit** / **push**: a commit records changes locally; a push sends commits to GitHub.
- **Worktree**: a second checkout of the same repo in another folder, for working on two branches at once.

## Testing

- **pytest**: the test runner (`venv/bin/python -m pytest -q`).
- **Fixture**: a ready-made thing a test asks for by name, such as `client`, `db` or `people`, set up in `tests/conftest.py`.
- **Regression test**: a test added with a bug fix, so the bug can't come back unnoticed.
