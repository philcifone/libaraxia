# Roadmap

The phased plan for Libaraxia: every open action item, security follow-up and bug found so far, in the order to work through them. This is the **single list of open work**. Tick items (`[x]`) as they land, and move a finished phase to [Done](#done) with a date.

- Assembled **2026-11-02** from the old `ACTION_ITEMS.md` (security audit of 2026-10-28), [FORK-SPEC.md](FORK-SPEC.md) (2026-11-01), and a screenshot/data pass on 2026-11-02 against an anonymised copy of `library.db`.
- **Phases 0–8 are all core Libaraxia work** and don't depend on the fork. The archive fork is parked as Phase 9, a future idea. [FORK-SPEC.md](FORK-SPEC.md) holds the fork plan, and also the original VHS design notes (Phase 8).
- Items marked 🆕 are new findings from 2026-11-02.

Priority key: 🔴 do soon · 🟠 important · 🟢 nice to have

## Phases at a glance

| # | Phase | Why this order | Done when |
|---|---|---|---|
| 0 | [Design refresh](#phase-0-design-refresh) | Match philcifone.com / negativeearth.net now; everything built later is built in the new look | Same elements, new skin: Gruvbox light + dark, Courier Prime + Young Serif, square corners, strong borders |
| 1 | [Prod upkeep](#phase-1-prod-upkeep) | Prod sits behind Cloudflare Access (2FA, 2–3 allowlisted emails), so this is upkeep, not an emergency. Do it before Phase 2 touches the DB | Prod DB path recorded, deps upgraded, `pip-audit` clean |
| 2 | [Data foundations](#phase-2-data-foundations) | Everything later writes migrations and needs tests | Fresh install is one command; migrations tracked; FK check clean; smoke tests in CI |
| 3 | [Data correctness](#phase-3-data-correctness) | Fix what the data already shows is wrong | Stats, covers, reviews and wishlist behave correctly |
| 4 | [Access & privacy](#phase-4-access--privacy) | Remaining security follow-ups | Every page has a decided and enforced access rule |
| 5 | [Finish the Goodreads import](#phase-5-finish-the-goodreads-import) | Self-contained; benefits from Phase 2 tests | A real Goodreads export imports cleanly, shelves included |
| 6 | [Page structure](#phase-6-page-structure) | One layout, no inline scripts; unlocks CSP | All pages extend `base.html`; CSP on |
| 7 | [Design polish](#phase-7-design-polish) | Per-page finish once pages share a layout | Film-frame covers, page fixes, a11y (theme toggle done early) |
| 8 | [VHS / UPC support](#phase-8-vhs--upc-support) | Built in the new style | A VHS can be scanned or entered, filtered and displayed |
| 9 | [Fork (parked)](#phase-9-the-archive-fork-parked) | Not planned yet; listed so the idea isn't lost | n/a |

Phases 3, 4 and 5 are independent of each other and can be interleaved. The ordering 0 → 1 → 2 → (3, 4, 5) → 6 → 7 → 8 → 9 is the part that matters.

**Why the refresh can go first without the `base.html` refactor:** the templates already use *semantic* Tailwind names: `text-content-secondary` ×319, `text-content-primary` ×222, `bg-primary` ×118, `bg-accent`/`text-accent` ×212, `font-display` ×40, plus Tailwind's default `white`, `gray-600/700`, `red`, `yellow`, `green`, `blue` and `shadow-*`. Re-pointing those names in `tailwind.config.js` recolours, re-fonts and squares off nearly every page **without editing templates**. Hand edits are limited to the shared partials, a find-and-replace adding borders to cards, and the text colour on coloured buttons. Per-page cleanup waits for Phase 7, when there's one layout to edit.

---

## Phase 0: Design refresh

**Goal: a reskin, not a redesign.** Libaraxia keeps every element it has today and takes on the look of philcifone.com and negativeearth.net:
- Courier Prime as the main font, Young Serif for headings
- Gruvbox colours in **light and dark**
- square corners, strong 1px borders, no soft shadows

This is core Libaraxia work with no dependency on the fork. Token values were taken from the sites' CSS on 2026-11-01, and everything needed is in this section.

| Keep exactly as is | Change |
|---|---|
| Page layouts and structure | Colours (Gruvbox, light + dark) |
| Top bar: hamburger, wordmark, search | Fonts (Courier Prime + Young Serif) |
| Slide-out sidebar: same links, order and icons | Corner radius (square) |
| All icons. They're inline SVGs in `currentColor`, so they recolour automatically. | Borders (strong 1px) |
| Library tabs, book grid, cards, badges, buttons, FAB, forms | Shadows (none, or a hard offset) |

A few small bug fixes ride along (0.6). They fix how existing elements behave; they don't add or remove anything.

### 0.1 Before you start
- [x] **Phil commits the 2026-10-28 security pass** (plus the README/screenshot/roadmap changes) once it's complete. Start the refresh from that commit, so it's its own reviewable diff.
- [x] The "before" screenshots are in `docs/screenshots/` (2026-11-02). Use them for the side-by-side check in 0.7.

### 0.2 Colours: Gruvbox, light and dark
- [x] Define the colours as CSS variables in `static/styles.css`. Light values go in `:root`, dark values in `@media (prefers-color-scheme: dark)`, so the app **follows the system** like philcifone.com.
- [x] Store each variable as RGB channels (`--paper: 29 32 33`) and point Tailwind at `rgb(var(--paper) / <alpha-value>)`. Then opacity modifiers like the sidebar's `hover:bg-primary/20` keep working.
- [x] Point the existing Tailwind names at the variables. Also override Tailwind's default `white`, `gray`, `red`, `yellow`, `green` and `blue` (only the shades below are used), so ~600 class uses follow the theme without template edits:

| Tailwind name | Used for | Light | Dark |
|---|---|---|---|
| `primary`, `primary-bg` | page background | `#fbf8f1` | `#1d2021` |
| `secondary` | top bar, sidebar, cards | `#f2ede1` | `#282828` |
| `primary-hover`, `gray-700` | inputs, hover fills | `#ebdbb2` | `#3c3836` |
| new `rule` (+ `gray-600`) | hairline dividers | `#d5c4a1` | `#504945` |
| new `rule-strong` | card, input, button and tab borders | `#3c3836` | `#7c6f64` |
| `accent` | links, primary buttons, active tab | `#79740e` | `#98971a` |
| `accent-hover` | hover | `#98971a` | `#b8bb26` |
| new `on-accent` | text on accent/red fills | `#fbf8f1` | `#1d2021` |
| `content-primary`, `white` | main text | `#282828` | `#ebdbb2` |
| `content-secondary` | secondary text | `#3c3836` | `#d5c4a1` |
| new `muted`, `gray-400` | labels, metadata | `#5a524c` | `#a89984` |
| `content-tertiary` 🆕 (used 3×, **never defined**, so that text gets no colour of its own) | faint text | `#7c6f64` | `#928374` |
| `red-*` | delete, errors | `#9d0006` / `#cc241d` | `#fb4934` / `#cc241d` |
| `yellow-*` | stars, warnings | `#b57614` | `#fabd2f` |
| `green-*` | status | `#79740e` | `#b8bb26` |
| `blue-600` | "Edit" links | `#076678` | `#83a598` |

- [x] **Text on coloured buttons:** today it's `text-white` / `text-content-primary`. Once `white` follows the theme, that text would be dark-on-green in light mode and light-on-green in dark mode, and the dark-mode version fails contrast (about 2.2:1). Switch text on accent and red fills to `text-on-accent` (about 4.6:1 light, 5.3:1 dark). This is the one template-wide find-and-replace in this phase.
- [x] Replace the 10 hard-coded greens (`#4f7d19` ×8, `#6a9839` ×2) and their `onmouseover` swaps, mostly in `user.html`, with `bg-accent hover:bg-accent-hover`. Otherwise they ignore the theme.
- [x] Check `no-cover.png` and the wishlist/feed cover placeholders on the light background. *(2026-11-02: the grid and detail page use a themed text placeholder, which is fine in both modes. The wishlist's white "image not available" tiles are saved placeholder images, see 3.2. `no-cover.png` itself is a watermarked Depositphotos stock photo; replacement added to 3.2.)*
- [x] **No toggle for now.** The theme follows the system. A manual toggle would be a new sidebar element, so it waits for Phase 7. *(Superseded 2026-11-02: Profile → Appearance now has Style and Mode settings; see Phase 7.)*

### 0.3 Fonts: Courier Prime first
- [x] Add **Courier Prime** 400, 700 and 400 italic to `static/fonts/` (OFL licence) with `@font-face` in `styles.css`. The italic is for the "by Author" lines. Young Serif is already there.
- [x] **Make Courier Prime the default font** by pointing `font-primary` (today Outfit) at it. That switches nearly all text at once: sidebar, tabs, buttons, labels, inputs, card titles, author lines, metadata, counts, descriptions and reviews.
- [x] **Keep Young Serif** (`font-display`, 40 uses) for the wordmark, page headings ("Activity Feed", "Reading Shelves") and the big title on the book detail page. That's the same split as the sites: serif headlines, typewriter for everything else.
- [x] **Judge the long text by eye.** *(Phil, 2026-11-02: paragraphs read fine, no change.)* Descriptions and reviews in Courier Prime are the sites' voice, but monospace paragraphs run wide. Cap them at about `66ch`. If they still feel heavy, switch just those two blocks to Young Serif.
- [x] **Weights:** Courier Prime only has 400 and 700, so `font-medium` (127 uses) renders as 400 and `font-semibold` (53) as 700. That's fine, but check that headings and card titles still read as intended. Courier is also wider than Outfit, so check that grid titles, tabs and buttons don't wrap or overflow. Drop a size step where needed.
- [x] Remove **Outfit** and **Crimson Pro**: the `@font-face` rules, the files in `static/fonts/`, and the two `@fontsource-variable/*` npm deps. No template links them directly. The wordmark keeps its text and spacing, in Young Serif.

### 0.4 Corners, borders, shadows
- [x] **Square corners:** in `tailwind.config.js`, **replace** (not `extend`) `borderRadius` so every size is `0`. That squares off all ~384 `rounded-*` uses at once. Keep `full` for avatars and any status dots.
- [x] **Strong borders:** cards are `bg-secondary` boxes with no outline today. Add `border border-rule-strong` to the ~94 `bg-secondary` / `bg-secondary-bg` containers. It's a mechanical find-and-replace, then a by-eye check. Use the same 1px strong border on inputs, buttons, tabs, the top bar's bottom edge and the sidebar's edge. Use `rule` (lighter) for dividers *inside* cards.
- [x] **Shadows:** replace `boxShadow` the same way. The soft blurs (`shadow-sm` … `shadow-xl`, 94 uses) become `none`. Only the FAB, dropdowns and modals get the sites' hard offset: `4px 4px 0` in the text colour.
- [x] **Focus:** a global `2px solid` accent outline, offset `3px`, on links, buttons and inputs.

### 0.5 Styling details (same elements, new look)
- [x] **Sidebar and tabs:** the same links, icons and order. The active item gets accent text and a 2px accent **underline** (philcifone.com style) instead of the current filled background.
- [x] **Links:** accent with a 1px underline offset `.2em`, 2px on hover.
- [x] **Labels** (`PUBLISHER`, `ISBN`, form labels; most are already uppercase): Courier Prime, `letter-spacing: .08em`, muted colour, a `rule` hairline underneath. One utility class in `styles.css`.
- [x] **Badges** (the shelf counts): kept, now square and in Courier Prime.
- [x] **Buttons and the FAB:** the same buttons. Square, 1px border, Courier Prime label; the FAB keeps its spot and gets the hard shadow.

### 0.6 Small bug fixes while in there (no element changes)
- [x] **Covers cropped in the grid:** `object-cover` cuts off the tops of covers (*11/22/63*, *Alaska*, *Anthem*). Keep the same card size, but fit the whole cover inside it (`object-contain` on the card fill).
- [x] **The FAB covers the last card's author line** on mobile. Add bottom padding to the grid.
- [x] **Library tabs wrap onto two lines** on a phone. Tighten the padding and text size so they fit on one line.
- [x] **Viewport:** `initial-scale=.8` → `1` in the 19 templates (a one-line `sed`). Otherwise the new type is judged at the wrong size on phones.

### 0.7 Build and check
- [x] `npm run build:css`, and commit `static/css/output.css`.
- [x] Click through every page in **light and dark**, at phone and desktop widths, side by side with the 2026-11-02 screenshots:
  - library, shared and friends' libraries
  - detail, add, edit
  - rate/review, collections, profile
  - wishlist, feed, notifications
  - admin, login/register, Goodreads import
- [ ] Retake the README screenshots in both themes, from an **anonymised copy** of the DB (rename other users, clear their emails/bios/avatars/review text), never the live one. *(Deferred 2026-11-02: Phil will retake them after Phase 8, once the app is fully presentable.)*

**Status 2026-11-02:** landed on branch `phase-0-design-refresh` (commit `35c2b13`). Headless screenshots of every page in light + dark looked right. Phil's phone pass is done (2026-11-02). Still open: the `no-cover.png` / long-text checks; the README screenshots are deferred to after Phase 8. Deviations from the token table, made for contrast: light `accent-hover` is `#5f5b0b` (`#98971a` under light text is 2.9:1) and dark `red-strong` is `#fb4934` (`#cc241d` under dark text is 3.0:1). Phone tab labels shorten to "Shared" / "Friends'" so they fit on one line.

**Done when:**
- Every page renders in both themes with Courier Prime + Young Serif, square corners, strong 1px borders and no soft shadows.
- Every element from the old screenshots is still there, in the same place.
- Text on accent and red buttons passes 4.5:1 in both themes.
- Nothing references Outfit/Crimson.
- The README screenshots are retaken.

**Not in this phase (→ Phase 7):** a manual theme toggle, film-frame "contact sheet" covers, page layout changes, the styled confirm modal, the a11y sweep.

---

## Phase 1: Prod upkeep

**Context:** prod is only reachable through a **Cloudflare tunnel with Cloudflare Access** (2FA, and only 2–3 allowlisted emails can get a code). Open registration and the dependency CVEs can't be reached by strangers today, so this phase is upkeep. One part still matters before Phase 2: knowing which DB file prod opens. Backups are already covered by daily ZFS snapshots.

**Goal:** a known prod DB path and no known-vulnerable dependencies, so things stay safe if Access is ever loosened.

### 1.1 Production `.env` (no code changes) 🟠

**Deploying this branch to prod (order matters):** prod needs the new code first, since `requirements.txt` and `migrations/013_add_theme_preferences.sql` only exist on `phase-0-design-refresh`. Merge it into `main` and push, then on prod:
1. Optional: take a manual ZFS snapshot.
2. `git pull`
3. `pip install -r requirements.txt` in prod's venv.
4. `sqlite3 <prod DB path> < migrations/013_add_theme_preferences.sql` (find the path first, see below). Without it, pages still load with the default theme, but saving Profile → Appearance fails.
5. Check `.env` (the items below), then restart gunicorn.

- [x] **Close self-registration:** `ALLOW_REGISTRATION=False`. Only Access-approved people can reach the site today, so this is defence in depth. 🟢
- [x] **Rate limiting behind the tunnel:** every request reaches gunicorn from `cloudflared` on localhost, so all users share **one IP** for rate limiting. That includes the global 50/hour default (see Phase 4), so one busy browsing session can 429 everyone. Set `TRUSTED_PROXY_COUNT=1` so the limiter uses the client IP that Cloudflare forwards in `X-Forwarded-For`, then confirm it in the logs. (`CF-Connecting-IP` is the other option, but it needs a small `key_func` change.)
- [x] **`SECRET_KEY`** is a real random value (`python3 -c "import secrets; print(secrets.token_hex(32))"`), not the `.env.example` placeholder. The app logs a warning if it is.
- [x] **Find out which DB file prod opens.** Run `ls -la` in the gunicorn working dir and grep the prod `.env` / systemd unit for `DATABASE_PATH`. Write the answer down here, because Phase 2.4 depends on it. → *prod DB path:* **`/home/phil/library-catalog/library.db`** (confirmed 2026-11-02). No `DATABASE_PATH` is set in `.env` or the systemd unit `library-catalog.service` (WorkingDirectory `/home/phil/library-catalog`, gunicorn on `:8000`, venv Python 3.12.3), so the `library.db` default applies. The `DATABASE_URI` line in prod's `.env` is read by nothing. `library-prod.db`, `libaraxia.db` and `library.db.backup-20251104` in that dir are leftovers; review them in Phase 2.6 before deleting. Optional: pin it explicitly with `Environment=DATABASE_PATH=...` via `systemctl edit library-catalog`.
- [x] **Backups:** prod runs in a Linux container on Proxmox, with a daily ZFS backup job. Snapshots can be rolled back from the Proxmox UI or with `zfs rollback`, and SQLite restores cleanly from them. Optional: take a manual snapshot right before Phase 2's first migration, so the rollback point is minutes old rather than up to a day.

### 1.2 Upgrade dependencies 🟠
`requirements.txt` pins are from late 2024 and several have published CVEs. Cloudflare Access keeps outsiders from reaching them today. Still, do it before the next release tag.

| Package | Pinned | Upgrade to at least | Why |
|---|---|---|---|
| gunicorn | 21.2.0 | 23.0.0 | HTTP request smuggling (CVE-2024-1135, CVE-2024-6827) |
| Jinja2 | 3.1.4 | 3.1.6 | sandbox escapes (CVE-2024-56201, CVE-2024-56326, CVE-2025-27516) |
| requests | 2.32.3 | 2.32.4 | `.netrc` credential leak (CVE-2024-47081) |
| urllib3 | 2.2.3 | latest 2.x | redirect/proxy and decompression issues (CVE-2025-50181/50182 and later) |
| pillow | 11.0.0 | 11.3.0+ | heap overflow in DDS handling (CVE-2025-48379) |
| Flask | 3.1.0 | 3.1.1+ | key-rotation signing bug (CVE-2025-47278) |
| Werkzeug | 3.1.3 | latest 3.1.x | routine security fixes |
| Flask-Limiter | 3.5.0 | match the venv (4.1.1) | `requirements.txt` and the venv have drifted |

```bash
pip install -U gunicorn Jinja2 requests urllib3 pillow Flask Werkzeug Flask-Limiter Flask-WTF Flask-Login certifi
pip install pip-audit && pip-audit
pip freeze > requirements.txt   # then hand-trim to direct deps if you prefer
```
- [x] Upgrade, `pip-audit` clean, update `requirements.txt`.
- [x] Manual smoke test: login, library grid, add book by ISBN, edit cover, Goodreads import.
- **2026-11-02:** venv upgraded and `requirements.txt` re-pinned (Flask 3.1.3, Werkzeug 3.1.9, gunicorn 26.2.0, pillow 13.0.0, requests 2.34.2, urllib3 2.8.0, idna 3.20). `pip-audit` reports no known vulnerabilities. The smoke test passed against a copy of the DB; the edit page was only checked for loading, not for a cover change. **Deployed to prod 2026-11-02:** `git pull`, `pip install -r requirements.txt`, migration 013 applied to `library.db`, gunicorn restarted.

### 1.3 Quick production hygiene 🟠
- [x] `app.py` forces `logging.DEBUG`. Use INFO in production.
- [x] Remove the `console.log` of the CSRF token and other debug logs in `add_book.js` / `wishlist.js`.
- [x] Remove debug `print()` statements from `blueprints/collections.py`.

**Done when:** prod `.env` is checked, the prod DB path is recorded above, deps are upgraded, and `pip-audit` reports nothing.

---

## Phase 2: Data foundations

**Goal:** the database can be created, migrated, checked and tested reliably. Everything after this writes migrations, so this layer needs to be solid.

### 2.1 Consolidated schema 🟠
- [x] `create_database.sql` lacks migrations 002, 005 and 007–012, so a fresh install crashes at first registration unless every migration is run by hand (and 001/004/006 throw duplicate-column errors). Regenerate it from a fully migrated DB (`sqlite3 library.db .schema`) and make `docker-entrypoint.sh` use it.
  - **2026-11-02:** rewritten as a clean schema equal to old schema + 001–013 (checked column-by-column, FKs, indexes and CHECKs). It also creates `schema_migrations` with 001–013 marked applied, for the 2.2 runner. A fresh DB from it registers, logs in and adds a book. `docker-entrypoint.sh` already loads it. Prod differs only in leftovers no migration created: `users.theme_mode`/`accent_color`, the `discovered_books` table, and `collections.created_at/updated_at` with no default (2.6).

### 2.2 Migration runner 🟠
- [x] `python3 manage.py migrate` keeps a `schema_migrations(name, applied_at)` ledger and applies each unapplied file in `migrations/` inside a transaction. It **backs up the DB first**.
- [x] A `--baseline` flag marks 001–013 as applied on existing databases (prod is at 013 as of 2026-11-02).
  - **2026-11-02:** `manage.py` has `status`, `migrate [--dry-run] [--baseline] [-y]` and `backup`, plus `--db PATH`. An empty DB is built from `create_database.sql`. A DB with tables but no ledger is refused until `--baseline`, which first checks that `users.theme_style` exists. Each file runs in its own transaction with FKs off and is rolled back on error or new `foreign_key_check` violations. Backups use the online backup API, are integrity-checked and never overwrite each other. `docker-entrypoint.sh` now runs `manage.py migrate --yes`. Tested on scratch copies: fresh, prod copy, idempotent re-run, rollback, triggers.

### 2.3 Referential integrity 🆕 🟠
SQLite only enforces foreign keys when each connection runs `PRAGMA foreign_keys = ON`, and `get_db_connection()` never does. So the schema's `ON DELETE CASCADE` rules have never fired, and deleting a book leaves its rows behind. `PRAGMA foreign_key_check` on `library.db` (2026-11-02) finds **10 orphaned rows**:

| Table | Orphans (book deleted) |
|---|---|
| `read_data` | 3 |
| `collections` | 2 |
| `reading_sessions` | 2 |
| `activity_likes` | 2 |
| `wishlist` | 1 |

Visible symptom: your profile says **131** books read, while the Reading Shelves page says **129**. The profile counts `collections` rows; the shelves page joins to `books`.

- [x] Migration `014_cleanup_orphans.sql`: delete rows that `foreign_key_check` reports (after backup). Books are never deleted: a book or household row whose user is gone gets `added_by = NULL` instead.
- [x] Turn on `PRAGMA foreign_keys = ON` in `get_db_connection()`.
- [x] ⚠️ **Before enabling, review every FK action.** 13 FKs to `users` are `ON DELETE CASCADE`, so deleting a user will now really delete their data. `books.added_by REFERENCES users(id)` has **no** action, so deleting a user who owns books will start *failing* with a constraint error. Decide what admin "delete user" should do with their books (transfer to a household member? `SET NULL`?) and make the code do that first.
- [ ] Add a check to the test suite that `PRAGMA foreign_key_check` is empty after the delete flows. → moved to 2.8 (tests).
- **Decided 2026-11-02** (see 2.7 for the full feature). A book is a *record*; owner and shelf status are attributes of it. Other users' reviews, ratings and reading history must never disappear because a book was removed or its owner left.
  - Migration `015_foreign_key_actions.sql` rebuilds 6 tables so every FK has a deliberate rule: `books.added_by` → `ON DELETE SET NULL` (deleting a user never deletes books); `collections`, `user_collections`, `collection_books` → `CASCADE`; `dismissed_activities` and `activity_likes.activity_user_id` get FKs (they had none). AUTOINCREMENT counters and column order are preserved; `collections` timestamps get their missing default. Adds `idx_books_added_by`.
  - **Hard delete** (`/books/delete`) is refused while any *other* user has a review, status, session, tag, shelf or wishlist entry on the book, so cascades only ever remove the owner's own rows.
  - **Admin delete user** requires a "their books go to" choice (another user, or no owner). Their wishlist-only books are deleted unless someone else has data on them. Everything else of theirs cascades. Minimal form for now; 2.7 replaces it with the full dialog.
  - Fixed while here: `POST /wishlist/remove/<id>` deleted **any** book with no statuses/reviews/tags/shelves, whoever owned it, even if it was never on your wishlist. Now the row is deleted only if it was your own wishlist entry and nobody has other data on it. The activity feed crashed on unowned books among the 20 newest; it now skips them.
  - Tested on a migrated copy: FK check empty after deleting users (transfer and no-owner), a mistaken book, a shared book (refused), a custom collection, wishlist removals; every GET route returns 200/302.

### 2.4 Config / `.env` load order 🟠
- [ ] `config.py` and `utils/database.py` read env vars at import time, before `load_dotenv()`, so `.env` values for `DATABASE_PATH`, `MAIL_*` and `EMAIL_VERIFICATION_REQUIRED` are silently ignored.
- [ ] ⚠️ Use the prod DB path recorded in Phase 1.1. Moving `load_dotenv()` earlier could switch prod to a different (possibly empty) DB file.
- [ ] Remove the hardcoded `/home/phil/library-catalog/...` paths, the unused `DATABASE_URI`, and the wrong-key `RATELIMIT_STORAGE_URL` from `config.py`.

### 2.5 DB connection helper 🟢
- [ ] Replace `with get_db_connection() as conn:` (commits but never closes; used in books/wishlist) with a Flask `g`-scoped connection and `teardown_appcontext`. That removes most try/finally boilerplate, and it's the one place the FK pragma lives.

### 2.6 Leftovers 🆕 🟢
- [ ] Drop the `discovered_books` table (Discover tab was removed; no code references it) and the `allow_friend_discovery` column. Do it in a migration, after backup.
- [ ] Delete the stray DB files in the repo root once you've confirmed prod doesn't use them: `libaraxia.db` (Oct 2025, 20 KB), `instance/library.db` (Oct 2025), `library.db.backup_20251018_191333`. They're git-ignored, but they're the "which DB is this?" trap from 2.4.

### 2.7 Ownership & removal 🆕 🟠
Decided 2026-11-02. The book row is a permanent *record*; who owns the copy and whether it is still on the shelf are attributes that change. Reviews and reading history hang on the record, so they survive both.
- [ ] **Deaccession instead of delete.** Migration adds `books.removed_at` and `books.removed_note` (e.g. "Little Free Library"). "Remove from library" on the book page asks for an optional note. Library grids, shared library, counts and stats-of-owned-books hide removed books; a "Show removed" filter brings them back. The book page says "Removed from the library on DATE (note)" and keeps reviews, sessions and history. Owner or admin can restore it.
- [ ] **Hard delete stays for mistakes** (duplicates, bad scans). Allowed only when no other user has data on the book (done in 2.3); otherwise the page offers Remove instead, and says why.
- [ ] **Unowned books (admin).** An admin page listing books with `added_by IS NULL`, with a reassign dropdown per book and "reassign all to…". Admin transfer may target any user (owners can still only give books to household members). Today unowned books show up in no library, because every library view filters by owner.
- [ ] **Account deletion dialog** for admin delete and a new self-delete (Profile → Account). A modal explains what happens, with:
  - **Deactivate (keep everything):** can't log in; reviews, history and books stay. Reversible. The gentle option, e.g. after a death.
  - **Delete permanently:** a "their books go to" dropdown (household members first, then other users for admins, then *No owner*), the list of what is deleted (reviews, reading history, shelves, wishlist, friendships, notifications), an **Export my data** button, and Proceed / Cancel. Self-delete asks for the password. The last admin can't be deleted.
- [ ] **Fuller export.** `/user/export_library` gains review text, all reading sessions, tags, custom shelves and the wishlist (CSV for the library; a ZIP with one CSV per table for "export my data").
- Future model (not now): books owned by the household (`library_id`) rather than a user. Noted in FORK-SPEC.md §9.

### 2.8 Smoke tests + CI 🟠
- [ ] A small pytest suite using `app.test_client()` against a temp DB built by the migration runner. Cover:
  - register/login
  - add/edit/delete book
  - ownership checks
  - the 2026-10-28 security fixes (unsafe cover paths, SSRF guard, POST-only delete)
  - FK check after deletes
  - every blueprint returning 200/302
- [ ] CI (`.github/workflows/basic-tests.yml`):
  - bump `actions/checkout@v4`, `actions/setup-python@v5`, Python 3.11+
  - exclude `./venv` from `py_compile`
  - add `python -c "from app import create_app; create_app()"`
  - run pytest

**Done when:** `sqlite3 new.db < create_database.sql` gives a working app; `manage.py migrate` is idempotent; `foreign_key_check` is empty; tests run green in CI.

---

## Phase 3: Data correctness

**Goal:** fix what the screenshots and queries show is wrong today.

### 3.1 Stats count the whole database 🆕 🔴
`user.py` stats divide "books you've read" by `SELECT COUNT(DISTINCT id) FROM books`, which is **every** row: all users' books *plus wishlist entries* (see 3.3). Today that's 131 / 415 instead of 131 out of your 155-book library. `calculate_library_stats()` has the same problem for total pages, unique authors, longest book and most common genre.
- [ ] Scope every stats query to the user's library (`added_by = ?`, or household members for the shared view) and exclude wishlist-only books.
- [ ] Same scoping for `get_filter_options` in `base.py`, which lists every user's genres and tags. Merge it with the duplicate in `utils/book_utils.py`; the two return different shapes.

### 3.2 Placeholder covers saved as real covers 🆕 🟠
**111 of 415 books (27%)** point at one of two placeholder images that were downloaded and saved as if they were covers:
- 95 files are Google's grey "image not available" JPEG.
- 27 are a generic grey book-outline image.

They show in the grid (see the library screenshot), count as "has a cover" so bulk fetch skips them, and waste disk space.
- [ ] **Detect at download:** in `download_and_save_cover` / `_fetch_image`, reject known placeholder hashes (keep a small set of SHA-256s in `book_utils`), and request Open Library covers with `?default=false` so a miss is a 404, not a placeholder.
- [ ] **One-off cleanup** (script or admin button): for books whose cover file hashes to a placeholder, set `cover_image_url = NULL`, remove the files via `delete_image_file()`, then rerun the admin bulk cover fetch.
- [ ] Use the existing `no-cover.png` / an empty state for books with no cover, not a white tile.
- [ ] **Replace `static/no-cover.png`:** it's a stock photo with a visible Depositphotos watermark (not licensed for use). It's only the JS fallback in `add_book.js` / `wishlist.js` (and the admin orphaned-images page) when a cover fails to load. Swap it for the same themed "No Image Available" text box the grid uses (CSS, no image), or a small in-house SVG.

### 3.3 Wishlist books live in the `books` table 🆕 🟠
A wishlist entry is a full `books` row plus a `wishlist` row. Today that's **260 of 415** rows. The library grid keeps them out with `AND NOT EXISTS (SELECT 1 FROM wishlist ...)`, so every query that forgets this clause leaks wishlist books (3.1 is one example).
- [ ] Decide the model:
  - (a) add `books.in_library` (or `status`), set on "move to library", and filter on it; or
  - (b) keep the `NOT EXISTS` approach, but put it in one helper/view (`library_books`) that every query uses.

  (a) is simpler to reason about.
- [ ] Wishlist duplicates: the same title is wishlisted as different editions (e.g. *Les Misérables* ×2, *Heretics of Dune* ×2, *Chapterhouse: Dune* ×2). Warn on title+author match when adding, not just ISBN.

### 3.4 Goodreads HTML in existing reviews 🆕 🟠
- [ ] **27 of your reviews** contain literal `<br>` / HTML from the Goodreads import, which shows up raw in the review editor. Write a one-off cleanup (`<br>` → newline, unescape entities, strip other tags) and fix the importer (Phase 5).

### 3.5 Error handling 🟠
- [ ] Stop returning `str(e)` to the browser: `books.fetch_cover`, `books.select_search_result`, the collections routes, `user.import_goodreads`, the user stats route. Log it and return a generic message.

**Done when:** profile stats match the shelves page and only count your own books; no placeholder covers remain; no raw HTML in reviews; wishlist books can't leak into library queries.

---

## Phase 4: Access & privacy

**Goal:** every page has a decided access rule, enforced in SQL.

- [ ] **Book detail access** 🟠: `/books/book/<id>` shows any book to any logged-in user, and it picks *any* user's wishlist entry (notes included) and friend reviews to display. Decide the rule (owner + household + friends?) and enforce it.
- [ ] **Privacy model** 🟠: the `privacy` columns (migration 012) and `models.can_view_content()` exist, but nothing calls them; everything is friends-or-nothing. Either wire them in with a settings UI (profile, wishlist, collections, sessions, feed), or drop the columns and the claim.
- [ ] **Household consent** 🟠: `user.add_to_shared_library` lets a friend add you to their household without asking. Make it an invite/accept flow, reusing `friend_requests` + `notifications`. Also, any member can currently remove any other member, **including the owner**. Restrict removal to the owner (or self-removal).
- [ ] **Email change needs the password** 🟠 (`user.update_email`): a hijacked session can take over the account's email. Require the current password, and re-verify the new address if verification is on.
- [ ] **Logout is a GET** 🟢: make it a POST form in `_sidebar.html`.
- [ ] **Rate limiter** 🟠:
  - Storage is `memory://` per gunicorn worker, so limits multiply by the worker count.
  - The global default of **50 requests/hour per IP** on every route is tight for infinite scroll and the feed. It's the likely cause of mystery 429s.
  - Fix: raise or remove the global default and keep strict per-route limits on auth/imports, or point storage at Redis.
- [ ] **Quagga** 🟢: `add_book.html` and `wishlist.html` load it from cdnjs without `integrity=`. Vendor it into `static/`, or pin it with SRI.

**Done when:** there's a written access rule per page type (put it in CLAUDE.md's "Access Model"), and tests assert it.

---

## Phase 5: Finish the Goodreads import

`blueprints/user.py` `import_goodreads`, `templates/goodreads_import.html`. What works today: matching by ISBN13/ISBN, then title+author; `to-read` → wishlist; `read` / `currently-reading` → collections + rating/review + one reading session.

- [ ] **Shelves** → map custom shelves (the comma-separated `Bookshelves` column) to **tags** or **custom collections**. Today a multi-shelf value never matches and is counted as "unknown shelf".
- [ ] **DNF:** map a "did-not-finish"-style shelf to the `did not finish` status.
- [ ] **Clean HTML** in reviews (`<br/>`, entities) on the way in. See 3.4 for existing data.
- [ ] **Reviews without a rating** are dropped. Import them, and import ratings for `to-read` books if present.
- [ ] **Read Count** → multiple reading sessions (today only one).
- [ ] **Unused columns:** Additional Authors, Private Notes, Owned Copies, Binding.
- [ ] **Per-row SAVEPOINT**, so a failing row doesn't leave half its data behind.
- [ ] **Empty values:** store empty year/pages as NULL, not `''`. Don't write a NULL `created_at` when Date Added is missing (it breaks feed ordering).
- [ ] **Report wishlist duplicates**; they're currently skipped silently.
- [ ] **Encoding and file checks:** try `utf-8-sig`, fall back to `latin-1`; case-insensitive `.csv` check.
- [ ] **Covers:** optionally queue a cover fetch for new books, reusing the bulk-fetch logic and the placeholder check from 3.2.
- [ ] **Large files:** progress indicator or chunked processing.
- [ ] Update the "Please Note" box on the import page to match what the import now actually does.

**Done when:** your own `goodreads_library_export.csv` re-imports into a fresh DB with shelves, DNF, multi-reads and clean reviews, and the result screen accounts for every row.

---

## Phase 6: Page structure

**Goal:** one layout, one shared JS file, no giant inline scripts. That makes the Phase 7 polish a mostly-one-file job and enables a real CSP.

- [ ] **`templates/base.html`** with `{% block title %}`, `{% block content %}` and `{% block scripts %}`, `<html lang="en">`, one `<meta name="csrf-token">`, and the sidebar/flash includes. Move the 27 standalone pages onto it one at a time.
- [ ] **`static/common.js`** with `getCSRFToken`, `escapeHtml` and `showFlashMessage`. Today the CSRF helper is copy-pasted into 5 JS files.
- [ ] **Move large inline scripts into `static/`:** `user.html` (~540 lines), `admin_settings.html` (~270), `rate_review.html`, `goodreads_import.html`, `book_detail.html`.
- [ ] **Named row access in templates:** replace `book[0]`, `book[8]` with names, so adding columns (VHS in Phase 8) can't break pages.
- [ ] **Rebuild Tailwind** (`npm run build:css`). The committed `output.css` is from Nov 2025, so classes added since may silently not exist.
- [ ] **Content-Security-Policy**, once the inline scripts are gone (no `'unsafe-inline'`).

**Done when:** every page extends `base.html`; no inline `<script>` over ~20 lines remains; CSP is on without `'unsafe-inline'`; smoke tests pass.

---

## Phase 7: Design polish

**Goal:** finish what the Phase 0 refresh deliberately left out, now that every page extends `base.html` (Phase 6) and edits happen in one place. Phase 0 is the house-style reference.

### 7.1 Finish the house style
- [x] **Theme toggle** (done early, 2026-11-02): Profile → Appearance has **Style** (House = Gruvbox/square/bold lines, Classic = the original 2024 look, with a new light version) and **Mode** (System/Light/Dark), saved per user (migration 013). Styles are CSS-variable sets on `<html data-style data-mode>`. To add a style: one shape block and a light + dark palette in `static/styles.css`, plus a line in `THEME_STYLES` in `models.py`.
- [ ] Optional: a quick sidebar shortcut for Mode, so it doesn't need a trip to the profile.
- [x] ~~Delete the now-inert `rounded-*` / `shadow-*` classes from templates and `static/*.js` page by page. Decide whether avatars go square (framed like photos).~~ **Won't do (2026-11-02):** these classes now drive the Classic style, so they must stay.
- [ ] **Film-frame covers:** a `--film` border with a mono "edge" caption under the cover (`▸ 9780670671908`), contact-sheet style.
- [ ] Remaining details from the sites:
  - zero-padded numbered markers (`01 — TITLE`)
  - `→` for internal links, `↗` for external
  - `--measure: 66ch` for review and description text

### 7.2 Page fixes seen in the 2026-11-02 screenshots 🆕
- [ ] **Book detail on mobile:** the 3-column metadata grid collapses to 2 with awkward wrapping ("Dial Press Trade / Paperback"). Use one column on narrow screens.
- [ ] **Profile card on desktop:** the avatar and title float above a two-column field list. Tighten it into a header row.

### 7.3 Quick wins and accessibility
- [ ] Replace `alert()` / `confirm()` with the toast and a small styled confirm modal.
- [ ] Cover loading skeletons; consistent no-cover styling (pairs with 3.2). Today it's a "No Image Available" text box (grid, detail, friend library, wishlists, rate/review), a book icon (feed, profile), and omitted (collections thumbnails). Make one `_no_cover.html` partial and use it everywhere; Phil to pick text or icon.
- [ ] Collections shelves as horizontal scroll-snap rows.
- [ ] Book detail: larger framed cover, tidy metadata grid, reviews as cards, smoother "read more".
- [ ] Empty states for an empty library, wishlist, feed and search.
- [ ] Stats: a small reading-over-time chart on the profile (after 3.1 fixes the numbers).
- [ ] Accessibility:
  - `<html lang="en">` everywhere (free with `base.html`)
  - labels/`aria-label` on form inputs and icon-only buttons
  - check focus styles from 0.5 on every page

**Done when:** `grep -rE "rounded-(sm|md|lg|xl|2xl|3xl)|\brounded\b" templates static/*.js` is empty; light and dark both render correctly at phone and desktop widths; screenshots are retaken in both themes.

---

## Phase 8: VHS / UPC support

A core Libaraxia feature. The design notes were written alongside the fork plan, in [FORK-SPEC §5](FORK-SPEC.md#5-phase-2-core-change-b-vhs-support), but nothing here needs the fork.

### 8.0 Fix the barcode scanner first 🆕
Reported by Phil (2026-11-02): it often takes the barcode too early (wrong number), seems to work with only one camera, and is generally flaky. VHS scanning builds on this, so fix it before the rest of the phase. The scanner code is duplicated in `add_book.js` and `wishlist.js`; fix it once in a shared module (ideally `common.js` from Phase 6) and use it from both.
- [ ] **Misreads (takes the code too early):** `onDetected` accepts the very first frame whose code is 10 or 13 digits, with no checksum and no confirmation. Validate the EAN/ISBN check digit, and only accept a code after it's read the same way on several frames in a row (e.g. 3), or reject reads whose average decoder error is high.
- [ ] **Only one camera:** the stream is hard-coded to `facingMode: "environment"` at 640×480. Add a camera picker (`enumerateDevices()`, select by `deviceId`, remember the choice in `localStorage`) and fall back cleanly on devices without a back camera (laptops, desktops). On phones with several back lenses (wide/ultra-wide/macro), the default can be one that won't focus up close, so the picker matters there too.
- [ ] **Resolution/focus:** ask for a higher resolution (e.g. 1280×720 ideal) and continuous autofocus where supported; 640×480 is too coarse for small barcodes.
- [ ] **Camera not released:** `stopScanner()` only calls `Quagga.stop()` when `Quagga.initialized` is true, which isn't a Quagga API property. Check whether the camera light stays on after a scan or when switching tabs, and stop the stream unconditionally.
- [ ] **Swap Quagga 0.12.1 for `@ericblade/quagga2`** (the maintained fork), vendored into `static/` (this also covers the Phase 4 SRI item). Or evaluate the browser's native `BarcodeDetector` where available, with quagga2 as the fallback.
- [ ] **UPC-A is rejected:** the code-format check only allows 10 or 13 digits, so 12-digit UPC-A (most VHS tapes) is dropped silently. Needed for the scanner dispatch below.
- [ ] **Feedback:** a visible target box, a beep/vibrate on a confirmed read, and a styled error instead of `alert()` (pairs with Phase 7).
- [ ] Test on Phil's phone(s) and at least one laptop webcam, over HTTPS.

- [ ] **Scanner dispatch:** an EAN-13 starting `978`/`979`, or a valid ISBN-10, takes the book path; any other UPC/EAN takes the media path. Store UPC-A as EAN-13.
- [ ] **Migration** `NNN_add_media_type.sql`: `media_type`, `barcode`, `catalog_number`, `runtime_minutes` on `books`, appended at the end; indexes; folded into `create_database.sql`.
- [ ] **Field labels by media type** in one place (`utils/media.py`).
- [ ] **Lookups** (`utils/media_lookup.py`): UPCitemdb → title cleanup → TMDb; Discogs for music video. Keys optional. All requests go through the SSRF guard. Manual entry is the primary path.
- [ ] **Routes/UI:**
  - `fetch_barcode_details` (keep `fetch_isbn_details` as an alias)
  - media-type selector on the add form
  - duplicate check on `barcode`
  - `media_type` filter and a `VHS` badge in the grid
  - VHS fields on the detail/edit pages
  - wishlist scanner dispatch
- [ ] Stats that sum pages ignore non-book rows. Goodreads import stays book-only.

**Done when:** scanning a retail VHS fills the form or opens it pre-set to VHS with the barcode; a saved VHS shows with a badge, filters correctly, and shows runtime/studio/barcode; book flows are unchanged (tests).

---

## Phase 9: The archive fork (parked)

**Not planned yet.** It's listed so the idea isn't lost; nothing in Phases 0–8 depends on it. The plan is in [FORK-SPEC.md](FORK-SPEC.md). In short:
1. Tag `v2.0.0` and create the fork repo with an `upstream` remote.
2. Turn off the social layer by config and rebrand.
3. Archival data model: accessioning, condition, provenance, locations, audit log.
4. Exports, labels and BagIt backups.

If it's picked up, start with fork prep in core Libaraxia:
- [ ] Resolve the open decisions in [FORK-SPEC §9](FORK-SPEC.md#9-open-decisions): name, users, accession format, theme default, …
- [ ] **Feature flags** (`FEATURES` in config, `{% if features.social %}` in templates) and a **plugin hook** in `create_app()` ([FORK-SPEC §3.2–3.3](FORK-SPEC.md#32-feature-flags)). Libaraxia ships with everything on.
- [ ] Migration naming for two streams: upstream `NNN_name.sql`, fork `A_NNN_name.sql`, one shared ledger.

---

## Not planned

- **Docker** is reference-only, since prod runs gunicorn directly. If it's ever revived:
  - move off `python:3.11-slim-bullseye` (Debian 11 is EOL)
  - add a non-root `USER`
  - drop `gcc`
  - use `--log-level info`
  - use the consolidated schema from Phase 2.1

---

## Done

### 2026-11-02: README + screenshots, roadmap
- [x] README rewritten: current features, gunicorn install with migrations, env var table, 12 screenshots in `docs/screenshots/` (WebP) taken from an anonymised DB copy.
- [x] Old dev diary and to-do list moved verbatim to `docs/DEVLOG.md`.
- [x] `ACTION_ITEMS.md` folded into this roadmap; new findings from the screenshot/data pass added (🆕).
- [x] Design refresh added as Phase 0 (match philcifone.com / negativeearth.net); the old restyle phase split into Phase 0 (refresh) and Phase 7 (polish).

### 2026-10-28: security pass + housekeeping
**Security fixes**
- [x] **Critical:** arbitrary file deletion via cover paths. Hidden form fields (`existing_cover_url`, `fetched_cover_url`) were stored unchecked and later passed to `os.remove`, so a user could delete `library.db`. Added `utils/image_utils.is_safe_upload_path()`, used it in `process_image` and `edit_book`, and `delete_image_file` now refuses anything outside `static/uploads/`.
- [x] **SSRF:** cover downloads from client-supplied URLs could reach localhost/LAN. `book_utils._fetch_image` now only fetches public hosts, checking every redirect hop.
- [x] **Stored XSS:**
  - Usernames are restricted to `[A-Za-z0-9_.-]{3,30}` (register, rename, admin create).
  - User-search results are escaped.
  - `confirm()` handlers and Jinja-in-JS use `|tojson`.
  - `escapeHtml` now escapes quotes and covers cover URLs, filter pills, wishlist cards, tags and flash messages.
- [x] Book delete is POST-only with a CSRF token (was a GET link).
- [x] `manage_book_collections` checks that the collection belongs to you.
- [x] Book transfer is owner/admin only. Adding a friend to your shared library no longer silently removes them from theirs.
- [x] Security headers (`nosniff`, `X-Frame-Options`, `Referrer-Policy`). Dev server debug follows config instead of always-on.
- [x] New opt-in env vars `ALLOW_REGISTRATION` and `TRUSTED_PROXY_COUNT`; placeholder `SECRET_KEY` warning.

**Housekeeping**
- [x] Untracked `node_modules/` and `.claude/init` from git (files kept locally); fixed the broken last line of `.gitignore`.
- [x] Moved old AI summaries and one-off scripts to `docs/archive/`; useful docs to `docs/`.
- [x] Deleted unused `static/notifications.js` (had an XSS sink, called a missing route) and `static/notification_badge.js`.
- [x] Removed unused Python deps (SQLAlchemy, Flask-SQLAlchemy, greenlet, Mako, Markdown, Cython, asarPy, Flask-Bcrypt) and unused imports.
- [x] Fixed the Goodreads import result screen (showed "Error" on success; now shows counts, warnings and row errors).
- [x] Removed links to the missing `css/fonts.css` (404 on 6 pages); fixed the `w42` icon typo and the `generate-cert.sh` usage hint.
- [x] Added `npm run build:css` / `watch:css`.
- [x] Rewrote CLAUDE.md to match the code.
