# Roadmap

The phased plan for Libaraxia: every open action item, security follow-up and bug found so far, in the order to work through them. This is the **single list of open work**. Tick items (`[x]`) as they land, and move a finished phase to [Done](#done) with a date.

- Assembled **2026-11-02** from the old `ACTION_ITEMS.md` (security audit of 2026-10-28), [FORK-SPEC.md](FORK-SPEC.md) (2026-11-01), and a screenshot/data pass on 2026-11-02 against an anonymised copy of `library.db`.
- **Phases 0–9 are all core Libaraxia work** and don't depend on the fork. The archive fork is parked as Phase 10, a future idea. [FORK-SPEC.md](FORK-SPEC.md) holds the fork plan, and also the original VHS design notes (Phase 8).
- Items marked 🆕 are new findings from 2026-11-02.

Priority key: 🔴 do soon · 🟠 important · 🟢 nice to have

## Phases at a glance

| # | Phase | Why this order | Done when |
|---|---|---|---|
| 0 ✅ | [Design refresh](#phase-0-design-refresh) | Match philcifone.com / negativeearth.net now; everything built later is built in the new look | Same elements, new skin: Gruvbox light + dark, Courier Prime + Young Serif, square corners, strong borders |
| 1 ✅ | [Prod upkeep](#phase-1-prod-upkeep) | Prod sits behind Cloudflare Access (2FA, 2–3 allowlisted emails), so this is upkeep, not an emergency. Do it before Phase 2 touches the DB | Prod DB path recorded, deps upgraded, `pip-audit` clean |
| 2 ✅ | [Data foundations](#phase-2-data-foundations) | Everything later writes migrations and needs tests | Fresh install is one command; migrations tracked; FK check clean; smoke tests in CI |
| 3 ✅ | [Data correctness](#phase-3-data-correctness) | Fix what the data already shows is wrong | Stats, covers, reviews and wishlist behave correctly |
| 4 ✅ | [Access & privacy](#phase-4-access--privacy) | Remaining security follow-ups | Every page has a decided and enforced access rule |
| 5 ✅ | [Finish the Goodreads import](#phase-5-finish-the-goodreads-import) | Self-contained; benefits from Phase 2 tests | A real Goodreads export imports cleanly, shelves included |
| 6 ✅ | [Page structure](#phase-6-page-structure) | One layout, no inline scripts; unlocks CSP | All pages extend `base.html`; CSP on |
| 7 ✅ | [Design polish](#phase-7-design-polish) | Per-page finish once pages share a layout | Component classes, negativeearth shadows, page fixes, a11y, clean phone sweep (theme toggle done early) |
| 8 ✅ | [Physical media: movies and vinyl](#phase-8-physical-media-movies-and-vinyl) | Built in the new style | Movies (VHS, DVD) and vinyl are their own sections: scanned or entered, watched/listened, reviewed and shared, never among the books; one add form and one grid layout for every type |
| 8B | [Music lookups, formats and ownership](#phase-8b-music-lookups-formats-and-ownership) | Follow-ups from using Phase 8; after it has shipped and settled | MusicBrainz finds CDs and tapes; books have a format (Book / Audiobook); you can review something you don't own |
| 8C | [Collections refresh](#phase-8c-collections-refresh) | Collections are still books-only | Status shelves and custom shelves per section (Books / Movies / Music), page heading, side-scrolling rows reused on the profile |
| 8D | [Profile wishlist](#phase-8d-profile-wishlist) | Follows 8C's rows | The profile's wishlist is a side-scrolling row per section instead of one grid |
| 9 (parked) | [More styles](#phase-9-more-styles) | Built on the 7.1 component classes; the Shelf style's video-store rack needs VHS (Phase 8) | Shelf (iBooks-style, with a VHS rack) and Outrun as Appearance choices |
| 10 | [Fork (parked)](#phase-10-the-archive-fork-parked) | Not planned yet; listed so the idea isn't lost | n/a |

Phases 3, 4 and 5 are independent of each other and can be interleaved. The ordering 0 → 1 → 2 → (3, 4, 5) → 6 → 7 → 8 → 8B → 8C → 8D is the part that matters. Phase 9 is parked (Phil, 2026-11-08: an accent colour picker, 8B.5, instead of new styles for now).

**Why the refresh can go first without the `base.html` refactor:** the templates already use *semantic* Tailwind names: `text-content-secondary` ×319, `text-content-primary` ×222, `bg-primary` ×118, `bg-accent`/`text-accent` ×212, `font-display` ×40, plus Tailwind's default `white`, `gray-600/700`, `red`, `yellow`, `green`, `blue` and `shadow-*`. Re-pointing those names in `tailwind.config.js` recolours, re-fonts and squares off nearly every page **without editing templates**. Hand edits are limited to the shared partials, a find-and-replace adding borders to cards, and the text colour on coloured buttons. Per-page cleanup waits for Phase 7, when there's one layout to edit.

## Loose ends

Housekeeping that doesn't belong to a phase and shouldn't hold one open: mostly "wait a bit, then delete". Tick and remove as they're done.

- [x] **Prod:** re-add the tag "nuclear war" to *Cat's Cradle*. It was on an old deleted copy of the book, and migration 014 cleaned it up with the other leftover rows. Done 2026-11-02.
- [ ] **Prod, from about 2026-11-09** (once Phase 2 has run for a few days without trouble):
  - in `/home/phil/library-catalog`, delete `library-prod.db`, `libaraxia.db` and `library.db.backup-20251104` (pre-Phase-2 leftovers nothing opens), and the `library.db.backup-20261102-*` files `manage.py` made during the Phase 2 deploy;
  - ~~delete the manual ZFS snapshot taken before the Phase 2 deploy~~ (done 2026-11-02).
- [x] **Prod: install auto-deploy** (done 2026-11-04; see `deploy/README.md`): one last `git pull`, https remote, sudoers line for the restart, enable `libaraxia-deploy.timer`. Then, once by hand (the pull leaves the timer nothing to do): `manage.py migrate` (018, 019) and restart gunicorn.
- [ ] **Dev machine:** delete the stray DB files in the repo root (all git-ignored, none opened by anything; checked 2026-11-02, see 2.6): `libaraxia.db`, `instance/library.db`, `library.db.backup_20251018_191333`, `library.db.backup_20261102_pre013`.

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

**✅ Done and deployed 2026-11-02.** 2.1–2.7 merged to `main` and deployed to prod: ZFS snapshot, `git pull`, `manage.py migrate --baseline`, then `manage.py migrate` (014–017). Before that, the deploy was rehearsed on a copy of the prod DB, which found that prod's old `collections` table declared its keys as `books(book_id)` / `users(user_id)` (columns that don't exist), so SQLite's FK check failed with "foreign key mismatch". Fixed in the runner (`fk_violations()` checks table by table and skips tables it can't check until a migration rebuilds them) and in 014 (cleans `collections` with a plain query). 014 removed 14 orphaned rows on prod, all pointing at books deleted long ago; the three reviews among them were duplicates of reviews already on the current copies. 2.8 (tests + CI) followed the same day. Leftover files to delete later are under [Loose ends](#loose-ends).

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
- [x] Add a check to the test suite that `PRAGMA foreign_key_check` is empty after the delete flows. (Done in 2.8.)
- **Decided 2026-11-02** (see 2.7 for the full feature). A book is a *record*; owner and shelf status are attributes of it. Other users' reviews, ratings and reading history must never disappear because a book was removed or its owner left.
  - Migration `015_foreign_key_actions.sql` rebuilds 6 tables so every FK has a deliberate rule: `books.added_by` → `ON DELETE SET NULL` (deleting a user never deletes books); `collections`, `user_collections`, `collection_books` → `CASCADE`; `dismissed_activities` and `activity_likes.activity_user_id` get FKs (they had none). AUTOINCREMENT counters and column order are preserved; `collections` timestamps get their missing default. Adds `idx_books_added_by`.
  - **Hard delete** (`/books/delete`) is refused while any *other* user has a review, status, session, tag, shelf or wishlist entry on the book, so cascades only ever remove the owner's own rows.
  - **Admin delete user** requires a "their books go to" choice (another user, or no owner). Their wishlist-only books are deleted unless someone else has data on them. Everything else of theirs cascades. Minimal form for now; 2.7 replaces it with the full dialog.
  - Fixed while here: `POST /wishlist/remove/<id>` deleted **any** book with no statuses/reviews/tags/shelves, whoever owned it, even if it was never on your wishlist. Now the row is deleted only if it was your own wishlist entry and nobody has other data on it. The activity feed crashed on unowned books among the 20 newest; it now skips them.
  - Tested on a migrated copy: FK check empty after deleting users (transfer and no-owner), a mistaken book, a shared book (refused), a custom collection, wishlist removals; every GET route returns 200/302.

### 2.4 Config / `.env` load order 🟠
- [x] `config.py` and `utils/database.py` read env vars at import time, before `load_dotenv()`, so `.env` values for `DATABASE_PATH`, `MAIL_*` and `EMAIL_VERIFICATION_REQUIRED` are silently ignored.
- [x] ⚠️ Use the prod DB path recorded in Phase 1.1. Moving `load_dotenv()` earlier could switch prod to a different (possibly empty) DB file.
- [x] Remove the hardcoded `/home/phil/library-catalog/...` paths, the unused `DATABASE_URI`, and the wrong-key `RATELIMIT_STORAGE_URL` from `config.py`.
  - **2026-11-02:** `app.py` loads `.env` (by absolute path) before importing `config.py`; `database_path()` reads `DATABASE_PATH` per call and resolves a relative path against the project dir, not the cwd. Startup logs the DB path and warns if the file is missing. `config.py` keeps only cookies/mail/verification; `.env.example` drops `DATABASE_URI`/`REDIS_URL` and documents `DATABASE_PATH`, `ALLOW_REGISTRATION`, `TRUSTED_PROXY_COUNT`. Prod opens the same file as before (no `DATABASE_PATH` set; cwd = project dir). **Behaviour change to check on prod:** any `EMAIL_VERIFICATION_REQUIRED` / `MAIL_*` / `DATABASE_PATH` lines in prod's `.env` were ignored until now and will take effect.

### 2.5 DB connection helper 🟢
- [x] Replace `with get_db_connection() as conn:` (commits but never closes; used in books/wishlist) with a Flask `g`-scoped connection and `teardown_appcontext`. That removes most try/finally boilerplate, and it's the one place the FK pragma lives.
  - **2026-11-02:** `utils.database.get_db()` gives each request one connection, closed by `teardown_appcontext` (uncommitted work rolls back); FKs are switched on in `get_db_connection()`, which it uses. All 11 `with` blocks (books ×3, wishlist ×8) converted. Add and edit book relied on the implicit commit and now commit explicitly. Wishlist `except` blocks roll back, so a failed wishlist insert no longer leaves a stray `books` row. The ~85 existing try/finally sites are correct and were left alone; move them to `get_db()` after 2.8 gives them test coverage.

### 2.6 Leftovers 🆕 🟢
- [x] Drop the `discovered_books` table (Discover tab was removed; no code references it) and the `allow_friend_discovery` column. Do it in a migration, after backup.
  - **2026-11-02:** migration `016_drop_legacy.sql` also drops the pre-reskin `users.theme_mode`/`accent_color` (prod only) by rebuilding `users`. After it, a migrated prod copy, a migrated old fresh DB and a new `create_database.sql` DB have identical schemas.
- [x] ~~Delete~~ Check the stray DB files in the repo root (deleting them moved to [Loose ends](#loose-ends)): `libaraxia.db` (Oct 2025, 20 KB), `instance/library.db` (Oct 2025), `library.db.backup_20251018_191333`. They're git-ignored, but they're the "which DB is this?" trap from 2.4.
  - **Checked 2026-11-02 (dev machine), not deleted:** `libaraxia.db` has no `users` table (an empty early schema); `instance/library.db` has 1 user and 1 book (old Docker test); `library.db.backup_20251018_191333` has 5 users and 37 books (a pre-Goodreads-import snapshot). None is opened by anything: the app and `manage.py` resolve `library.db` in the project dir and log the path at startup. Prod's own leftovers (`library-prod.db`, `libaraxia.db`, `library.db.backup-20251104` in `/home/phil/library-catalog`) are covered in the Phase 2 deploy steps. Delete by hand once you're happy.

### 2.7 Ownership & removal 🆕 🟠
Decided 2026-11-02. The book row is a permanent *record*; who owns the copy and whether it is still on the shelf are attributes that change. Reviews and reading history hang on the record, so they survive both.
- [x] **Deaccession instead of delete.** Migration adds `books.removed_at` and `books.removed_note` (e.g. "Little Free Library"). "Remove from library" on the book page asks for an optional note. Library grids, shared library, counts and stats-of-owned-books hide removed books; a "Show removed" filter brings them back. The book page says "Removed from the library on DATE (note)" and keeps reviews, sessions and history. Owner or admin can restore it.
- [x] **Hard delete stays for mistakes** (duplicates, bad scans). Allowed only when no other user has data on the book (done in 2.3); otherwise the page offers Remove instead, and says why.
- [x] **Unowned books (admin).** An admin page listing books with `added_by IS NULL`, with a reassign dropdown per book and "reassign all to…". Admin transfer may target any user (owners can still only give books to household members). Today unowned books show up in no library, because every library view filters by owner.
- [x] **Account deletion dialog** for admin delete and a new self-delete (Profile → Account). A modal explains what happens, with:
  - **Deactivate (keep everything):** can't log in; reviews, history and books stay. Reversible. The gentle option, e.g. after a death.
  - **Delete permanently:** a "their books go to" dropdown (household members first, then other users for admins, then *No owner*), the list of what is deleted (reviews, reading history, shelves, wishlist, friendships, notifications), an **Export my data** button, and Proceed / Cancel. Self-delete asks for the password. The last admin can't be deleted.
- [x] **Fuller export.** `/user/export_library` gains review text, all reading sessions, tags, custom shelves and the wishlist (CSV for the library; a ZIP with one CSV per table for "export my data").
- **2026-11-02, done:** migration `017_book_removal.sql`; `POST /books/remove|restore/<id>`; the book page has a removed banner, Remove / Put Back, and "Delete permanently…" that names who blocks it. My library, shared library, search and friends' libraries hide removed books, with an "Include books removed from the library" filter (and a Removed badge, also on infinite scroll). Admin → Maintenance → **Unowned books** (`/admin/unowned_books`, reassign one or all). Admins can transfer any book to anyone from the book page. `utils/accounts.py` + `templates/_account_removal.html` drive both admin delete (dialog loaded from `/admin/users/<id>/removal`) and self-service Profile → **Account** (`POST /user/delete_account`, password required; users can hand books only to household members). Deactivation now also ends existing sessions and remember-me logins (`load_user` returns no user for inactive accounts). `utils/export.py`: `/user/export_library` is now scoped to *your* books and data (it used to dump every book in the database) and gains owner/removed columns; `/user/export_data` is a ZIP (library, reviews, reading sessions, shelves, wishlist, profile), and admins can pass `?user_id=`.
  - Still on the old rules: profile **stats** count the whole database (3.1), and reading-shelf pages list removed books like any other (on purpose: they're history).
- Future model (not now): books owned by the household (`library_id`) rather than a user. Noted in FORK-SPEC.md §9.

### 2.8 Smoke tests + CI 🟠
- [x] A small pytest suite using `app.test_client()` against a temp DB built by the migration runner. Cover:
  - register/login
  - add/edit/delete book
  - ownership checks
  - the 2026-10-28 security fixes (unsafe cover paths, SSRF guard, POST-only delete)
  - FK check after deletes
  - every blueprint returning 200/302
- [x] CI (`.github/workflows/basic-tests.yml`):
  - bump `actions/checkout@v4`, `actions/setup-python@v5`, Python 3.11+
  - exclude `./venv` from `py_compile`
  - add `python -c "from app import create_app; create_app()"`
  - run pytest

**Done when:** `sqlite3 new.db < create_database.sql` gives a working app; `manage.py migrate` is idempotent; `foreign_key_check` is empty; tests run green in CI.

- **2026-11-02, done:** `tests/` has 73 tests that run in about a second (`pip install -r requirements-dev.txt`, then `pytest`). Every test gets its own copy of a database built by `manage.py migrate` in a temp dir; `library.db` and `.env` are never used, and network calls are blocked.
  - `test_migrations.py`: a fresh DB has every migration and a clean FK check; `create_database.sql` alone gives the same schema as `migrate`; `migrate` is idempotent; a DB without a ledger is refused; a prod-like DB with the broken `collections` keys baselines and migrates (regression); bad migrations roll back; BEGIN/COMMIT is refused.
  - `test_pages.py`: register (first user is admin, bad usernames and short passwords refused), login, deactivated users are logged out, login and admin gates, security headers, **every GET route** loads as an admin with seeded data, and a missing book is a 404.
  - `test_books.py`: add/edit, ownership on edit/remove/delete/transfer, household-only transfer, remove/restore keeps reviews, delete is POST-only and needs CSRF, delete cascades cleanly or is refused while others have reviews, the wishlist-remove fix, unsafe cover paths, and the SSRF guard (private addresses, odd schemes, and a redirect into the LAN).
  - `test_accounts.py`: deactivate, delete with books going to a user or to no owner, reassigning unowned books, wishlist-only books, the last-admin guard, self-delete (password, household-only), exports scoped to one user.
  - CI now installs `requirements-dev.txt`, syntax-checks the tracked `.py` files, checks `create_app()` starts, and runs pytest on Python 3.12 (same as prod).
  - **Found by the suite:** opening a custom shelf (`/collections/collections/<id>/view`) crashed with a template error (`target_username` undefined). Fixed in `view_custom_collection`.

---

## Phase 3: Data correctness

**Goal:** fix what the screenshots and queries show is wrong today.

### 3.1 Stats count the whole database 🆕 🔴
`user.py` stats divide "books you've read" by `SELECT COUNT(DISTINCT id) FROM books`, which is **every** row: all users' books *plus wishlist entries* (see 3.3). Today that's 131 / 415 instead of 131 out of your 155-book library. `calculate_library_stats()` has the same problem for total pages, unique authors, longest book and most common genre.
- [x] Scope every stats query to the user's library (`added_by = ?`, or household members for the shared view) and exclude wishlist-only books.
- [x] Same scoping for `get_filter_options` in `base.py`, which lists every user's genres and tags. Merge it with the duplicate in `utils/book_utils.py`; the two return different shapes.
- **2026-11-04, done:** stats read from the `library_books` view (3.3). *Books Read* now counts the Read shelf (it counted rated/reviewed books), so it matches the shelves page; pages, top genres and top authors follow it. *Read percentage* and the Library tab cover the profile owner's own shelf, not removed books. On the dev copy: 129 read, 134 books, 89.6% (was 131 / 415). One `get_filter_options(owner_ids)` in `book_utils`: genres from the libraries on screen, statuses and tags your own. Also fixed: the *Minimum rating* filter matched the rating exactly instead of "and up".

### 3.2 Placeholder covers saved as real covers 🆕 🟠
**111 of 415 books (27%)** point at one of two placeholder images that were downloaded and saved as if they were covers:
- 95 files are Google's grey "image not available" JPEG.	
- 27 are a generic grey book-outline image.

They show in the grid (see the library screenshot), count as "has a cover" so bulk fetch skips them, and waste disk space.
- [x] **Detect at download:** in `download_and_save_cover` / `_fetch_image`, reject known placeholder hashes (keep a small set of SHA-256s in `book_utils`), and request Open Library covers with `?default=false` so a miss is a 404, not a placeholder.
- [x] **One-off cleanup** (script or admin button): for books whose cover file hashes to a placeholder, set `cover_image_url = NULL`, remove the files via `delete_image_file()`, then rerun the admin bulk cover fetch.
- [x] Use the existing `no-cover.png` / an empty state for books with no cover, not a white tile.
- [x] **Replace `static/no-cover.png`:** it's a stock photo with a visible Depositphotos watermark (not licensed for use). It's only the JS fallback in `add_book.js` / `wishlist.js` (and the admin orphaned-images page) when a cover fails to load. Swap it for the same themed "No Image Available" text box the grid uses (CSS, no image), or a small in-house SVG.
- **2026-11-04, done:** `placeholder_reason()` in `book_utils` rejects a download that is tiny, blank, a wide strip (height under half the width), or a perceptual-hash (dHash) match for the two known placeholders. SHA-256 wasn't used: saved files are re-encoded, so a Pillow upgrade would change the bytes. All Open Library cover URLs use `?default=false`. Admin → Maintenance → **Covers** (`/admin/placeholder_covers`) lists them, clears them (cover set to NULL, unused files deleted) and runs the bulk fetch 10 books per click (50 would hit gunicorn's 30 s timeout). The bulk fetch had routes but no button until now. Dev copy: **142** books (87 Google "image not available", 24 grey outline, 31 strips cut from interior title pages). The grid already showed "No Image Available" for empty covers; the white tiles were the placeholder files. `no-cover.png` replaced by `static/no-cover.svg`.
- [x] **Prod:** Admin → Maintenance → Covers → *Clear*, then *Fetch next 10* until it stops finding covers. Books with no ISBN need a cover search from their edit page. *(2026-11-04: not needed. Prod has no placeholder covers; the 142 on dev came from an old Goodreads import test. The page stays for future imports.)*
- [x] ~~About 6 covers are Google scans of a white title page~~ (dev only, same import test; not worth fixing). with a small publisher logo. They aren't auto-detected (a minimalist white cover would look the same), Left as is.

### 3.3 Wishlist books live in the `books` table 🆕 🟠
A wishlist entry is a full `books` row plus a `wishlist` row. Today that's **260 of 415** rows. The library grid keeps them out with `AND NOT EXISTS (SELECT 1 FROM wishlist ...)`, so every query that forgets this clause leaks wishlist books (3.1 is one example).
- [x] Decide the model:
  - (a) add `books.in_library` (or `status`), set on "move to library", and filter on it; or
  - (b) keep the `NOT EXISTS` approach, but put it in one helper/view (`library_books`) that every query uses.

  (a) is simpler to reason about.

  **Decided 2026-11-04: (b), as a SQL view.** Migration 018 adds `library_books`: books with an owner that aren't the *owner's* own wishlist entry. It's derived from the data, so there is no flag to keep in sync with the wishlist on add, move-to-library, transfer or account deletion (the risk with (a)). Library pages, search, friends' libraries, stats, filter options, the account dialog and admin totals query it. The old clauses disagreed: search hid a book from its owner if *anyone* wishlisted it, and the friends' libraries page counted wishlist entries as books. Removed books stay in the view (filter on `removed_at`). A future table rebuild of `books` or `wishlist` must drop and recreate the view (noted in the migration and `migrations/README.md`).
- [x] Wishlist duplicates: the same title is wishlisted as different editions (e.g. *Les Misérables* ×2, *Heretics of Dune* ×2, *Chapterhouse: Dune* ×2). Warn on title+author match when adding, not just ISBN.
  - **2026-11-04, done:** one `find_duplicates()` in `book_utils` serves both `/books/check_duplicates` and `/wishlist/check_duplicates` (they were near-copies). Matches ISBN (hyphens ignored) or title + author with case, accents, punctuation and a leading "The/A/An" ignored, so *Les Misérables* = *Les Miserables*. Searches the household's shelf and your wishlist only; the wishlist check used to search every user's books. Removed books are flagged as such in the warning.

### 3.4 Goodreads HTML in existing reviews 🆕 🟠
- [x] **27 of your reviews** contain literal `<br>` / HTML from the Goodreads import, which shows up raw in the review editor. Write a one-off cleanup (`<br>` → newline, unescape entities, strip other tags) and fix the importer (Phase 5).
  - **2026-11-04, done:** migration `019_clean_goodreads_reviews.sql` (data only): `<br/>` becomes a newline, so `<br/><br/>` is a paragraph break (reviews render with `pre-wrap`). Only `<br>` tags were in the data, no entities. The importer now stores plain text via `goodreads_review_text()` (breaks, other tags stripped, entities decoded), so this item is off Phase 5's list.

### 3.5 Error handling 🟠
- [x] Stop returning `str(e)` to the browser: `books.fetch_cover`, `books.select_search_result`, the collections routes, `user.import_goodreads`, the user stats route. Log it and return a generic message.
  - **2026-11-04, done:** every `str(e)` sent to the browser (books, wishlist, feed, tags, collections, user, admin) is now logged with its traceback and answered with a generic message. The two account-deletion flashes still show their `AccountError` text on purpose: those messages are written for the user.
- [x] **Removed books (from Phil, 2026-11-04):** after a removal the button does switch to *Put Back in Library*. To list them: the library filter's *Include books removed from the library* checkbox is now a **Removed books** choice: *On the shelf only* (default), *Include removed*, *Removed only*. Books you reviewed but no longer own stay on your Read shelf and in your profile reviews.
- [x] **Transfer ownership is owner/admin only (from Phil, 2026-11-04):** confirmed. The section is inside the owner/admin block on the book page, and `transfer_book` checks again on the server (owners: household only; admins: anyone), covered by `test_non_owner_cannot_edit_remove_delete_or_transfer` and `test_transfer_within_household_only`. Moving it to the edit page is in 7.2.

**Done when:** profile stats match the shelves page and only count your own books; no placeholder covers remain; no raw HTML in reviews; wishlist books can't leak into library queries.

- **2026-11-04:** all done in code on branch `phase-3-data-correctness` (94 tests; new ones in `tests/test_library_data.py`). Left for prod: run migrations 018 and 019 on deploy (see Loose ends). **Phase 3 closed 2026-11-04.**

---

## Phase 4: Access & privacy

**Goal:** every page has a decided access rule, enforced in SQL.

**2026-11-04, done.** The written rule per page type is the table in CLAUDE.md's "Access Model"; `tests/test_access.py` and `tests/test_households.py` assert it (120 tests). Two migrations: 020, 021.

- [x] **Book detail access** 🟠: `/books/book/<id>` showed any book to any logged-in user, and picked *any* user's wishlist entry (notes included) to display.
  - **Rule:** admins, or someone in your *circle* (you, household, friends) owns the book or has data on it (review, status, session, tag, wishlist, collection). Otherwise 404, so ids can't be probed. The "has data" clause keeps your history reachable after a book is given away or its owner deleted, and keeps feed links working (a friend's review of a household member's book).
  - `models.circle_ids` / `models.can_view_book`. The routes that attach your data to a book id (status, review, reading session, tag, custom collection, wishlist quick-add) run the same check first, or attaching data would itself grant access.
  - Other users' wishlist notes on a book page only come from your circle.
- [x] **Privacy model** 🟠: dropped. Every row still had the default `friends` and nothing read the columns. Migration 020 drops the `privacy` columns and their indexes and `users.default_privacy`; `can_view_content()` is gone. A real per-item privacy model, if ever wanted, should be designed fresh.
- [x] **Household consent** 🟠: joining is invite/accept. New `household_invites` table (migration 021) rather than overloading `friend_requests`; pending invites show on the notifications page and in the badge count, and on the inviter's profile with *Cancel*. Only the owner (or someone in no household) can invite, and only friends. Only the owner can remove a member; anyone can leave. When the owner leaves, the longest-standing member becomes owner; a household of one is dissolved. All of it lives in `utils/households.py`, which admin removal and account deletion now use too, so neither can leave a household without an owner. Admin *add* to a new library makes that user its owner. 021 also repairs existing data: ownerless households get an owner, one-person households are dissolved.
- [x] **Email change needs the password** 🟠 (`user.update_email`): a password field appears while editing the email. With `EMAIL_VERIFICATION_REQUIRED` on, the new address is marked unverified and a verification email is sent (login then waits for it, as at registration).
- [x] **Logout is a POST** 🟢: sidebar form with CSRF; GET `/auth/logout` is now 405.
- [x] **Rate limiter** 🟠: the global default (200/day, 50/hour per IP on *every* route, static files and covers included) is gone; per-route limits on auth, profile changes, friend/household requests and imports stay. Memory storage per worker is documented as accepted (limits are x workers); Redis is the upgrade path. `TRUSTED_PROXY_COUNT` was already set in Phase 1.
- [x] **Quagga** 🟢: vendored to `static/vendor/quagga-0.12.1.min.js`; its sha512 matched cdnjs's published SRI. Source, licence and hash in `static/vendor/README.md`. No CDN scripts remain, which helps the Phase 6 CSP.

**Follow-ups found on the way** (not access bugs, so not done here):
- ~~The Goodreads import and the wishlist add match existing books across **everyone's** books.~~ Done in Phase 5 (`utils/book_matching.py`).
- Household members who aren't also friends can't see each other's profile or feed activity. Fine for one real household where both are friends; revisit only if it ever matters.

**Prod rollout:** migrations 020 and 021 run automatically on deploy. They were rehearsed on the dev DB copy and a fresh DB, not on a prod copy; prod's schema has surprised before (see Phase 2), so rehearse on a copy of the prod DB first, run from the dev checkout (prod doesn't have the new migration files until the deploy): `manage.py backup` on prod, copy the backup here, `venv/bin/python manage.py --db /tmp/prod-copy.db migrate`, then delete the copy.

---

## Phase 5: Finish the Goodreads import

`utils/goodreads.py` (the import), `utils/book_matching.py` (shared matching), `blueprints/user.py` `import_goodreads` / `import_fetch_covers`, `templates/goodreads_import.html`. Tests: `tests/test_goodreads.py`.

**2026-11-04, done** on branch `phase-5`; background covers added 2026-11-05 (149 tests). One migration: 022 (`cover_jobs`), runs on deploy.

- [x] **Match within your own books**: `BookIndex` matches by any ISBN-10/13 form, then by normalised title + author (a trailing "(Series, #1)" ignored, whitespace collapsed: the export has names like `Stephen        King`). It only looks at your own books, then your household's shelf; everyone else's means a new book. A `to-read` row on a book you or your household own gets *Want to Read* instead of a wishlist row (a wishlist row on your own book hides it from your library, see the `library_books` view). A `read` row on your own wishlist entry moves it into the library.
  - Wishlist add (manual form and search result) only reuses your own books: already on your wishlist means the duplicate message, already on your shelf is refused ("already in your library", it used to silently hide the book). Household and stranger copies are never reused for a wishlist entry, since *Move to library* would then not make the book yours. Checked before the cover download, so a refusal leaves no orphaned file.
- [x] **Shelves** become **custom collections** of the same name (chosen over tags: the schema already calls them shelves, they have their own page, and they work for wishlist books, which never appear in the tag-filtered library). The status shelf is left out; an unknown custom *exclusive* shelf is kept as a collection too.
- [x] **DNF:** an exclusive or regular shelf named `dnf`, `did-not-finish`, `abandoned`, `gave-up`, `unfinished`, `not-finished`, `stopped-reading` (and a couple of spellings) sets `did not finish`. Your export has none, so this is covered by tests only.
- [x] **Reviews without a rating** are imported (rating NULL), and ratings/reviews on `to-read` books too. To make those editable, `read.rate_review` now accepts a review without a rating (but not neither), and the book page hides the "x / 5" line when there's no rating.
- [x] **Read Count** → that many sessions; the last is dated Date Read, earlier ones are undated (Goodreads keeps only the last date). A `read` row with no Read Count still gets one session. Undated sessions used to display as "Currently Reading"; they now say "Date unknown" and sort first (book page and review page).
- [x] **Unused columns**, decided: **Private Notes** → the wishlist note on to-read books (it used to put *My Review* there); on library books there's nowhere to keep them, so the result screen counts them as not imported (your export has none). **Not imported:** Additional Authors (79 rows, almost all translators, editors and illustrators: appending them to `author` would be wrong and break matching), Binding (no format column; revisit with Phase 8's format work), Owned Copies (0 on every row of your export; read books still go to your library), Spoiler.
- [x] **Per-row SAVEPOINT** inside one transaction for the file (an explicit `BEGIN`: otherwise the first SAVEPOINT opens the transaction and its RELEASE commits each row). A failing row is rolled back completely, reported as an error, and the import carries on.
- [x] **Empty values:** year/pages are integers or NULL. Dates are validated and zero-padded (`2016/5/9` → `2016-05-09`). `created_at` is never NULL: the Goodreads Date Added when present, else the column default. New books also get Date Added as `books.created_at`, so an import doesn't flood friends' feeds with 300 "added today" entries.
- [x] **Wishlist duplicates** are reported (outcome *Already imported*), as are re-imported rows. Re-importing the same file is a no-op: all 374 rows come back *already*.
- [x] **Encoding and file checks:** UTF-8 (BOM or not), else Windows-1252, else Latin-1; the result says when it wasn't UTF-8. Case-insensitive `.csv`. A CSV without the Goodreads columns is refused with a message.
- [x] **Covers, in the background** (2026-11-05): a cover fetch is now a job (`cover_jobs` table, migration 022; `utils/cover_jobs.py`; `blueprints/covers.py`) run by a daemon thread, so it carries on after you leave the page. Started from the import result screen, **Profile → Fetch Missing Covers** (your own books) and **Admin → placeholder covers** (all books; replaces the old 10-per-click button, whose limit was gunicorn's 30 s request timeout, not API manners). A small panel in the bottom-left corner of every page shows progress with *Stop*, then the result with *Dismiss*; it only polls while you have a job. Each book is tried once per job (an id cursor), so books with no cover online don't loop. If the process dies (deploy restart), the heartbeat goes stale after 3 minutes and the next page load picks the job up where it stopped. 0.5 s pause between books. Measured on the demo DB: about 1.5 s per book, with the odd slow one (one took 25 s of Open Library timeouts).
- [x] **Large files:** measured: your 374 rows import in 0.02 s (no network calls), so no chunking. The slow part is covers, which is batched with progress (above).
- [x] "Please Note" and "Where your data goes" on the import page rewritten to match; the garbled rate-limit sentence fixed.

**Found on the way:**
- [x] Saving a review with no dates added an **empty reading session** every time (`read.rate_review`). Fixed: a session is only added when a date is given. **Existing data:** the dev DB has 8 such sessions (both dates NULL) on 5 books. They now show as "Date unknown", which is harmless; delete them if you want (`DELETE FROM reading_sessions WHERE date_started IS NULL AND date_completed IS NULL AND created_at < '2026-11-05'`, after a backup). Not done in a migration, since Goodreads imports now create undated sessions on purpose.
- [x] The book page hid **Reading History** unless you had also written a review. It now always shows.
- [x] Removing a wishlist book that has your own rating on it keeps the books row (`remove_from_wishlist` won't delete a book anyone has data on), so it becomes a `library_books` row and appears in your library. Rare (a rated to-read book), but the import makes it possible. **Fixed 2026-11-05:** such a book is now marked removed (note "Removed from wishlist; not owned"), so it stays out of the library with its review intact; if you've rated/reviewed it or marked it read, it also goes on a custom collection **"Read but not owned"** (created on first use). *Restore* on the book page brings it into the library if you buy it after all.
- [x] `read.py` passes `datetime.date` objects to sqlite (Python 3.12 deprecates the default date adapter; one test warning). Store `.isoformat()` strings. Done in Phase 6.

**Done when:** your own `goodreads_library_export.csv` re-imports into a fresh DB with shelves, DNF, multi-reads and clean reviews, and the result screen accounts for every row.

- **2026-11-04:** checked through the real route on a fresh DB: 374 rows = 123 added to the library + 251 wishlist, 0 errors, all listed by outcome on the result screen. 121 ratings, 82 reviews (no HTML left), 125 sessions (*God Bless You, Mr. Rosewater* and *The Stand* have two each), collections audiobook (42), re-read (7), picture-book (3). DNF is tested but not in your data. A second import of the same file: 374 *already*, nothing changed.

---

## Phase 6: Page structure

**Goal:** one layout, one shared JS file, no giant inline scripts. That makes the Phase 7 polish a mostly-one-file job and enables a real CSP.

- [x] **`templates/base.html`** with blocks `title`, `html_class`, `body_class`, `head`, `sidebar` (auth pages empty it), `content` and `scripts`; `<html lang="en">`, one `<meta name="csrf-token">`, the sidebar/flash includes. All 25 pages extend it (converted mechanically, page markup unchanged; per-page `<html>`/`<body>` classes kept as-is for Phase 7 to tidy). `tests/test_pages.py` asserts every page extends it.
- [x] **`static/common.js`** with `getCSRFToken`, `getCSRFHeaders`, `addCSRFToFormData`, `escapeHtml`, `showFlashMessage` and `dismissFlash`, loaded in `<head>` by `base.html`. The copies in `script.js`, `add_book.js`, `edit_book.js`, `tags.js` and `wishlist.js` are gone. Flash close buttons use a delegated `data-dismiss-flash` listener instead of `onclick`; the flash and star-rating CSS moved into `styles.css`.
  - Legacy `static/sidebar.js` replaced: the hamburger/search-dropdown code moved out of `script.js` into a new `static/sidebar.js`, loaded by `_sidebar.html` itself. **Bug found on the way:** the hamburger only worked on pages that happened to load `script.js`, so it was dead on the Goodreads import page (and threw errors on notifications).
- [x] **Inline scripts moved into `static/`:** all of them, not just the large ones (a CSP without `'unsafe-inline'` blocks a three-line `<script>` too): `user.js`, `admin_settings.js`, `rate_review.js`, `goodreads_import.js`, `book_detail.js`, `activity_feed.js`, `orphaned_images.js`, `fab.js`. Values the server knows (URLs, the username) come from `data-` attributes; the CSRF token from `getCSRFToken()`. `tests/test_csp.py` fails if an inline `<script>` comes back.
- [x] **Inline event handlers:** all 69 gone. `common.js` has a small dispatcher: `data-confirm="..."` asks before a form submits or a button acts; `data-click` / `data-change` / `data-submit="name"` call a function the page registered with `registerActions({...})` (looked up by name, never evaluated); `data-fallback-src` replaces `onerror` cover fallbacks. Built-ins `toggleHidden` and `showModal` (by `data-target` id) cover the one-liners. `postForm(action, fields)` replaced four copies of build-a-hidden-form-and-submit.
  - Kept: 16 `style="..."` attributes, allowed by `style-src 'unsafe-inline'`. Injected CSS is a far smaller risk than injected script; converting them is Phase 7 tidying if ever.
- [x] **Named row access in templates:** `book[0]`, `book[8]` etc. are now `book['id']`, `book['cover_image_url']`. **Bug found:** `edit_book.html` tested `book.details` (always undefined) instead of `book_details`, so the **subtitle field was always empty and saving the edit form wiped the book's subtitle**. Fixed, with a test. Subtitles already lost this way can't be recovered from the DB; a Goodreads re-import doesn't carry them either.
- [x] **Content-Security-Policy** on every response (`app.py`): `script-src 'self'`, `img-src 'self' data: blob:`, `connect-src 'self'`, `worker-src 'self' blob:` (Quagga's scanner workers), `object-src 'none'`, `base-uri`/`form-action`/`frame-ancestors 'self'`. `CSP_REPORT_ONLY=true` in `.env` downgrades it to report-only as an escape hatch.
  - Search-result covers (add book, wishlist) now go through **`/books/thumbnail?url=`**: Google Books and Open Library hosts only, fetched with the SSRF-guarded `_fetch_image`, re-encoded as a small JPEG (so nothing but a plain image is served from our origin), cached a day in the browser, 600/hour per IP. The browser no longer contacts Google while you search, and Google's "image not available" placeholders now show the app's own no-cover image.
  - Checked in headless Chromium against a copy of the demo DB: every page, 49 interactions (sidebar, filters, view toggle, FAB, flash, session forms, profile editing, tabs, confirm dialogs, admin forms, a live title search) and the barcode scanner with a fake camera. No CSP violations, no JS errors.
  - If Cloudflare in front of prod injects its Web Analytics beacon, the CSP blocks it (harmless; turn the beacon off or add its host to `script-src`).
- [x] **Routes use `get_db()`:** every request-time `get_db_connection()` (blueprints, `models.py`, `app.py`, `email_utils.py`, `book_utils.get_filter_options`) now uses the request's shared connection; the `try/finally: conn.close()` wrappers are gone. `get_db_connection()` remains for `manage.py`, `utils/cover_jobs.py` (its own thread, no request) and `get_db()` itself.

**Found on the way:**
- [x] `script.js` cleanup: about 150 lines of commented-out code and five functions nothing called removed; a stale second `submitSortForm` that silently overrode the first (dropping its loading indicator) and a load handler that threw on pages with a query string are gone.
- [x] `switchView` threw on collection pages (a book grid without the grid/list buttons), so the saved list/grid choice half-applied there. Fixed.
- [x] Add-book and wishlist cover previews put API-supplied URLs into `innerHTML` unescaped (one inside an `onerror` JS string). Now escaped and proxied.
- [x] **Title-page covers** (reported by Phil): Google Books sometimes offers a scanned title page, "praise for" page or publisher-logo page instead of the jacket. `placeholder_reason` now also refuses an image that is at least 80% near-white with under 0.6% coloured pixels (`looks_like_page_scan`). Tuned on the 672 covers in `static/uploads`: it flags 161 files (34 distinct images, all page scans, header strips or "image not available" boxes); the closest real cover kept is *Blink* (90% white, 0.9% blue). A plain "75% white" rule would have dropped real covers such as *Choke*, *Wild* and *Consider the Lobster*. New fetches skip them, and **Admin -> placeholder covers** now lists the ones already saved (19 books in the demo DB) for clearing; *Fetch missing covers* then tries the other sources.
- [x] Barcode scanner over plain http:// (the LAN dev server) failed with "getUserMedia is not defined": browsers only offer the camera on https:// or localhost. Now says so (`cameraUnavailableReason()` in `common.js`). Prod is https behind Cloudflare, so unaffected.
- [x] Session dates are stored with `.isoformat()` (the Phase 5 item below); the test suite runs clean with `-W error::DeprecationWarning`.

**Done when:** every page extends `base.html`; no inline `<script>` over ~20 lines remains; CSP is on without `'unsafe-inline'`; routes use `get_db()`; tests pass.

---

## Phase 7: Design polish

**Status 2026-11-07: done.** 7.0–7.3 done and merged to `main`; 7.2b layout done, the rest deferred (the two-searches merge and the "Do I have this?" lookup build on Phase 8). The final headless sweep was skipped by Phil's call; 7.0's sweep and `tests/test_layout.py` stand in for it. The two open questions are settled (Phil, 2026-11-07):
1. **Friends' reviews on the book page:** the section only ever showed household members' reviews, so it's renamed "Household Reviews" (`household_reviews` in `books.show_book`). No ISBN/title matching of friends' copies; friends' reviews stay on their profiles.
2. **"Find friends" on the empty feed:** the link (to your profile, where the search is closed) and the sentence pointing at it are removed. Side note still stands: the user search matches any 2+ letters of a username, so switch to exact-username match if registration ever opens.

**Goal:** finish what the Phase 0 refresh deliberately left out, now that every page extends `base.html` (Phase 6) and edits happen in one place. Phase 0 is the house-style reference.

**Decided with Phil, 2026-11-05:**
- **negativeearth.net shadows, full match in House.** Taken from the site's CSS:
  - **Cards:** 2px ink border and a `4px 4px 0` olive (accent) offset shadow. A clickable card moves `2px,2px` on hover/press and its shadow drops to `2px`.
  - **Buttons:** a `2–3px` shadow that drops to `1px` as the button moves `1px`.
  - **Dark mode:** the border turns light; the shadow stays accent.
  - **Libaraxia's rules on top:** only clickable things press (a static panel that moves on hover looks clickable when it isn't), inputs get the 2px border but no shadow, and there's no movement under `prefers-reduced-motion`. Classic keeps its soft shadows.
- **New styles go in their own phase** ([Phase 9](#phase-9-more-styles)), after VHS: Shelf (iBooks-style), Outrun, and a video-store rack for VHS **inside Shelf**. Phase 7 lays the groundwork they need: component classes (7.1) instead of utility strings repeated in every template.
- **7.2b changes how Phil uses the app: ask him before starting it.**
- **Order:** 7.0 → 7.1 → 7.2 → 7.3 → 7.2b.

### 7.0 Layout bugs found on phones (done 2026-11-05)
Found by a headless sweep: every GET page × House/Classic × light/dark × 390/768/1280px, checking page overflow, controls past their card's edge, and console/CSP errors. Now 0 problems; `tests/test_layout.py` pins each cause.
- [x] **Add book: one column of inputs split into two after a manual ISBN lookup** (reported by Phil).
  - The cause: the server-rendered "Data source" line had a bare `col-span-2`. Below `md` the form grid has no column template, so spanning two columns made the grid invent a second one and every later field flowed into it.
  - The other entry paths (title search, barcode) fill the form in JS without that line, so they never split.
  - Now `md:col-span-2`. The form card's `m-8 p-8` also left inputs only 260px of a 390px phone; it now has phone padding.
- [x] **Add book and wishlist: a stray `</div>`** closed the method card early, so the form sat outside the page container, and the last close ate into `base.html`'s wrapper. The same mistake was in `collection_status.html` (a stray close) and `book_detail.html` (two divs never closed). `test_every_page_loads` now fails on any page whose tags don't balance.
- [x] **Inputs and buttons past the card edge on phones** (reported by Phil). The places:
  - add/wishlist search row and method tabs
  - the book page's tag input
  - profile → reading goal
  - collections → new shelf
  - The cause: a flex item's `min-width` defaults to its intrinsic width, about 20 characters (~200px in Courier Prime) for a text input. So `input flex-1` never shrank and pushed the button out. Fixed once in `styles.css` (`min-width: 0` on form controls). Method tabs get short labels on phones; friend-library shelf tabs wrap.
- [x] **Toasts and some coloured buttons were unreadable in House.** `text-white` on an accent/red fill: Tailwind's `white` is the ink colour in House, so that was dark-on-olive (light mode) and pale-on-bright-green (dark mode). Toasts now use `.flash-success/-error/-info` (shared by the Jinja partial and `showFlashMessage`), and 11 other spots use `text-on-accent`; a test greps for the pattern. Toasts also keep a 16px gutter on phones.
- [x] `tags.js` threw on wishlist books' pages (no tags section there).
- [x] **Hamburger X sometimes showed two dots on reopen** (reported by Phil, 2026-11-07): the ends of the middle bar showing past the rotated outer bars. The icon was six Tailwind classes toggled separately from three handlers. Now one `setSidebarOpen()` in `sidebar.js` sets `aria-expanded`, and `.hamburger-bar` in `styles.css` draws the X from it, with the middle bar scaled to zero as well as faded. Also closes the sidebar on a back/forward-cache restore.

### 7.1 Component classes and the house style
- [x] **Component classes** in `styles.css` (2026-11-05).
  - The classes: `.card` (a panel), `.card-link` (a clickable card: the book grids, wishlist cards), `.btn` (any filled button; the fill stays a utility such as `bg-accent` / `bg-red-600`), `.btn-outline` (an unfilled button) and `.fab`.
  - They read per-style shape variables: `--bw-card`, `--bw-btn`, `--card-edge`, `--sh-card`, `--sh-card-hover`, `--card-press`, `--sh-btn`, `--sh-btn-hover`, `--btn-press`, `--bw-outline`, `--outline-edge`.
  - About 170 class strings in templates and `static/*.js` moved over. A card inside a card turns into a hairline section with no shadow.
  - `tests/test_layout.py` fails if a `shadow-*` / `transition-colors` / `hover:scale-105` utility sits on the same element (utilities win over components and would switch the press off), or if a bordered panel or filled button skips the classes.
- [x] **negativeearth shadows in House:**
  - cards: 2px ink outline, `4px` accent offset, pressing to `2px` on hover
  - buttons: `2px` → `1px`
  - form controls: a 2px ink outline, no shadow
  - FAB, toasts and loading overlay: `--sh-hard` (now the accent offset)
  - no movement under `prefers-reduced-motion`
  - **Classic** gets the same classes with its original values: soft shadows, book cards scale 1.05 on hover, borderless buttons. Checked in a headless browser: computed transform and shadow at rest and on hover, both styles.
- [x] **Theme toggle** (done early, 2026-11-02): Profile → Appearance has **Style** (House = Gruvbox/square/bold lines, Classic = the original 2024 look, with a new light version) and **Mode** (System/Light/Dark), saved per user (migration 013). Styles are CSS-variable sets on `<html data-style data-mode>`. To add a style: one shape block and a light + dark palette in `static/styles.css`, plus a line in `THEME_STYLES` in `models.py`.
- [x] **Sidebar Mode shortcut** (System / Light / Dark above Logout). One handler in `sidebar.js` drives every `[data-theme-picker]` (sidebar and profile) and keeps them in step.
  - **Found on the way:** the add-book FAB (`z-50`) sat on top of the open sidebar, covering the Mode switch and Logout on phones. Its container (which includes the invisible menu above the button) also swallowed clicks on the page underneath.
  - Now the FAB is `z-30` and click-through except the button itself, and its menu backdrop is `z-20`.
- [x] ~~Delete the now-inert `rounded-*` / `shadow-*` classes from templates.~~ **Won't do (2026-11-02):** they drive the Classic style, so they stay. (The `shadow-*` utilities on cards and buttons did go, replaced by the component classes.)
- [x] **Film-frame covers** on the book page (House): the cover sits in a strip of film stock with sprocket holes, and the ISBN is printed along the edge in amber (`▸ 9780143129554`). Classic shows the plain cover. `--film`, `--film-edge` and `--film-hole` are fixed in both modes (film is dark either way).
  - **Removed 2026-11-05:** Phil didn't like it on books. The CSS, tokens and markup are parked in `docs/parked/film-frame.css` (not loaded) for VHS/DVD covers (9.1 rack, or the fork).
- [x] Remaining details from the sites (House only):
  - [x] zero-padded numbered markers (`01 — Step`) on `ol.numbered` (the Goodreads export steps)
  - [x] `↗` after links that open another site (`target="_blank"`); internal "more" links already end in `→`
  - [x] `.measure` (66ch) on description and review text (was already in place)

### 7.2 Page fixes seen in the 2026-11-02 screenshots
- **Decided 2026-11-04: keep a separate edit page** (no in-place editing on the book page).
  - Security is the same either way, since the server checks ownership on every save.
  - In-place editing would need per-field save endpoints or a JS form-state layer, plus its own validation and error display. Edits are rare in a household catalog, so that's a lot of work for a small gain.
  - The book page stays a clean read view; the edit page holds the owner/admin tools.
- [x] **Book tools on the edit page (from Phil, 2026-11-04; done 2026-11-05):** combine *Transfer Book Ownership* and *Delete permanently…* into one "Book tools" disclosure, styled with the transfer section's arrow, and move it to the edit page. Edit is already owner/admin only (`can_manage` on the page, ownership check in `edit_book`), so the tools stay owner/admin only for free. *Remove from Library / Put Back* stays on the book page: it's the normal, everyday action.
  - Now `_book_tools.html`, included by `edit_book.html`. `books._book_tools_context()` supplies its data and `_transfer_candidates()` is the shared "who can receive it" query. The book page links to `Edit Book → Book tools`. The edit page's back link now goes to the book, not the catalog.
- [x] **Book detail on mobile:** the 3-column metadata grid collapses to 2 with awkward wrapping ("Dial Press Trade / Paperback"). Use one column on narrow screens. *(One column on phones, two from `sm`, three from `lg`: at `md` the column beside the cover is too narrow for three.)*
- [x] **Profile card on desktop:** the avatar and title float above a two-column field list. Tighten it into a header row.
  - Avatar | name, bio and friend/household actions in one row, then a hairline and the fields: two columns, one on phones.
  - The avatar row had its own `p-4` inside the card's, which is why it sat 16px in from everything else.
- [x] **Add book:** after an ISBN lookup (a full page load) the method tabs reset to *Search*; keep *ISBN* selected. 🆕 2026-11-05
- [x] **Found on the way:**
  - The household and decline buttons (`bg-orange-600`, `bg-gray-600 text-white`) were missed by the `.btn` pass; they're now `.btn` / `.btn-outline`, and the lint tests cover orange and gray fills.
  - The book page's tag chips were hard-coded light gray (a bright chip in dark mode) and their remove button had no label and no focus outline. Now themed and labelled.

### 7.2b Search, sort and list view (from Phil, 2026-11-05; layout done, the rest deferred)

Go over the whole search/sort/filter bar (`_search_sort_filter.html`, `script.js`) and the grid/list toggle, and make them friendlier. What they do today, found while answering "which search do I use in a bookstore?":

- [ ] **Two searches that look alike but aren't.**
  - The header magnifier (`/books/search`) searches your and your household's shelf by title, author or year (substring). It **hides removed books** unless the Removed filter says otherwise, so "Read but not owned" and given-away books don't show. It doesn't search your **wishlist** or by **ISBN**.
  - Add Book's search queries **Google Books**, not your library.
  - Make the difference obvious, or merge them into one "find" that also covers wishlist and removed books, with results labelled *On your shelf* / *Household's* / *Removed* / *On wishlist*.
- [ ] **A "Do I have this?" scan for bookstores.**
  - Today the best in-store check is Add Book → barcode (or type the ISBN): the duplicate warning says *In library* / *Removed from library* / *In wishlist*, and you just don't add it. That's a detour through an add form, and it doesn't show whether you've **read** it or how you rated it.
  - A dedicated lookup (scan or type → owned? read? your rating? on wishlist? household's?) with one-tap *Add to wishlist* or *Add to library* would fit the use better.
  - Needs HTTPS for the camera, and builds on the Phase 8 scanner fixes.
- [x] **Search bar layout:** the grid/list toggle and the sort controls are hidden inside the header search dropdown, so you have to open "search" to change the view. Give view and sort their own visible spot above the grid; keep search in the dropdown (or the reverse).
  - **Done (2026-11-05, Phil chose "layout fix only"):** `_view_bar.html` above the grid on the library, shared library and search pages: book count, sort (field + direction) and a Grid/List switch with `aria-pressed`. Search and filters stay in the dropdown.
  - Fixed on the way: sorting always went to `/base/index` with only the sort fields, so it dropped your filters and threw you out of the shared library or search. Sort and filter forms now submit to the page they're on and carry the other parameters. *Clear filters* removes only filter parameters (it used to drop the search term too). The direction reads *Oldest/Newest first* for Year and Date added instead of A–Z. The GET forms no longer carry the CSRF token (it ended up in URLs, history and logs).
  - The two-searches merge and the "Do I have this?" lookup are deferred; the lookup builds on the Phase 8 scanner fixes.
  - Also decide whether sort applies instantly (it does today) and filters need *Apply* (they do today), which is inconsistent.
- [ ] **List view** is the grid restyled by `switchView` swapping class strings in JS (`script.js`). Make it a real layout (CSS class on the container, columns for author/year/status/rating), so it can show more than the grid and doesn't drift from `_book_grid.html`.
- [ ] Search matching is a plain `LIKE '%term%'`: no accent/punctuation folding (the duplicate check's `_normalise` already does that), no subtitle, no tags. Consider the same normalisation, and SQLite FTS5 if it ever needs ranking.

### 7.3 Quick wins and accessibility
- [x] Replace `alert()` / `confirm()` with the toast and a small styled confirm modal (built from `.card` / `.btn`).
  - **Done:** 47 `alert()`s are toasts. `confirmDialog()` / `confirmSubmit()` in `common.js` are a native `<dialog>` card (Esc and Cancel keep things, destructive wording gets a red OK with focus on Cancel); every `data-confirm` uses it and replays the click or submit. `test_no_native_alert_or_confirm` keeps them out.
- [x] Cover loading skeletons; consistent no-cover styling (pairs with 3.2).
  - **Done:** Phil picked "title on a plain binding". `_no_cover.html` (and its JS twin `noCoverHtml()` in `common.js`) is the surface colour with an accent spine band and the title and author set in Young Serif; `sm` thumbnails show the title only, and shelf-preview strips (no title in the query) just the binding. It replaces the "No Image Available" boxes and book icons on the grid, list view, book page, review page, friend library, wishlists, feed, profile and collections.
  - Grid covers shimmer until loaded (`img.book-cover-img:not([data-loaded])`, set by a capture-phase `load`/`error` listener in `common.js`). An attribute, not a class, because the grid/list switch in `script.js` rewrites `className`. That rewrite also dropped `relative` from the cover box, un-anchoring the *Removed* badge after a view switch; fixed.
- [x] Collections shelves as horizontal scroll-snap rows (`.shelf-row`; the cover strip overflowed its card on phones).
- [x] Book detail: larger framed cover, tidy metadata grid, reviews as cards, smoother "read more".
  - **Done:** larger cover (the film frame was tried and removed, see 7.1), metadata grid 1/2/3 columns, transfer and delete moved to Edit → Book tools. Household reviews are cards with the text in place, not an accordion in a scroll box. One shared "Read more" (`initReadMore` / `toggleReadMore` in `common.js`) for the description and reviews on the book page and profile; it only shows when the text overflows and animates both ways. Replaces three hand-rolled toggles.
  - The "Friend Reviews" section only showed **household members'** reviews (`get_library_members`); renamed "Household Reviews" on 2026-11-07 (see the status above).
- [x] Empty states for an empty library, wishlist, feed and search (`_empty_state.html`). The library one tells filtered-to-nothing apart from empty; the feed one says it shows friends' activity (it used to say "start adding books"). Also fixed the shared-library text, which told you to do something that doesn't exist.
- [x] Stats: a small reading-over-time chart on the profile (after 3.1 fixes the numbers).
  - **Done:** Overview tab, books finished per month (`user.reading_by_month`). Twelve months ending now, or ending at the last finished book when the log has gone quiet; the range is always printed. HTML bars, no chart library, hover tooltips, a summary for screen readers and a "Show as a table" view. Bars use a `--chart-bar` token: Classic dark lifts it to `#6a9f2a` because its accent is under 3:1 on those greys.
- [x] Accessibility:
  - [x] `<html lang="en">` everywhere (free with `base.html`)
  - [x] labels/`aria-label` on form inputs and icon-only buttons: 39 unnamed controls, now 0 in a headless audit of every page; `test_every_field_and_button_has_a_name` checks the templates.
  - [x] focus styles from 0.5 on every page: a headless check focuses every control in House and Classic; all show an outline or a ring. (Tailwind 3's `focus:outline-none` is a *transparent* outline, so a check has to look at the colour, not just the style.)
  - [x] hover-only controls (delete ×, edit pencils) use `.reveal`: always visible on touch screens, and shown on keyboard focus.

**Done when:**
- Every page uses the component classes, and House matches negativeearth's borders and shadows.
- The headless sweep (every page × House/Classic × light/dark × 390/768/1280px) finds no horizontal overflow, no control past its card, and no console or CSP errors.
- No `alert()` / `confirm()` is left in `static/*.js`.
- The 7.2 and 7.3 items are done. 7.2b is done or deliberately deferred.
- The README screenshots stay deferred to after Phase 8 (see 0.7).

---

## Phase 8: Physical media: movies and vinyl

A core Libaraxia feature. The design notes were written alongside the fork plan, in [FORK-SPEC §5](FORK-SPEC.md#5-phase-2-core-change-b-vhs-support), but nothing here needs the fork.

### 8.0 Fix the barcode scanner first 🆕
Reported by Phil (2026-11-02): camera only fills half the barcode window, it often takes the barcode too early (wrong number), seems to work with only one camera, and is generally flaky. VHS scanning builds on this, so fix it before the rest of the phase. The scanner code is duplicated in `add_book.js` and `wishlist.js`; fix it once in a shared module (ideally `common.js` from Phase 6) and use it from both.
- [x] **Misreads (takes the code too early):** `onDetected` accepts the very first frame whose code is 10 or 13 digits, with no checksum and no confirmation. Validate the EAN/ISBN check digit, and only accept a code after it's read the same way on several frames in a row (e.g. 3), or reject reads whose average decoder error is high.
- [x] **Only one camera:** the stream is hard-coded to `facingMode: "environment"` at 640×480. Add a camera picker (`enumerateDevices()`, select by `deviceId`, remember the choice in `localStorage`) and fall back cleanly on devices without a back camera (laptops, desktops). On phones with several back lenses (wide/ultra-wide/macro), the default can be one that won't focus up close, so the picker matters there too.
- [x] **Resolution/focus:** ask for a higher resolution (e.g. 1280×720 ideal) and continuous autofocus where supported; 640×480 is too coarse for small barcodes.
- [x] **Camera not released:** `stopScanner()` only calls `Quagga.stop()` when `Quagga.initialized` is true, which isn't a Quagga API property. Check whether the camera light stays on after a scan or when switching tabs, and stop the stream unconditionally.
- [x] **Swap Quagga 0.12.1 for `@ericblade/quagga2`** (the maintained fork), vendored into `static/` (this also covers the Phase 4 SRI item). Or evaluate the browser's native `BarcodeDetector` where available, with quagga2 as the fallback.
- [x] **UPC-A is rejected:** the code-format check only allows 10 or 13 digits, so 12-digit UPC-A (most VHS tapes) is dropped silently. Needed for the scanner dispatch below.
- [x] **Feedback:** a visible target box, a beep/vibrate on a confirmed read, and a styled error instead of `alert()` (pairs with Phase 7).
- [x] Test on Phil's phone(s) and at least one laptop webcam, over HTTPS. *(2026-11-07: iPhone 17 Pro Max, Safari home-screen app: quick reads, right numbers, better than before. Laptop dropped: Phil never scans on one.)*

**Status 2026-11-07 (branch `phase-8`):** one shared module, `static/scanner.js`, used by `add_book.js` and `wishlist.js`. It owns the camera (`getUserMedia`, 1280×720 ideal, continuous autofocus where offered, stream stopped on scan / Stop / tab hidden / page left) and hands the decoder only the pixels inside the visible target box, so the decoder is a small `{available(), decode(canvas)}` object (`quaggaDecoder`) that can be swapped. The "camera only fills half the window" bug was Quagga appending its own canvases into `#interactive.viewport`, its default target; the decoder now gets a detached element instead. A code is accepted after 3 identical reads in a row with a valid EAN-13/UPC-A check digit, and handed over as 13 digits (UPC-A gets its leading 0). Readers are EAN-13 and UPC-A only (EAN-8/UPC-E dropped: never on books or tapes, and a source of partial misreads). Default camera on iPhones is the "Back Ultra Wide Camera": on Phil's iPhone 17 Pro Max it was the only one that read barcodes, since the main camera can't focus closer than about 20 cm and the Ultra Wide has macro autofocus. Elsewhere it's the plain back camera (Android ultra-wides are often fixed-focus); a camera picker appears when there are two or more, remembered in `localStorage`. `BarcodeDetector` not used (not on iOS WebKit or Firefox). quagga2 1.12.1 vendored with hash; since it decodes on the main thread, the CSP's `worker-src` dropped `blob:`. Checked end to end in headless Chromium with a fake camera: EAN-13 and UPC-A read and confirmed in about 0.5 s with the stream released, a bad check digit never accepted. Tests: `tests/test_scanner_js.py` (check digits, confirmer, camera choice, under node), vendor hash and CSP checks in `test_csp.py`. `generate-cert.sh` now writes subjectAltNames (localhost + LAN IPs), which iOS requires.

### 8.1 Design: videos are their own section (decided with Phil, 2026-11-07)
Supersedes FORK-SPEC §5.4's "VHS in the library grid with a badge". Phil wants tapes kept apart from books.

- **Own sidebar section, "Videos"**, with its own grid, search/filter, add form, detail page and stats. The Library, its counts, book stats, the Goodreads import and the cover fetcher stay **books-only**, exactly as today.
- **Same table underneath:** a video is a `books` row with `media_type = 'video'` and a `format` (`'VHS'` now; LaserDisc/DVD/Betamax possible later without a migration). A separate table would duplicate reviews, tags, collections, sessions and wishlist, which all hang off `books.id`.
- **Separation lives in the views:** `library_books` gets `AND media_type = 'book'`, so every page and count already built on it ignores videos with no other edits. A new `library_videos` view feeds the Videos pages. Every query that reads `books` directly (about 50: feed, collections, wishlist, export, cover jobs, book matching, admin) is checked and filtered where needed, and tests assert a video never appears on a book page or in a book count.
- **Per-tape data:** the catalog record (title, director in `author`, studio in `publisher`, year, runtime, barcode, catalogue number, sleeve photo), plus **Watched / Want to watch** and **rating + review**.
- **Sharing:** same access rules as books. Household members see a shared Videos view, friends can browse your Videos, `can_view_book` covers video detail pages. Tape reviews appear in friends' feeds, worded "watched".
- **Defaults (Phil can override):** no video wishlist for now (a tape scanned on the wishlist page says so); the cover fetcher skips videos; tags and custom collections are shared with books (a collection may hold both); export includes videos, marked by type.

### 8.2 Build
- [x] **Scanner dispatch** (server + `add_book.js`/`wishlist.js`): an EAN-13 starting `978`/`979`, or a valid ISBN-10, takes the book path; any other EAN-13/UPC-A takes the video path. UPC-A is stored as EAN-13 (the scanner already hands it over that way). A server-side twin of the check-digit helpers in `utils/media.py`.
- [x] **Migration** `023_add_videos.sql`: on `books`, appended at the end, `media_type TEXT NOT NULL DEFAULT 'book' CHECK (media_type IN ('book','video'))`, `format`, `barcode`, `catalog_number`, `runtime_minutes`; indexes on `media_type` and `barcode`; `collections.status` CHECK extended with `'watched'` and `'want to watch'` (a table rebuild); `library_books` restricted to books and `library_videos` added (drop/recreate both). Folded into `create_database.sql`.
- [x] **`utils/media.py`:** media types, formats, field labels by type (Author ↔ Director, Publisher ↔ Studio, Pages ↔ Runtime, ISBN ↔ Barcode), statuses by type, barcode helpers. One place, used by templates and JS (via `data-` attributes).
- [x] **Books-only audit:** every direct `books` query checked; book stats, counts, filters, Goodreads import, cover jobs and book matching exclude videos. Tests for each.
- [x] **Videos section (routes/UI):** sidebar entry; `/videos` grid with search/sort/filter (format, status, rating); add form (manual entry first, scanner on it); detail/edit pages showing runtime, studio, barcode, catalogue number; Watched / Want to watch; rating + review; household and friends' Videos views; duplicate check on `barcode`; `fetch_barcode_details` (keep `fetch_isbn_details` as an alias).
- [x] **Feed:** video reviews and "watched" activity in friends' feeds.
- [x] **Video stats** on the profile, separate from book stats.
- [x] **Lookups** (`utils/media_lookup.py`), last and optional. *(Phil, 2026-11-07: UPCitemdb + TMDb; Discogs not used.)* Barcode → UPCitemdb (trial endpoint, no key, ~100/day) → cleaned title → TMDb (`TMDB_API_KEY`, optional; a v4 read token goes in a header, a v3 key in the query) for director, runtime, synopsis, genre, poster. Studio and the sleeve photo come from UPCitemdb, the film data from TMDb. Title-only lookup (TMDb) for tapes without a barcode. `/videos/lookup` (60/hour), runs after a scan and when Add Video opens with a barcode; it only fills empty fields. Hits cached per process for 6 h, misses not (could be the rate limit). JSON and images via `_get_public` / `save_best_cover`; `_get_public` takes `headers`, sent on the first hop only. TMDb attribution on the form.

**Status 2026-11-07 (branch `phase-8`):** all of the above. In the UI the section is called **Cartridges** (Phil, 2026-11-07); code, URLs and the DB say "video". `blueprints/videos.py` (`/videos/`, `/shared`, `/friends`, `/user/<name>`, `/<id>`, `/add`, `/edit/<id>`, `/check_duplicates`) on the `library_videos` view; the detail page is `book_detail.html` worded by `media_labels()` (`/books/book/<id>` redirects videos there, so feed and collection links work). Scans: `classifyCode()` in `scanner.js` and `media.classify_code()` agree (one test runs both); a tape scanned or typed on Add Book goes to `/videos/add?barcode=`, on the wishlist it's refused with a pointer to Videos; `/books/fetch_barcode_details` with `fetch_isbn_details` as alias. Duplicate barcode/title in the household needs an "Add it anyway" tick. Status changes are now checked against the item's type, and *Untracked* clears a status (it used to fail on the CHECK constraint). Book stats, the profile's shelves and reviews, the Collections page's reading lists, book matching (Goodreads), the book duplicate check and the cover fetcher are books only; export adds Type/Format/Barcode/Catalogue Number/Runtime columns at the end; the account-removal dialog counts videos too. Admin's unowned-books page lists videos as well (reassigning one is harmless). Tests: `tests/test_videos.py`.

**Done when:** a VHS can be scanned or typed in from the Videos section and lands there with its barcode; it shows runtime/studio/barcode, can be marked watched and reviewed, and household/friends see it under Videos; no video appears in the Library, book stats, Goodreads import or cover fetching (tests); book flows are unchanged.

### 8.3–8.7: Movies, shared UI, vinyl (from Phil, 2026-11-07)
Worked in this order: each step makes the next one smaller. Movies and the shared grid/add-form pieces come first, so Vinyls is built on them instead of being a third copy. Items marked *(proposed)* are Claude's recommendation, to be confirmed by Phil before building.

### 8.3 Cartridges become Movies, with DVD
- [x] **Sidebar "Cartridges" → "Movies"**, likewise the headings and tabs (My Movies, Household Movies, Friends' Movies), with "Movie" as the noun in `media_labels()`. "Cartridge" stays as the name shown for the VHS format (*proposed:* a display name per format in `utils/media.py`: VHS → "Cartridge", DVD → "DVD"; the stored value stays `'VHS'`).
- [x] **DVD needs no migration.** `format` already allows any value and `media.VIDEO_FORMATS` lists DVD; a DVD is a `video` row with `format = 'DVD'`. The movie data (title, director, year, runtime, synopsis) is the same for both. *(Proposed: no DVD-only fields for now. Region code and disc count are the candidates if Phil wants them later; both would be plain columns.)*
- [x] Format filter, the badge on the grid and the stats' "by format" use the display names.
- [x] Tests: wording; a DVD added, filtered and counted.

**Status 2026-11-07:** done. "Movies" everywhere in the UI (sidebar with a film-strip icon instead of the cassette, headings, tabs, flashes, feed, profile tab); `media.FORMAT_LABELS` / `format_label()` (template filter `format_label`, and `format_label` in the duplicate-check JSON) show VHS as "Cartridge" on the grid badge, the format filter and picker, the detail page, the duplicate notice and the stats. "Sleeve" wording became "box" so it fits DVD cases. The "Add a Movie" button under the heading stays until 8.4's floating button replaces it.

### 8.4 Grid pages: one add button and one search for every section
- [x] **Floating add button, shared** (`_add_book_fab.html` → `_add_fab.html`, items passed in): a square `[+]` button only (no "Add Book" text), smaller, closer to the bottom-right corner on phones (about 16px in, instead of 24). The menu it opens is text only:
  - Library: `[Library]` / `[Wishlist]`
  - Movies: one flat menu, `[Cartridge]` / `[DVD]` / `[Wishlist]` (decided 2026-11-07; one tap less than a Cartridge/DVD → collection/wishlist tree, and the wishlist form picks the format itself).
  - Vinyls: `[Vinyl]` / `[Wishlist]`.
- [x] The Movies page's "Add a Cartridge" button under the heading goes; the floating button replaces it.
- [x] **Search via the magnifying glass in the top bar** on Movies (and later Vinyls), like the Library. Today `_search_sort_filter.html` always searches books (`books.search`); make it take the section's action URL, placeholder and filters (format, status, rating for movies), and drop the inline search/filter form from `videos.html`.
- [x] Tests: the menu items per section; the Movies search form points at `/videos/`.

**Status 2026-11-07:** done. `_add_fab.html` (replaces `_add_book_fab.html`) takes `fab_items`; `fab.js` rewritten (aria-expanded, Escape closes, menu links out of the tab order while closed). Library pages: Library / Wishlist. Movies: Cartridge / DVD, which open Add Movie with `?format=` picked; the Wishlist item waits for 8.6. `_search_sort_filter.html` takes `search_action` and `m`: on Movies the magnifier opens the same search box and Advanced Filters (genre, format, watch status, rating, removed, tags) and stays on the page; the Movies grid reads the Library's parameter names (`search_term`, `read_status`, `tags[]`, ...). `get_filter_options(owner_ids, media_type)` is per section, which also fixed the Library's status filter offering "watched" and movie-only tags. LaserDisc and Betamax dropped from the formats (Phil, 2026-11-07).

### 8.5 One add form for every media type
The book and movie add forms have drifted apart (book: Search / ISBN / Scan tabs over a hand-written form; movie: a collapsible scanner, a lookup bar and fields from a macro). Make them one template and one script, with the fields, wording and lookup sources driven by `media_labels()`.
- [x] **Same tab box on every type:** `[Search | Barcode | Scan]`, where Barcode is ISBN for books.
  - **Search:** books keep Google Books / Open Library. Movies get a **TMDb title search** that lists results (poster, title, year) to pick from, like the book search, and the pick fills the form. That's film data only, which suits VHS and DVD alike. It needs `TMDB_API_KEY`; without it the Search tab says so and Barcode and Scan still work.
  - **Barcode / ISBN:** the lookup button sits **next to the input** (as the movie form's "Look up barcode" does), instead of the book form's separate "Fetch with ISBN" button below it. A movie barcode goes to UPCitemdb, then TMDb.
  - **Scan:** the shared scanner; a read fills the code and runs the barcode lookup.
- [x] A lookup fills only empty fields and never reloads the page (the book ISBN lookup reloads today). Duplicate checks look the same on both.
- [x] One script (`add_item.js`) replacing the form parts of `add_book.js` and `videos.js`.
- [x] Edit forms use the same field layout: `edit_book.html` and `video_form.html` both use `_item_fields.html`; Edit Book keeps its cover search as "Find a better cover" (`cover_fetch`, `edit_book.js`).
- [x] Tests: each type's form renders its fields and tabs; lookups (faked) fill the form; no regressions in the book add flow (the existing tests).

**Status 2026-11-07:** done. `templates/add_item.html` (replaces `add_book.html` and the add half of `video_form.html`) with `_item_fields.html` (shared fields: work on the left, this copy on the right) and `static/add_item.js` (replaces `add_book.js` and `videos.js`). Tabs `[Search | ISBN or Barcode | Scan]`; the Look up button sits beside the code box, which still works without JS (books: POST `isbn_lookup`; movies: GET `?barcode=`). Movie title search: `/videos/search` (TMDb, 120/hour, results shown via `/books/thumbnail`, which now allows `image.tmdb.org`), then `/videos/lookup?tmdb_id=`. Without a TMDb key the Search tab says so and Add Movie opens on Barcode. A lookup fills empty fields and fields a previous lookup filled (`data-filled`), never what you typed, and never reloads the page. Duplicates: a notice above the form for both types (books used to get a blocking confirm dialog); movies still need "Add it anyway" on submit. Search runs on Enter / the button, no longer on every keystroke (saves API quota). The `title_search` / `barcode_scan` POST branches of `add_book` were dead and are gone. Checked in headless Chromium with stubbed replies: search, pick, barcode lookup, kept typed field, duplicate notice. Tests in `test_videos.py`.

### 8.6 Movie wishlist
- [x] Movies on the wishlist: add from the floating button or by scanning a barcode on the wishlist page (it's refused today), with the format picked on the form. "Move to collection" sends a movie to Movies, not the Library.
- [x] The wishlist page lists books and movies, separated (two sections, with jump links when both have items).
- [x] Friends' wishlists show both. Goodreads import unchanged (books only).

**Status 2026-11-07:** done. Adding to the wishlist is the shared add page: `/wishlist/add?type=book|video` (`wishlist.add_to_wishlist`) renders `add_item.html` with `destination='wishlist'` (a note field, "Add to Wishlist", Back to Wishlist; a code of the other type stays on the wishlist). `/wishlist/view` is the list only: Books and Movies sections (`_wishlist_card.html`, format icon on movies), its own `+` (Book / Cartridge / DVD), and the magnifier filter (`wishlist.js`, 809 lines down to 60). The Library's `+` Wishlist item opens the book form, Movies' `+` has a Wishlist item. A movie you already own (same barcode) is refused, like a book. "Add to Movies" moves it onto the shelf marked Want to Watch. Removing a watched wishlist movie keeps it on **"Watched but not owned"** (books: "Read but not owned"). Quick-add and remove work for movies; the book page's wishlist panel is worded per type, and the ThriftBooks/Bookshop links show for books only. The one-click "add from a search result" on the old wishlist page is gone (pick fills the form, then Add to Wishlist), as are its dead endpoints (`select_search_result`, `search_books`, `fetch_isbn_details`). Also fixed in Edit Book: the ISBN is saved (the UPDATE left it out), Genre isn't required, and saving goes back to the book's page instead of the Library. Follow-ups (Phil, same day): the wishlist has Books / Movies / Both tabs (`?show=`, default Both) instead of jump links; Add Book now refuses a copy already on the household's shelf until "Add it anyway" is ticked, like Add Movie (a wishlist-only match stays a warning); the `+` sits 14px further in from the edge (30px on phones, 38px wider).

### 8.7 Vinyls
Sidebar link **"Vinyls"**. Laid out like Books and Movies: the same grid, view bar, magnifying-glass search, floating add button, the 8.5 add form, the detail page worded by `media_labels()`, household and friends' tabs, stats on the profile, feed activity.
- [x] **Migration** `024_add_records.sql` (Phil, 2026-11-07: lookup tables instead of wider CHECKs). `media_types` and `statuses` lookup tables replace the CHECKs on `books.media_type` and `collections.status` (foreign keys instead), so a new type or status is an INSERT from now on, never another rebuild. One last **table rebuild of `books` and `collections`**: views dropped first, columns in the same order, ids and AUTOINCREMENT counters kept; `library_records` view added. Folded into `create_database.sql`. Tests: 023 → 024 keeps rows, ids and counters; unknown type/status refused; `utils/media.py` matches the lookup tables.
- [x] **Fields** (`utils/media.py`): artist (`author`), label (`publisher`), year, cat. no. (`catalog_number`), **Length** (`runtime_minutes`, summed from MusicBrainz track lengths), tracklist and notes in the description. Formats stored as `LP`, `EP`, `7in`, `10in`, `12in`, shown as LP, EP, 7" single, 10", 12" single (`FORMAT_LABELS`). No speed column: it follows from the format.
- [x] **Statuses:** Listened / Want to listen.
- [x] **Lookups: MusicBrainz** (decided 2026-11-07): open data, no key, a **title search** (artist + title) like the book and movie Search tabs; covers from the **Cover Art Archive**. Through the SSRF guard like the others.
- [x] **No barcodes for vinyl at all** (Phil, 2026-11-07, replacing the earlier "Movie or vinyl?" question): Add Vinyl is title search plus manual entry, with no Barcode or Scan tab and no barcode field. `classify_code()` is unchanged, so a non-ISBN code on Add Book still goes to Movies. The duplicate check is by title (and cat. no.). `books.barcode` stays empty for records, so scanning can be added later without a migration.
- [x] **Shared section module** (Phil, 2026-11-07): the Movies blueprint's grid, filters, add/edit, duplicate check and friends' list become one module that builds a blueprint per type (`videos`, `records`; endpoint names unchanged), instead of a copy for records.
- [x] Books-only audit repeated for `'record'` (the 8.2 tests, run for each type).

**Status 2026-11-07:** done. `blueprints/media_section.py` (`Section` + `make_blueprint`, `section_for(type)`) now serves Movies and Vinyls; `videos.py` and `records.py` are a Section each plus their own lookups. Templates renamed to `media_grid.html`, `_media_tabs.html`, `media_friends.html`, `media_form.html`; `_format_badge.html` replaces three copies of the badge. `media_labels()` gained `bp`, `item`, `formats`, `has_barcode`, `want_status`, `not_owned`, `description`, `search_placeholder`, `no_sessions`, and `media.item_endpoint()` / `media.VIEWS`; the template globals `item_url(row)` and `labels_for(row)` word and link mixed lists (feed, wishlist, grid) by each row's type, so templates no longer test for `'video'`. MusicBrainz (`utils/music_lookup.py`): `/records/search` (one row per pressing: label, cat. no., year, country), `/records/lookup?mbid=` (UUID only); every word must match the artist or title, and `format` is listed per vinyl size because MusicBrainz matches it as a whole value (`format:vinyl` misses `12" Vinyl`). User-Agent with a contact (`MUSICBRAINZ_CONTACT`, default the GitHub URL), one request per 1.1 s per process, 6 h cache, a 503 says "busy, try again". Covers via `coverartarchive.org` (added to `THUMBNAIL_HOSTS`), the pressing's art then its release group's. Record duplicates: title only with the same artist (or a blank one), plus the cat. no. ignoring case/spaces/dashes. Wishlist: Books / Movies / Vinyls / All tabs (`?show=both` still works); removing a listened wishlist record keeps it on "Listened to but not owned". Profile: a Vinyls stats tab (`calculate_media_stats`, which replaced `calculate_video_stats`). Feed: "listened to" / "wants to listen to". Checked in headless Chromium with MusicBrainz stubbed: search, pick (fills 9 fields, sets the format, keeps a typed genre), duplicate notice, save, detail page, phone width. Tests: `tests/test_records.py` (40), migration tests in `test_migrations.py`.

**Follow-up (Phil, 2026-11-08):** search moved out of the header. Every grid page (Library, Shared, search results, Movies, Vinyls) has one row under its tabs: the search box (3/4) and a filter button (1/4: funnel with the active-filter count, arrow) whose panel drops down over the grid; click outside or Escape closes it, and it no longer opens by itself when the URL has filters (the count and the "Active filters" pills under the row say so). The wishlist filter is an inline box under its tabs. The header magnifying glass is gone. Same day:
- **Header:** site title on the left, hamburger on the right (the sidebar still opens from the left).
- **Grid headings:** a card under the tabs with the section's icon and the page's name (`_icons.html`: `icon()` and `section_heading()`; Library = Lucide `library`, Vinyls = Lucide `disc-3`, Movies = the VHS cassette, which Lucide lacks). The sidebar and format badges use the same icons. Spacing: 24px around the heading card, 16px between the search row and the view bar (`_book_grid.html` lost its `pt-8`).
- **Vinyl covers are square** in the grid (`#book-container[data-media="record"]`, styles.css) and on wishlist cards.
- **Fixes:** date inputs overflowed the session box on iOS Safari (`appearance: none`); the session form said "Reading Session" for every type (the JS hard-coded it); the `+` menu's first item showed a focus ring after a tap (focus moves only for keyboard opens).
- **Vinyls became Music** (Phil): the section is "Music", an item is an "album" (`media_labels`, with an `a` article key: "an album"), and CD and Cassette joined the formats. Code, URLs and the DB keep `record`; `?show=vinyls` on the wishlist still works. Manual entry covers CDs and tapes; MusicBrainz still searches vinyl only (Phase 8B).
- **Dropped the Goodreads cover source** (the BookCover API at bookcover.longitood.com): slow, and it often timed out after 10 s, holding up every lookup and cover search.
- **"Find a better cover"** streams its progress (NDJSON: a line per source asked and per download, covers shown as they arrive; `book_utils.cover_search_steps`) and is on Add Book too (books only; `static/cover_finder.js`). The route was admin-only although Edit Book shows the button to owners; now any signed-in user, 30/hour.

---

## Phase 8B: Music lookups, formats and ownership

From Phil, 2026-11-08, after using Phase 8. Ship Phase 8 first and let it run for a few days. Plan the schema side with Phil before building (the ownership part especially).

### 8B.1 MusicBrainz for CDs and cassettes
- [x] `music_lookup.build_query` asks for CD and Cassette as well as the vinyl formats (MusicBrainz matches `format` as whole values, so the CD variants are listed: CD, Enhanced CD, HDCD, SHM-CD, Blu-spec CD, Copy Control CD, Hybrid SACD (CD layer), SACD, CD-R), and `vinyl_format()` became `album_format()`, which also returns `CD` / `Cassette` (an EP on CD is a CD; vinyl with a bonus CD stays vinyl). Search results already show the format per row.
- [x] A format choice on the Search tab (Any format / Vinyl / CD / Cassette, `?format=` on `/records/search`; each is its own cache entry), so a CD search doesn't list twenty vinyl pressings.

**Status 2026-11-08:** done. Checked live: a CD search for *Blue* lists the HDCD pressings. A cassette search for it found none, unconfirmed whether that's the data or the query (MusicBrainz started answering 503 before a second album could be tried); try a cassette search on the live page. Tests: `test_build_query_needs_every_word_and_a_physical_format`, `test_album_format`, `test_search_route_narrows_by_format`.

### 8B.2 Book formats: Book / Audiobook
- [x] A format for books: `Book` or `Audiobook`, a select on the book form (Add and Edit). A plain book is stored as NULL (`media.book_format`), so every existing book reads as Book with no migration. The Format filter appears on the Library pages once there's an audiobook (`format_filter`: Book also matches NULL).
- [x] Grid badge: Lucide `book-headphones` (`_icons.html` `audiobook`, `_format_badge.html`, and the infinite-scroll cards in `script.js`); a plain book has none. The book page lists Format, and "Print Pages" for an audiobook.
- [x] Goodreads import: a row on an audiobook shelf (`audiobook`, `audiobooks`, `audible`, ...) or with an audio Binding (Audible Audio, Audio CD, ...) that creates a new book creates it as Audiobook, **not owned**; a to-read one goes to the wishlist as Audiobook. A row matching a book you already have leaves it alone. The `audiobook` custom collection is still made, as before. This settles the audiobook question in CLAUDE.md "Product direction".
- [x] Decided (Phil, 2026-11-08): audiobooks count in reading stats (read, goal, reviews, feed), never in page totals (library pages, pages read, longest book), owned or not. Usually not owned (picking Audiobook on Add ticks "I don't own this"); an owned one (files you bought) counts as owned.

**Status 2026-11-08:** done with 8B.3. Tests in `tests/test_ownership.py` and `tests/test_goodreads.py`.

### 8B.3 Reviewing something you don't own
Phil's idea: a movie watched on TV, an audiobook from a library, still worth a review. Decided with Phil (2026-11-08): **ownership is its own field**, separate from format and from removal. Phil's worry: never see something in the grid (or in a search at a bookstore) and think he owns it.
- [x] Migration `025_owned.sql`: `books.owned` (1/0, default 1). The old "not owned" rows (stored as removed with the note "Removed from wishlist; not owned") become `owned = 0`, not removed. Removal keeps meaning "had it, it left".
- [x] **Default is the shelf:** every grid, search (Library, Shared, search results, Movies, Music, friends' libraries) and owned count shows only `owned = 1 AND removed_at IS NULL` (`book_utils.on_shelf` / `shelf_filter`). Owned counts and stats (profile, admin, friends' counts, Movies/Music stats, export "You Own It") skip not-owned items; reading stats count them.
- [x] **Show** in the filter panel replaces "Removed": On the shelf (default) / Not owned / Removed / Everything (`?show=`; old `?show_removed=` links still work). Not-owned cards carry an accent "Not owned" badge, removed ones "Removed".
- [x] On the add form (books, movies, music; not the wishlist's): "I don't own this (I read/watched/listened to it and want to review it)". A not-owned add goes to the item's page, since the grid won't show it.
- [x] Item page: a "Not owned." note and an **I Own It Now** button (`POST /books/ownership/<id>`, owner or admin, any type); owned items get a small "Never owned it? Mark it not owned" under the buttons.
- [x] Duplicate notices say "not owned (bought it? open it and choose I own it now)", so buying it later keeps the review on the same record instead of making a second copy.
- [x] Removing a read wishlist item (`wishlist._keep_as_not_owned`) sets `owned = 0` instead of removing it, still filed on "Read / Watched / Listened to but not owned".
- [x] The search hint (Phil, 2026-11-08): a search on the default Show that matches items off the shelf adds one line above the results, e.g. "Not on your shelf: Circe (read, not owned). Show it", with the owner's name for a household member's item and "removed" for removed ones. The items never join the results; "Show it" reruns the search with Show: Everything. Library search and the Movies/Music grids (yours and household; not friends'). `book_utils.off_shelf_matches`, `_off_shelf_hint.html`, `url_with()` template helper. Tests: `test_search_hints_at_matches_not_on_the_shelf`, `test_section_search_hint_names_household_owner_and_skips_friends`.

**Status 2026-11-08:** done. Checked on a migrated copy of the dev DB in headless Chromium (desktop and phone): default grid hides not-owned, Show: Not owned lists them badged, the item page note and button, Audiobook ticking the box. The dev DB had no old not-owned rows, so the data step of 025 is only covered by `test_025_turns_wishlist_not_owned_rows_into_not_owned`; on prod it will convert whatever "Read but not owned" items exist.

### 8B.4 Export: movies and music (Phil, 2026-11-08)
- [x] "Export my data" covers every type (done 2026-11-08, `test_data_export_has_type_and_format`). `library.csv` already has every type (with Type, Format, Catalogue Number, Runtime), but `reading_sessions.csv`, `reviews.csv`, `shelves.csv` and `wishlist.csv` have no Type or Format column, so a movie review can't be told from a book's. Append Type and Format (appended, so older readers keep working). Profile wording: "library" means books, movies and music.

### 8B.5 Accent colour picker (Phil, 2026-11-08; instead of Phase 9 for now)
- [x] Profile → Appearance: an accent choice next to Style and Mode, as swatches: green (default), aqua, blue, purple, orange, red, yellow, each with a light and a dark Gruvbox value (`styles.css`: `--acc-l` / `--acc-d` per `:root[data-accent=…]`, read by the House palette). Stored in `users.accent` (migration `026_accent.sql`, default `green`, checked against `models.ACCENTS`), on `<html data-accent=…>` like `data-style`. **House style only:** Classic keeps its own green and hides the picker.
- [x] Hard shadows, focus rings, tabs and chart bars follow `--accent`, so nothing else needed touching. Light values are Gruvbox's dark shades and dark values its bright ones, the pairs the palette already uses for text on paper, so `--on-accent` stays the paper/ink colour. Contrast checked: every accent is at least 4.5:1 against its on-accent text in both modes (lowest: light green 4.6, dark red 4.8).

- [x] Classic gets the accents too (Phil, 2026-11-08). Gruvbox's standard colours can't carry Classic's white button text (yellow 2.5:1, green 3.1:1), so Classic uses each accent's light shade (Gruvbox faded, 4.9 to 8.6:1 with white) in both modes; green stays Classic's own #4f7d19. Its dark-mode chart bars use the bright shade.
- [x] Style names: House shows as **Negative Earth**, Classic as **OG** (`models.THEME_STYLES`; the stored keys `house` / `classic` and the CSS are unchanged, the same way Movies is still `video` underneath).
- [ ] Known, older than the picker: in OG dark mode, accent-coloured *text* (links like "View all", `text-accent`) is under 3:1 on the greys, for the original green too (2.8). Fix with a separate text token (the accent's bright shade) for OG dark.

**Status 2026-11-08:** done. Tests: `test_accent_colour_is_saved_and_on_every_page`, `test_every_accent_has_css`, `test_style_names_and_classic_accents`. Checked in headless Chromium with blue in dark mode.

### 8B.6 One page heading everywhere (Phil, 2026-11-08)
- [x] `page_heading(icon, name, subtitle)` in `_icons.html` (`section_heading` uses it) on Activity Feed, Notifications, Wishlist, Collections and Admin Settings, with the sidebar's icons, now in the `icon()` macro too (bell, feed, bookmark, collections, user, settings), so the sidebar and the headings can't drift. Test: `test_pages_share_the_heading_card`.

### 8B.7 Feed images (Phil, 2026-11-08)
- [x] Activity feed covers follow the image's own shape (natural aspect ratio, bounded size) instead of a fixed box that crops or hides overflow. `.feed-cover` in `styles.css`: only a max width (6rem) and max height (10rem), so an album is square, a book or VHS box tall, and the corners and shadow hug the picture. Checked at phone width with a wide, a square and a tall cover.

### 8B.8 "Back to Catalog" (Phil, 2026-11-08)
- [x] Replaced by breadcrumbs: `crumbs(trail, here)` in `_icons.html`, a quiet uppercase trail (LIBRARY / CAT'S CRADLE / REVIEW; links muted, accent and underlined on hover, the current page cut with an ellipsis). It says where you are as well as the way back, so there's no arrow button to style. On item pages (Library, Movies or Music, or Wishlist / a friend's wishlist when you came from there), review, edit, add, search, friend's library and wishlist, shelves, Goodreads import and the admin sub-pages.
- [x] Pages in the sidebar (profile, notifications, collections, admin settings) lost their back link. Tests: `test_no_back_to_catalog_links`, `test_item_page_crumbs_follow_the_section`.

### 8B.9 Phase 9 parked
- [x] Phase 9 (Shelf, Outrun) parked in favour of 8B.5.

### 8B.10 Discogs for Add Album (Phil, 2026-11-08)
MusicBrainz kept answering 503 (busy on their side, not our rate: a handful of searches seconds apart).
- [x] `utils/discogs_lookup.py`: search (`/database/search`, the same Any / Vinyl / CD / Cassette choice, digital-only releases dropped) and release lookup (`/releases/<id>`: artist, label, cat. no., year, format, genre, length, tracklist with side headings, cover). Personal access token in `DISCOGS_TOKEN` (`.env`, prod and dev), sent in a header only. One request per 1.1 s per process, 6 h cache, a 429 or 5xx is "busy".
- [x] `/records/search` asks Discogs when the token is set; MusicBrainz when it isn't or when Discogs is busy (one try each, no retries). Rows carry `source`; `/records/lookup?discogs=<id>` or `?mbid=`.
- [x] Credit lines under search results: "Data provided by Discogs" (their API terms), and TMDb's required notice on Add Movie's search.
- [x] Checked live 2026-11-08 (two requests): a cassette search for Rumours lists the cassette pressings; the lookup fills every field.
- [x] TMDb's logo: their "Primary short" SVG, unchanged, in `static/logos/tmdb.svg` (from themoviedb.org/about/logos-attribution, 2026-11-08), shown small beside the notice at the foot of Add Movie (`test_tmdb_logo_with_the_notice`).


### 8B.11 Shop links on wishlist items (Phil, 2026-11-08)
- [x] One partial (`_buy_links.html`, `media.buy_links`) instead of two copies of the book buttons: books ThriftBooks and Bookshop.org (as before), movies an eBay search for the title plus VHS or DVD, music the Discogs Marketplace filtered to the album's format (Vinyl / CD / Cassette). Buttons now use the accent colour instead of fixed blue and green.


### 8B.12 Barcodes for music (Phil, 2026-11-08: reverses "no barcodes for music")
- [x] `media.HAS_BARCODE[RECORD]` on: Add Album has Search, Barcode and Scan tabs (the shared scanner), a barcode field stored as EAN-13 like movies, and duplicates match on it.
- [x] `/records/lookup?barcode=`: Discogs barcode search (asked as printed, a UPC-A as 12 digits), then the first release fills the form; MusicBrainz (`barcode:` both forms) when there's no token, Discogs is busy, or Discogs has nothing. ISBNs are refused ("add it as a book").
- [x] Add Book with a non-ISBN barcode no longer jumps to Add Movie: it says "not a book: add it as a movie or as an album", both links carrying the code (also on the wishlist's add).
- [x] Checked live: Rumours' UPC 075992731324 finds the Warner CD (3010-2) and fills 9 fields; the Add Book to Add Album hand-over at phone width.
---

## Phase 8C: Collections refresh

From Phil, 2026-11-08. Plan the schema with Phil before building.
- [x] Page heading (8B.6).
- [x] **Collections per section:** Books / Movies / Music tabs on the Collections page, each with its own status shelves (`media.STATUSES`: Read / Currently Reading / Want to Read / Did Not Finish; Watched / Want to Watch; Listened / Want to Listen) and its own custom shelves. Status shelves already differ by type, so that part is a template change plus `view_by_status` taking a type. Custom shelves need a decision: (a) a `media_type` on `user_collections` (migration, existing shelves become `book`), a shelf holds one type; or (b) shelves stay mixed and each tab shows the shelves that hold that type. Proposed: (a), simpler to read and to add to.
  - **Done 2026-11-08 with (a)** (Claude went ahead with the proposal; easy to revisit before it ships). Migration `027_shelf_types.sql` rebuilds `user_collections` with `media_type` and `UNIQUE (user_id, media_type, name)`, so "Favourites" can exist in each section. Existing shelves holding only movies (or only albums) become that section's, all others Books; a shelf still shows everything on it. `?type=` picks the tab; the item page's shelf picker lists its section's shelves (plus any other shelf it's already on), and creating a shelf there makes one of that section and returns to the item. The wishlist's "Watched but not owned" shelves are made per section; Goodreads makes Books shelves. `view_by_status` now shows only the status's own type (it listed every type before) and 404s an unknown status.
- [x] **Side-scrolling rows on the profile:** the profile's status shelves use the Collections page's `.shelf-row` (one partial for both pages, so they can't drift apart). The profile's copy still has `flex truncate`, which hides covers instead of scrolling.
  - Done: `_shelf_rows.html` + `utils/shelves.py` draw every shelf card (Collections, profile, profile wishlist). The profile shows each section's statuses that are in use (Books, Movies, Music). Covers keep their own shape at a fixed height. Tests: `tests/test_shelves.py`.

## Phase 8D: Profile wishlist

From Phil, 2026-11-08. After 8C, since it reuses its rows.
- [x] The profile's wishlist grid becomes one side-scrolling row per section (Books / Movies / Music), each titled and linked to the wishlist page on that tab (`?show=`), the same partial as 8C's rows. Rows with nothing in them are left out. Done 2026-11-08 (`shelves.wishlist_shelves`, `test_profile_rows_per_section`); on a friend's profile the rows link to their wishlist page.

---

## Phase 9: More styles

**Parked** (Phil, 2026-11-08): the accent colour picker (8B.5) comes first; pick this up later.

From Phil, 2026-11-05. New choices next to House and Classic under Profile → Appearance. They come after Phase 8 because the Shelf style's video-store rack needs VHS records. Each style is a shape block and palettes in `styles.css` (as today), plus a scoped `[data-style=…]` stylesheet for structure, built on the 7.1 component classes. Do one style at a time, with the same headless sweep as 7.0.

### 9.1 Shelf (iBooks-style skeuomorphic) 🟢
Reference: `docs/skeuomorphic-inspo.jpg` (local only, git-ignored): the 2010 iPad iBooks shelf.
- [ ] Wood-grain page and shelves. Light mode = maple, dark = walnut. Texture as a small tiling image (self-made or CC0, in `static/`), or a CSS gradient approximation if that looks good enough.
- [ ] **Library grid as shelves:** covers only (title/author on hover/focus and in list view), fixed row height so a shelf ledge runs under each row (a per-card ledge that bridges the gaps), soft drop shadow on covers.
- [ ] Embossed toolbar and buttons (gradient, inset highlight), system sans with a light text shadow.
- [ ] **Video-store rack for VHS** (Shelf only; in House and Classic the Videos grid looks like the book grid): tapes spine-out in a rack, navy and marquee yellow, ticket-stub labels. Generic, no Blockbuster or other branding. Needs Phase 8. Candidate for the tape/sleeve cover: the parked film frame, `docs/parked/film-frame.css`.
- [ ] Forms, profile and admin pages stay plain-but-themed (wood frame, paper panels); only the library views go full skeuomorphic.

### 9.2 Outrun (80s neon) 🟢
- [ ] **Dark only:** the Mode setting is ignored (documented on the Appearance picker).
- [ ] Perspective neon grid behind the page (fixed pseudo-element, CSS gradients + `perspective`; no images, no literal scenery).
- [ ] Purple → orange gradient on the top bar and headings; glow (`text-shadow` / `box-shadow`) on headings, accents and focus only, never on body text.
- [ ] Angled card and button corners via `clip-path` (boxy 80s car livery), with contrasting stripes on buttons. `clip-path` also clips borders and focus outlines, so draw those inside the shape.
- [ ] An OFL display font for headings (e.g. Audiowide or Orbitron) in `static/fonts/`; body text stays readable (Courier Prime or a plain sans).
- [ ] Contrast check: text on the gradient and neon fills passes 4.5:1; animations respect `prefers-reduced-motion`.

**Done when:** each style renders every page in its modes at phone and desktop widths with a clean sweep; Shelf shows books on shelves and VHS in the rack.

---

## Phase 10: The archive fork (parked)

**Not planned yet.** It's listed so the idea isn't lost; nothing in Phases 0–9 depends on it. The plan is in [FORK-SPEC.md](FORK-SPEC.md). In short:
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
