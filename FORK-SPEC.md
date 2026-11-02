# FORK-SPEC: Libaraxia → archival catalog

Status: **draft** · Written 2026-11-01 · Owner: Phil

This is the plan for turning Libaraxia into two projects:

- **Libaraxia** (this repo) stays the personal library app and becomes the **upstream**. Shared features get built here first.
- **The archive fork** (working name `ARCHIVE_NAME`, see [§9](#9-open-decisions)) is a **downstream fork** for cataloguing a personal collection properly: item-level records, condition, provenance, accession numbers, exports to standard formats. It drops the Goodreads-style social layer.

Two core changes land in Libaraxia **before** the fork, so both projects get them:

1. **Sharp-edged restyle** in the shared house style of negativeearth.net, philcifone.com and photo.philcifone.com.
2. **VHS support**: scanning and cataloguing tapes by their barcode.

---

## 1. Is "upstream core, downstream fork" a real thing?

Yes. It's the standard **upstream/downstream fork** model, the same way distro packages track upstream projects or a company fork tracks an open-source project. The fork keeps a git remote called `upstream` pointing at Libaraxia and regularly merges from it. Fixes and shared features go upstream first and flow down.

It has one known failure mode: **drift**. Every file the fork edits that upstream also edits is a future merge conflict. The design below is mostly about keeping the fork's edits to shared files near zero:

| Rule | How |
|---|---|
| Fork-only code lives in fork-only files | New blueprints, templates, static files and migrations go in their own paths (see [§6.2](#62-fork-layout)). |
| Turning things off is config, not deletion | Upstream gets feature flags, so the fork hides social features by setting config instead of deleting files ([§3.2](#32-feature-flags)). |
| The fork plugs in, it doesn't patch | Upstream gets a small plugin hook in `create_app()`, so the fork registers its blueprints without editing `app.py` ([§3.3](#33-plugin-hook)). |
| Shared tables are extended, not altered | The fork adds new tables keyed to `books.id` instead of changing `books` ([§7.1](#71-data-model)). |
| One migration ledger, two streams | Upstream migrations stay `NNN_*.sql`, fork migrations use `A_NNN_*.sql`, and both are tracked by name in `schema_migrations` ([§3.1](#31-migration-runner-and-consolidated-schema)). |

**Where does a change go?** If it would make sense in a personal reading-library app, it goes in **Libaraxia** and gets merged down. If it only makes sense for archival cataloguing, it goes in the **fork**. Bugs in shared code always get fixed upstream.

**Later option, not now:** if merges start to hurt, pull the shared code (lookups, image handling, auth, DB helpers) out into an installable package, e.g. `libaraxia-core`, that both apps depend on. That is more work and more ceremony than one person needs today. Treat it as the escape hatch if the fork drifts too far. Don't start there.

---

## 2. Phases at a glance

| Phase | Where | What | Done when |
|---|---|---|---|
| 0 | Libaraxia | Commit current work, then foundations: migration runner, consolidated schema, feature flags, plugin hook, `base.html`, smoke tests | Fresh install works from scratch; tests pass |
| 1 | Libaraxia | Core change A: sharp-edged restyle | No rounded corners left; light + dark themes |
| 2 | Libaraxia | Core change B: VHS / UPC support | A VHS can be scanned, looked up (or entered by hand), filtered and displayed |
| 3 | both | Tag `v2.0.0`, create the fork | Fork repo exists with `upstream` remote and runs |
| 4 | fork | Strip the social layer (config only) and rebrand | Fork runs with feed/friends/wishlist/reading features off |
| 5 | fork | Archival data model and workflows | Accessioning, condition, provenance, locations, audit log |
| 6 | fork | Export, labels, preservation | Dublin Core / CSV / JSON export, printable labels, BagIt backups |

The restyle goes before VHS so the VHS screens are only built once, in the new style.

---

## 3. Phase 0: upstream foundations

These are worth doing for Libaraxia alone. In [ROADMAP.md](ROADMAP.md), the schema/runner/tests/`base.html` items are core work (Phases 1, 2 and 6), and feature flags + plugin hook are parked as fork prep (Phase 9). They matter more now because two codebases will depend on them.

**First:** the working tree has a large set of uncommitted changes from the 2026-10-28 security pass (renames into `docs/`, untracking `node_modules/`, blueprint fixes). Commit those before anything else so the fork starts from a clean, known point.

### 3.1 Migration runner and consolidated schema
*Scheduled as ROADMAP Phase 2.1–2.2.*

- Regenerate `create_database.sql` from a fully migrated DB (`sqlite3 library.db .schema`) so a fresh install is one command.
- Add a tiny runner, e.g. `python3 manage.py migrate`:
  - It keeps a `schema_migrations(name TEXT PRIMARY KEY, applied_at TIMESTAMP)` table.
  - It applies every file in `migrations/` that isn't recorded yet, in sort order, each one inside a transaction.
  - It backs up the DB first (`.backup library.db.pre-migrate_<date>`).
  - It marks 001–012 as already applied on existing databases (a one-off `--baseline` flag).
- **Naming rule:** upstream uses `migrations/NNN_name.sql` (013, 014, ...). The fork uses `migrations/A_NNN_name.sql`. Both live in the same folder and share the same ledger, so they never collide and order doesn't matter between streams.
  - Fork migrations may add tables and columns. They must never alter or drop upstream columns.

### 3.2 Feature flags
Add a `FEATURES` setting to `config.py`. Each flag is read from the environment with a default of on:

```python
FEATURES = {
    "social":    env_bool("FEATURE_SOCIAL", True),     # friends, feed, likes, notifications, friend search
    "wishlist":  env_bool("FEATURE_WISHLIST", True),
    "reading":   env_bool("FEATURE_READING", True),    # reading status, sessions, ratings/reviews, goals
    "household": env_bool("FEATURE_HOUSEHOLD", True),  # shared library / library_members
    "goodreads": env_bool("FEATURE_GOODREADS", True),
}
```

- In `app.py`, only register a blueprint if its flag is on.
- Expose `features` to Jinja through a context processor. `_sidebar.html` and the profile/detail pages wrap the matching links and panels in `{% if features.social %}` etc.
- Libaraxia ships with everything on, so this changes nothing for current users. The fork turns things off in its own `config` defaults.

### 3.3 Plugin hook
At the end of `create_app()`, load optional extension modules named in config:

```python
for name in app.config.get("PLUGINS", []):
    importlib.import_module(name).init_app(app)
```

An `init_app(app)` can register blueprints, add a context processor, add sidebar entries (via a list in `app.config["NAV_EXTRA"]` that `_sidebar.html` loops over), and extend lookups. This is the standard Flask extension pattern. Then the fork only sets `PLUGINS = ["archive"]` and never touches `app.py`.

### 3.4 `templates/base.html`
*Scheduled as ROADMAP Phase 6.*

There are 27 standalone templates today, each with its own `<head>`, font links and includes. Before restyling, add a base layout with `{% block title %}`, `{% block content %}` and `{% block scripts %}`, plus one `static/common.js` holding `getCSRFToken`, `escapeHtml` and `showFlashMessage`. Then move pages onto it one at a time. This turns the restyle from a 27-file job into a mostly-one-file job. It also gives the fork a single `{% block %}` to override for branding.

### 3.5 Smoke tests
Both repos will be merged into regularly, and merges need a quick "did I break it?" check. A small pytest suite is enough: `app.test_client()` against a temp DB built by the migration runner. Cover:

- register/login
- add/edit/delete a book
- the ownership checks
- ISBN and UPC lookup dispatch, with the network mocked
- every blueprint returning 200 or 302 with features on **and** off

Run it in CI (ROADMAP Phase 2.7).

### 3.6 Dependency upgrade
*Scheduled as ROADMAP Phase 1.2 🔴.* Do it before tagging v2.0.0 so the fork doesn't inherit known CVEs.

---

## 4. Phase 1: core change A, the sharp-edged restyle

### 4.1 The house style (taken from the live sites' CSS, 2026-11-01)

All three sites share one system. philcifone.com's tokens are the cleanest statement of it, and photo.philcifone.com and negativeearth.net use the same Gruvbox palette and fonts.

**Type**
- **Young Serif** for headings and body (`--font-text`). It's already in `static/fonts/young-serif/`.
- **Courier Prime** for labels, nav, metadata, numbers, buttons and code (`--font-mono`), in 400 and 700. It needs adding to `static/fonts/` (OFL licence).
- Drop **Outfit** and **Crimson Pro**. That means 20 templates reference them, plus `tailwind.config.js` and `styles.css`.

**Colour.** Gruvbox, with light ("paper") and dark themes that follow `prefers-color-scheme`:

| Token | Light | Dark | Use |
|---|---|---|---|
| `--paper` | `#fbf8f1` | `#1d2021` | page background |
| `--ink` | `#282828` | `#ebdbb2` | text |
| `--muted` | `#5a524c` | `#a89984` | labels, secondary text |
| `--rule` | `#d5c4a1` | `#504945` | hairlines, borders |
| `--accent` | `#79740e` | `#98971a` | links, focus, primary action |
| `--frame-fill` | `#f2ede1` | `#282828` | cards, cover frames, inputs |
| `--film` | `#1d2021` | `#121314` | "film strip" frames (covers, VHS sleeves) |
| `--film-ink` / `--film-accent` | `#d5c4a1` / `#b8bb26` | same | edge text and frame numbers on film frames |

Gruvbox extras seen on photo.philcifone.com: yellow `#d79921` (hover ink) and gray `#928374`. The current Libaraxia accent `#4f7d19` is close to Gruvbox green, so the shift is a natural one.

**Shape and rhythm**
- `--radius: 0` everywhere.
- `--hairline: 1px solid var(--rule)` for borders and dividers.
- Hard offset shadows instead of soft blurs, and only where depth is needed: `4px 4px 0` and `8px 8px 0` in near-black (photo site).
- Spacing scale `.25 / .5 / 1 / 1.5 / 2.5 / 4rem`. Fluid type steps `--step--1` … `--step-3`.
- `--measure: 66ch` for prose. `--page-width: 64rem`, with `--gutter: clamp(1rem, 4vw, 2rem)`.

**Voice and details** (this is what makes it read as "yours")
- Section labels: mono, uppercase, `letter-spacing: .08em`, muted, with a hairline underneath.
- Numbered, zero-padded markers: `01 — TITLE — 2022–PRESENT`.
- Nav as an index: `0:library*  1:collections*  2:archive*` (photo site), or mono uppercase links with an accent underline on the current page (philcifone.com).
- Bracketed counts: `All · [415]`. Arrows: `→` for internal links, `↗` for external, `▸` before filenames and captions.
- Links in accent with a 1px underline, offset `.2em`, 2px on hover. Focus: `2px solid var(--accent)`, offset `3px`.
- Lowercase wordmark.
- Covers shown like contact-sheet frames: a `--film` border with a mono "edge" caption under the image (e.g. `▸ 9780670671908` or the accession number).

### 4.2 Implementation
*Scheduled in two steps: ROADMAP Phase 0 (design refresh: tokens, fonts, radius, shadows, shared partials, done via `tailwind.config.js` without template edits) and Phase 7 (design polish: light theme, class cleanup, film-frame covers).*


1. **Kill rounding globally first, then clean up.** In `tailwind.config.js`, *replace* (don't `extend`) `theme.borderRadius` so every size is `0`. Keep one escape hatch, `full`, but don't use it for avatars (see below):
   ```js
   borderRadius: { none: '0', DEFAULT: '0', sm: '0', md: '0', lg: '0', xl: '0', '2xl': '0', '3xl': '0', full: '9999px' }
   ```
   That makes the existing ~384 `rounded-*` usages compile to square corners at once, without touching every template.
   - Then remove the classes as each page is touched: 246 × `rounded-lg`, 50 × `rounded`, 22 × `rounded-xl`, 19 × `rounded-md`, 47 × `rounded-full`, across 32 files, including 22 in `static/*.js` template strings.
   - **`rounded-full` decision:** square avatars (framed like photos), square FAB, square tag chips. Keep `full` only for tiny status dots, if any survive.
2. **Tokens.** Define the CSS variables from §4.1 in `static/styles.css` under `:root` and `@media (prefers-color-scheme: dark)`. Point the Tailwind colours at them (`paper: 'var(--paper)'`, `ink`, `muted`, `rule`, `accent`, `frame`). Then the theme switches without `dark:` variants.
   - Rename the old `primary`/`secondary`/`content` colours to the new names and replace them in templates. A temporary alias layer is fine during the sweep.
   - This also covers the old "Light theme or toggle" item.
3. **Fonts.** Add `@font-face` for Courier Prime 400/700. Set `fontFamily: { text: [...], mono: [...] }`. Remove Outfit and Crimson Pro files and links.
4. **Components** to restyle in `base.html` / partials:
   - `_sidebar.html`: becomes an index-style nav.
   - `_book_grid.html`: film-frame covers with mono edge captions.
   - `_flash_messages.html`: hairline box, mono label.
   - `_search_sort_filter.html`: hairline inputs, bracketed counts.
   - `_add_book_fab.html`: a square button with a hard shadow.
   - Buttons: hairline border, mono uppercase label, accent fill for primary actions, no radius.
5. **Hard-coded colours.** Remove inline hex and the `onmouseover` colour swaps (e.g. `#4f7d19` in `user.html`). (ROADMAP Phase 0.2)
6. **Viewport.** Fix `initial-scale=.8` → `1` while the heads are moving into `base.html` (ROADMAP Phase 0.5).
7. Run `npm run build:css` and commit `output.css`.
8. **Check every page in both themes.** Library grid, detail, add/edit, collections, profile, admin, auth, wishlist, feed, notifications, Goodreads import.

**Done when:** `grep -rE "rounded-(sm|md|lg|xl|2xl|3xl)|\brounded\b" templates static/*.js` returns nothing; no Outfit/Crimson references remain; light and dark both render correctly.

---

## 5. Phase 2: core change B, VHS support

### 5.1 What a "VHS ISBN" actually is
VHS tapes don't have ISBNs. Retail tapes carry a **UPC-A** (12 digits) or **EAN-13** barcode, and often a studio **catalogue number** printed on the spine/label (e.g. `VHS 1234`). Pre-1980s and rental-only tapes often have no barcode at all.

The scanner in `add_book.js`/`wishlist.js` already decodes `upc_reader` and `ean_reader`. Today, though, every scanned code is treated as an ISBN, so a VHS scan just returns "Book not found".

**Dispatch rule:**
- An ISBN is an EAN-13 starting `978` or `979`, or a valid ISBN-10. Those take the existing book path.
- Everything else (12-digit UPC, or EAN-13 with any other prefix) takes the new media path.

Normalize UPC-A to EAN-13 by left-padding a `0` for storage and comparison.

### 5.2 Schema (upstream migration `013_add_media_type.sql`)
Generalize the existing table instead of making a parallel one. The `books` table becomes "catalogue items of any medium", which is also the shape the fork wants.

```sql
ALTER TABLE books ADD COLUMN media_type TEXT NOT NULL DEFAULT 'book';  -- 'book' | 'vhs' (more later)
ALTER TABLE books ADD COLUMN barcode TEXT;           -- normalized EAN-13/UPC for non-book media
ALTER TABLE books ADD COLUMN catalog_number TEXT;    -- studio/label catalogue number
ALTER TABLE books ADD COLUMN runtime_minutes INTEGER;
CREATE INDEX idx_books_media_type ON books(media_type);
CREATE INDEX idx_books_barcode ON books(barcode);
```

- **Field reuse for VHS:**

  | Column | Book | VHS |
  |---|---|---|
  | `author` | author | director / creator |
  | `publisher` | publisher | studio / distributor |
  | `publish_year` | year published | release year of *this* tape edition |
  | `page_count` | page count | NULL |
  | `cover_image_url` | cover | sleeve front |

  The UI relabels fields by `media_type`. Keep the labels in one place, e.g. `utils/media.py: FIELD_LABELS[media_type]`, used by templates and JS.
- Keep the table name `books` for now. Renaming it would touch every query, and it isn't worth the merge pain. Revisit only if the package extraction in §1 ever happens.
- **Append the new columns at the end.** Templates still index rows by position (`book[0]`, `book[8]`), so columns must not be reordered. Better still, finish the named-access item (ROADMAP Phase 6) first.
- Fold the migration into `create_database.sql` (§3.1).

### 5.3 Lookups (`utils/media_lookup.py`, new)
Media barcode coverage is patchy, so design for **manual entry first, lookup as a bonus**:

| Source | Lookup by | Gives | Notes |
|---|---|---|---|
| UPCitemdb | UPC/EAN | title (often messy: `"Jaws [VHS]"`), brand, images | Free trial endpoint with no key, rate-limited. Check the current limits. |
| TMDb | title + year (from the UPC result, or typed) | director, year, runtime, synopsis, poster | Needs `TMDB_API_KEY`. Film metadata only, not tape-edition data. |
| Discogs | barcode | music-video VHS: label, catalogue number, year | Needs `DISCOGS_TOKEN`. Has a `VHS` format. |

- **Flow:** UPC → UPCitemdb → clean the title (strip `[VHS]`, `(VHS)`, `VHS`, edition noise) → TMDb search for metadata → merge, keeping the tape-specific fields (studio, barcode) from the UPC result.
  - If nothing matches, return the code and open the form pre-filled with `media_type='vhs'` and `barcode` set.
- **Security:** every request goes through `book_utils._get_public()` and every image through `_fetch_image()` / `save_best_cover()` (SSRF guard, CLAUDE.md). API keys come from `.env`, added to `.env.example`. Keys are **optional**: with none set, the feature is manual entry plus whatever UPCitemdb returns.
- Log errors and return generic messages to the client, not `str(e)` (CLAUDE.md).

### 5.4 Routes and UI
- `GET /books/fetch_barcode_details?code=…` replaces direct use of `fetch_isbn_details`. It dispatches per §5.1 and returns `{"success", "media_type", "book_details"}`. Keep `fetch_isbn_details` as a thin alias so nothing else breaks.
- **Add form:** a media-type selector (Book / VHS). Labels and visible fields switch (pages ↔ runtime, ISBN ↔ barcode + catalogue number). Scanning sets the type automatically.
- **Duplicate check** (`/books/check_duplicates`): match on `barcode` as well as `isbn`.
- **Library filter:** a `media_type` filter in `_search_sort_filter.html` / `get_filter_options`. Show a small mono `VHS` badge on grid cards. In the new style, a VHS sleeve gets the `--film` frame.
- **Detail and edit pages:** show runtime, barcode and catalogue number for VHS. Hide page count.
- **Goodreads import and stats:** stay book-only. Stats that sum pages must ignore non-book rows.
- **Wishlist:** the scanner dispatch applies there too (`wishlist.js`). The `wishlist` table may need a matching `media_type`/`barcode`; decide during implementation.

**Done when:** scanning a retail VHS either fills the form from a lookup or opens it pre-set to VHS with the barcode filled in; a saved VHS shows in the grid with a badge, filters correctly, and its detail page shows runtime/studio/barcode; book flows are unchanged (smoke tests).

---

## 6. Phase 3: creating the fork

### 6.1 Mechanics
GitHub won't let you fork your own repo into the same account, so make it a separate repo with a manual `upstream` remote. Git treats this exactly like a fork.

```bash
# in Libaraxia, once phases 0–2 are merged and tests pass
git tag -a v2.0.0 -m "Restyle + VHS; fork point for ARCHIVE_NAME"
git push origin v2.0.0

# create an empty repo philcifone/ARCHIVE_NAME on GitHub, then:
git clone git@github.com:philcifone/libaraxia.git ARCHIVE_NAME
cd ARCHIVE_NAME
git remote rename origin upstream
git remote add origin git@github.com:philcifone/ARCHIVE_NAME.git
git remote set-url --push upstream NO_PUSH   # can't accidentally push the fork into Libaraxia
git push -u origin main --tags
```

**Syncing** (best practice is to merge upstream **tags**, not random `main` commits):
```bash
git fetch upstream --tags
git merge v2.1.0            # merge, don't rebase: the fork's history is published
python3 manage.py migrate   # picks up any new upstream migrations
pytest
```

**Rules**
- Tag Libaraxia releases with semver. `MAJOR` = a breaking schema change or a removed feature. The fork pins to and merges tags.
- When a fork change turns out to be general, re-implement or `git cherry-pick` it into Libaraxia, then merge it back down. Don't let the fork become the only home of shared code.
- Separate deployments and separate databases. The fork never opens Libaraxia's `library.db`.
- GPLv3 carries over, and the fork stays GPLv3. That's fine, since you own both.

### 6.2 Fork layout
Everything fork-specific lives under paths upstream will never touch:

```
archive/                    # the plugin package: init_app(app) registers everything below
  __init__.py
  blueprints/               # accession, items, locations, exports, labels
  templates/archive/
  static/archive/
  lookups.py                # extra metadata sources (LoC, OCLC, Wikidata …)
migrations/A_001_*.sql      # fork migrations, same folder and ledger as upstream
config_archive.py           # FEATURES off, PLUGINS = ["archive"], branding
ARCHIVE.md                  # fork-specific CLAUDE.md addendum
```

Files the fork **is allowed** to edit in shared code:
- `README.md`, `CLAUDE.md`, `ROADMAP.md`. Expect conflicts on these and resolve them by keeping the fork's version.
- `base.html` blocks via template inheritance. Override, don't edit.

Anything else is a smell. Add an upstream hook instead.

---

## 7. Phases 4–6: the archive fork

### 7.0 Phase 4: strip and rebrand
- **Features off:**
  - `social`: friends, feed, likes, notifications, friend search
  - `goodreads`
  - `reading`: status/sessions/ratings; maybe keep as a private "notes" field, see §9
  - `household`: keep if more than one cataloguer is wanted
- **Wishlist:** becomes **desiderata** (wanted items). Keep the feature, relabel it in the fork's templates.
- **Roles:** reuse `is_admin`. Add `role` (`admin` | `cataloguer` | `viewer`) in a fork migration if others will use it.
- **Branding:** name, wordmark, and an index-style nav: `0:catalogue* 1:accessions* 2:locations* 3:export*`.

### 7.1 Data model
Libaraxia's `books` row is one record per title. Archives separate the **description of a thing** from **each physical copy**, following IFLA LRM / FRBR: *work → manifestation → item*. That separation is the fork's central change.

- **Manifestation:** the existing `books` row, i.e. "this edition / this tape release". It's shared with upstream and untouched, so merges stay clean.
- **Item:** a new `items` table. One row per physical copy you hold.

```sql
-- A_001_items.sql (sketch)
CREATE TABLE items (
  id INTEGER PRIMARY KEY,
  book_id INTEGER NOT NULL REFERENCES books(id),
  accession_number TEXT NOT NULL UNIQUE,      -- e.g. 2026.0042 (year.sequence), never reused
  copy_number INTEGER DEFAULT 1,
  status TEXT NOT NULL DEFAULT 'held',        -- held | on_loan | in_conservation | deaccessioned | missing
  location_id INTEGER REFERENCES locations(id),
  condition_grade TEXT,                       -- controlled list, see below
  condition_notes TEXT,
  physical_description TEXT,                  -- binding/format, dimensions, extent
  edition_statement TEXT,                     -- "First edition, third printing" / "Rental release"
  inscriptions TEXT,                          -- signatures, marginalia, bookplates, stickers
  provenance TEXT,                            -- ownership history
  acquisition_date DATE,
  acquisition_source TEXT,                    -- shop, person, estate, gift
  acquisition_method TEXT,                    -- purchase | gift | trade | found | inherited
  acquisition_price_cents INTEGER,
  insured_value_cents INTEGER,
  notes TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP
);
CREATE TABLE locations (id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES locations(id),
  code TEXT UNIQUE, label TEXT);               -- room > case > shelf > box
CREATE TABLE identifiers (book_id INTEGER REFERENCES books(id), scheme TEXT, value TEXT,
  PRIMARY KEY (book_id, scheme, value));       -- isbn10/isbn13/upc/lccn/oclc/issn/catalog/wikidata
CREATE TABLE subjects (id INTEGER PRIMARY KEY, scheme TEXT, term TEXT, uri TEXT);  -- LCSH etc.
CREATE TABLE book_subjects (book_id INTEGER, subject_id INTEGER, PRIMARY KEY (book_id, subject_id));
CREATE TABLE item_images (id INTEGER PRIMARY KEY, item_id INTEGER REFERENCES items(id),
  role TEXT,                                   -- front | back | spine | inscription | damage | label
  master_path TEXT, derivative_path TEXT, sha256 TEXT, width INTEGER, height INTEGER,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE audit_log (id INTEGER PRIMARY KEY, user_id INTEGER, table_name TEXT, row_id INTEGER,
  action TEXT, changes_json TEXT, at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE loans (id INTEGER PRIMARY KEY, item_id INTEGER REFERENCES items(id),
  borrower TEXT, out_date DATE, due_date DATE, returned_date DATE, notes TEXT);
```

**Condition vocabularies** (controlled lists, stored as codes):
- **Books:** the ABAA/ILAB scale: As New, Fine, Near Fine, Very Good, Good, Fair, Poor. Dust jacket is graded separately.
- **VHS:** a separate grade for tape, shell, sleeve and case, plus a "plays / untested / damaged" flag.

### 7.2 Phase 5: archival workflows
- **Accessioning:**
  - "Add item" either creates a new manifestation (via the shared ISBN/UPC lookup) or attaches a copy to an existing one.
  - The accession number is assigned automatically (`YYYY.NNNN`) and is immutable once saved.
- **Deaccession, not delete.** Items are never hard-deleted. Deaccessioning records a reason, a date, and the disposition (sold/gifted/discarded). Upstream's delete route stays hidden in the fork.
- **Audit log.** Every insert/update/deaccession on fork tables writes to `audit_log`, with a "history" panel on the item page.
- **Locations:** a hierarchy with "move item(s) to…" and a shelf-list view per location.
- **Images:**
  - The upload **keeps the original master untouched**: no resize, SHA-256 recorded, stored under `static/uploads/masters/`. A resized derivative is made for display.
  - Upstream's `process_image` resizes destructively. The fork wraps it rather than changing it, or upstream grows a `keep_original=True` option.
  - Several images per item, each with a role.
- **Identifiers and subjects:**
  - The `identifiers` table holds every scheme. Upstream's `isbn` / `barcode` columns are mirrored in on save.
  - Optional Library of Congress (id.loc.gov) lookups for LCCN and subject headings, and Wikidata QIDs for creators.
- **Batch cataloguing:** scan many barcodes in a row into a "to process" queue, then catalogue each one at the desk.

### 7.3 Phase 6: export, labels, preservation
- **Exports:**
  - CSV (flat, one row per item)
  - JSON (full nested record)
  - **Dublin Core** XML (`oai_dc`) per manifestation
  - Optionally MARCXML later, via `pymarc`, if the catalogue will ever leave the app
- **Printable labels:** spine/box labels with accession number, short title and a Code 128 or QR code that links to the item page, in Courier Prime. Print as a PDF sheet.
- **Backups:** a one-click **BagIt** bag (DB snapshot from `sqlite3 .backup`, plus masters, plus a `manifest-sha256.txt`). Optionally a fixity check that re-hashes masters and reports mismatches.
- **Public catalogue (later, optional):** a read-only, no-login view of selected items, i.e. an OPAC. Off by default.

---

## 8. Risks

| Risk | Mitigation |
|---|---|
| Fork drifts and merges become painful | Plugin hook and feature flags (§3); fork-only paths (§6.2); merge upstream tags often, while the diffs are small; package extraction as the escape hatch (§1). |
| Migration collisions between streams | Named ledger plus the `A_` prefix (§3.1). Fork migrations never alter upstream columns. |
| Positional row access breaks when columns are added | Append-only columns (§5.2). Finish the named-access cleanup (ROADMAP Phase 6) before or during Phase 2. |
| VHS lookups mostly miss | Manual entry is the primary path, by design (§5.3). |
| A Phase 0 migration runner run against the wrong DB file | CLAUDE.md load-order caveat: confirm which DB prod opens before the first `migrate`, and the runner always backs up first. |
| Data loss in the archive | No hard deletes; audit log; masters kept with checksums; BagIt backups. |

---

## 9. Open decisions

1. **Fork name.** Placeholder `ARCHIVE_NAME`. Something short and lowercase fits the house style.
2. **Users:** single-cataloguer, or a small team with roles?
3. **Reading data in the fork:** drop it entirely, or keep a private "notes / read" field per manifestation?
4. **Accession format:** `YYYY.NNNN` (museum style) or a plain running number?
5. **More media after VHS:** DVD, LP, cassette, CD, zine, ephemera, photographs. The `media_type` column allows them; decide which get first-class lookups (Discogs covers LP/CD/cassette).
6. **Theme default:** follow the system (like philcifone.com), or force dark for Libaraxia and light/paper for the archive?
7. **Public catalogue:** ever, or never?
