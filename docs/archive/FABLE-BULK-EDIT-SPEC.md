# Fable Bulk Edit Spec

Status: DRAFT for tightening. This fleshes out ROADMAP Phase 14 (bulk edit and
granular Goodreads import). If it goes ahead, the ROADMAP phase links here and
its checklist is replaced by the build order at the end of this file.

## Goal

Let a user select many items on a grid and change them in one go, without ever
being surprised by the result. The motivating case: a lot of cookbooks carry a
wrong genre ("Cooking", "Cookbook", "Cookery", empty). Select them all, set one
genre, done.

The same machinery then serves the granular Goodreads import (Phil's second
use): after parsing the CSV, show every row beside what the library already
holds, let the user decide per row and per field, and only then write.

The design goal in one sentence: **nothing is written until the user has seen
exactly what will change, and anything that was written can be taken back.**

## Constraints (carried over from CLAUDE.md and ROADMAP 14)

- Raw `sqlite3`, no ORM, no new dependencies, no CDN, no inline JS (CSP;
  `tests/test_csp.py` enforces it). Vanilla JS in `/static/`, wired with
  `data-click` / `data-change` / `data-submit` and `registerActions`.
- Every write is a POST with CSRF. Ownership is checked in the SQL, per item,
  on the server. The browser only ever says "these ids, this action"; it never
  names a column, a table or a path.
- Reuse the existing rules, do not fork them: `models.can_view_book`,
  `media.is_valid_status`, `media.FORMATS`, `book_utils.on_shelf()` /
  `shelf_filter()`, `utils/book_matching.py`.
- Works with the keyboard and at 375 px wide. All four themes (House, OG,
  Outrun, Shelf), both modes: use the semantic classes, add no raw colours.
- No emojis in docs or markdown. Comments explain why.

## What is already true (from reading the code)

These shape the design, so they are stated up front.

1. **Editing an item is owner-or-admin** (`books.edit_book`,
   `media_section` edit). A household member viewing the shared shelf can see a
   book they do not own but cannot edit it. Bulk edit inherits this: on the
   Household view, rows owned by someone else are reported "skipped: not
   yours", never silently changed.
2. **Your own marks are a different class.** Status, tags, custom-shelf
   membership and wishlist entries belong to the user, are keyed by
   `(user_id, book_id)`, and are allowed on any book `can_view_book` passes.
   The single-item status route already works this way. So the actions split
   in two (see "Actions").
3. **`books.genre` is free text.** Stats group by `LOWER(genre)` and the grid
   filter compares `LOWER(genre)`, so "Cooking" and "cooking" merge in some
   places and are separate in the picker. A bulk genre field must therefore
   nudge towards spellings that already exist.
4. **The feed is built at query time from `collections.created_at`**
   (`blueprints/feed.py`). Setting a status on 47 items would announce 47
   "started reading" lines to every friend. The Goodreads import dodges this by
   writing the Goodreads Date Added into `created_at`. Bulk status needs its own
   answer (see "Feed side effects").
5. **Grids infinite-scroll** (`script.js`, JSON pages of 30 to 100), so "select
   all" cannot mean "tick every card in the DOM".
6. **The query-building for a grid is duplicated** between `base.library_page`
   and `media_section.grid_page` (search, genre, status, rating, tags, `Show`).
   "All items matching this view" needs that logic in one place.
7. **The Goodreads importer already has the right shape** for half of this: one
   SAVEPOINT per row, one outcome per row, "never overwrite" as the rule
   (`utils/goodreads.py`). It just decides and writes in the same pass.

## The core idea: plan, review, apply, undo

Every bulk operation, whatever the action, goes through four steps, in code
(`utils/bulk.py`) and in the UI:

1. **Plan** (read only). Given the user, an action, its parameters and a set of
   item ids, compute one `PlanRow` per item: what is there now, what it would
   become, and an outcome: `change`, `same` (already that value, nothing to
   do), `blocked` (with a reason: not yours, not valid for this type, removed),
   or `conflict` (there is a value the user might not want lost). Pure function
   of the database; no writes; cheap to call repeatedly.
2. **Review.** The plan is shown before anything happens: counts per outcome
   and a table of the rows with before and after. Conflicts default to *leave
   as it is* and can be flipped per row. The user presses "Apply 44 changes".
3. **Apply.** The browser posts the action, the parameters, the ids and a plan
   fingerprint. The server re-plans (the data may have changed since the
   preview), refuses if the fingerprint no longer matches, then writes the
   plan in one transaction, one SAVEPOINT per item (a failing item leaves
   nothing behind and is reported, the rest carry on, exactly as the Goodreads
   importer does). The apply step never trusts the preview's content, only the
   user's decisions (which conflict rows to overwrite).
4. **Undo.** Every apply writes a journal (below). The result banner offers
   Undo, and Profile keeps a short history for a while.

Why preview-then-apply rather than "apply, then offer undo": undo is the safety
net, preview is the guard rail. A guard rail stops the cookbook case going
wrong for the 3 books that were correctly "Reference" and got swept in; undo
alone makes the user notice after the fact. Both are cheap once the plan exists.

### Overwrite modes (the "don't overwrite by accident" control)

Every field action takes a mode, shown as a two-way choice beside the value:

- **Fill empty only** (default): items that already have a value are `same` or
  `conflict`-free `blocked: "already has a genre"`; they are not touched.
- **Replace**: items with a different existing value are `conflict` rows in the
  review (before shown next to after), and are written only if the review's
  checkbox for that row is on. A "select all conflicts" toggle is there, but
  Replace never writes over a differing value without it having been on screen.

Items with no existing value are plain `change` in both modes. For the cookbook
case you would pick Replace, review "Cooking -> Cookbooks" for 38 rows, see the
2 that say "Reference", untick them, apply.

## Selecting

### Select mode on the grids

An **Edit** toggle in the view bar (`_view_bar.html`), on Shelves in every
section (own, household, a friend's is read-only so it does not show), search
results, a status collection, a custom shelf. Entering it:

- Each card gets a checkbox; tapping the card (or the cover) toggles instead of
  navigating. The card's normal links are inert in select mode, so a mis-tap
  cannot open a page and lose the selection.
- Shift-click selects a range; Ctrl/Cmd-click toggles one; Space toggles the
  focused card, arrow keys move focus (cards become a roving-tabindex listbox
  with `aria-multiselectable`). Escape leaves select mode.
- A sticky bottom bar (above the FAB, below the sidebar's z-index): count,
  "Select all", "Clear", and the action menu. On phones the bar is a
  full-width strip with the actions behind one "Actions" button.
- Select mode is a class on `#book-container` next to `data-view`, so grid,
  list and the Shelf theme's cover boxes all get it from CSS, not from a
  parallel template.
- The selection is a `Set` of ids in JS. It survives infinite scroll (newly
  loaded cards check themselves against the set). It is cleared when the
  filters, search or tab change, because a selection that silently outlives the
  view it was made in is how the wrong things get edited.

### "Select all" means all matching, not all loaded

"Select all" first selects what is loaded, then offers "Select all 212 items in
this view" (the Gmail pattern). The latter sends the view's query string (the
same `?search_term=&genre=&show=...` the grid uses) and the count the user saw,
not 212 ids:

- Server: `utils/grid_query.py` (new) holds the one implementation of "the rows
  this grid shows for this viewer and these args", extracted from
  `library_page` and `grid_page` with no behaviour change (tests pin it first).
  It returns ids. The bulk endpoint calls it with `ids_from_view=<qs>`, checks
  the count equals what the user was shown (`expected_count`), and refuses with
  "the view changed, reload" if not.
- Hard cap of **500 items per operation**, on explicit ids and on resolved
  views. Over the cap the bar says "Too many to edit at once, narrow the view"
  rather than truncating. Reason: bounded transaction time (SQLite has one
  writer; a 10 000-row write would block every other request) and a bounded
  blast radius.

## Actions

Two classes. The plan reports class and permission per item.

### Item edits (changes the `books` row; owner or admin)

| Action | Detail |
|---|---|
| Set genre | Free text with a picker of existing genres and their counts (see below). Applies to all three media types. Empty value clears (needs the confirm checkbox, see "Confirmations"). |
| Set format | Only values valid for each item's own type (`media.FORMATS`); a mixed-type selection is allowed and rows whose type does not offer the value are `blocked: "not a format for Movies"`. Books: Book / Audiobook (`media.book_format`). Changing a book to Audiobook does not change `owned`; the review notes that audiobook page counts stop counting. |
| Owned / not owned | `books.owned`. Review lists the ones that would leave the shelf. |
| Remove from library | Deaccession: sets `removed_at` and `removed_note` (one note for all). Reviews survive (data principles). Already-removed rows are `same`. Restore is the reversal and is undoable. Hard delete is **not** a bulk action: it has the "other users have data on it" check and exists for mistakes, one at a time. |
| Restore | The inverse, available when the view shows removed items. |

Candidates for later, same machinery, not v1: publisher, year, author
(find-and-replace), subtitle. Author and title are excluded from v1 on purpose:
they feed matching (`book_matching.py`) and wishlist/duplicate detection, and a
mass rewrite of them is the likeliest way to break the catalog quietly.

Whitelist, not pass-through: `FIELDS = {'genre': Field(column='genre',
clean=clean_genre, applies_to=ALL), 'format': Field(...), ...}` in
`utils/bulk.py`. The request carries the key `'genre'`; the column name in the
SQL comes from the table, never from the request.

### My marks (per-user rows; any item `can_view_book` allows)

| Action | Detail |
|---|---|
| Set status | Only statuses valid for each item's type (`media.is_valid_status`); others `blocked`. Items that already have a different status are `conflict` under Replace, `same`/`blocked` under Fill empty. "No status" (`untracked`) clears. |
| Add to / remove from a custom shelf | The selection's section's shelves only (`user_collections.media_type`); items of another type are `blocked`. `INSERT OR IGNORE`, so already-in is `same`. Offers "New shelf..." inline. |
| Add / remove a tag | `book_tags`, existing tags suggested; tag text cleaned the way `tags.py` does. |
| Add to / remove from wishlist | Not v1 (it creates rows in `books` territory and has its own household-match rules). Listed so nobody wonders. |

A status of `read` / `watched` / `listened` set in bulk does **not** create a
reading session or ask for a rating: those are per-read facts the user has not
supplied. The single-item flow redirects to the review page with the finished
date offered (ROADMAP 12.3); bulk deliberately does not. The review states
"No reading dates will be added". (Setting dates in bulk is the Goodreads
import's job, where the dates exist.)

### Genre picker

- `GET /bulk/genres?type=` returns the user's genres with counts, folded
  (case- and accent-insensitive via `search.fold`), most common first, each
  showing its most common spelling. Rendered as an input with a listbox (not a
  bare `<datalist>`, which cannot show counts on every browser).
- Typing a value that case-insensitively matches an existing one switches to
  that spelling and says so ("Using existing spelling 'Cookbooks'"). A new
  value is allowed and labelled "new genre".
- `clean_genre`: trim, collapse inner whitespace, cap length (80), reject
  control characters. No title-casing (Phil's "Sci-Fi" stays "Sci-Fi").
- Consequence worth knowing: the grid's existing `?genre=` filter plus Select
  all plus Set genre already covers rename and merge ("every item whose genre
  is 'Cooking' becomes 'Cookbooks'"), so a separate Genres manager page is not
  planned. Revisit if Phil finds himself doing this a lot.

## The review step

A modal sheet (a full-height sheet on phones) over the grid, built once and used
by every action and by the import (see below):

- Summary line with counts, colour-and-text coded so it is not colour-only:
  "44 will change, 3 already set, 2 need a decision, 1 skipped".
- Table: cover thumb (via `coverSrc`), title and creator, Before, After,
  Outcome. Sortable by outcome so the surprising rows sit on top. Blocked rows
  carry their reason in words ("Not yours", "Not a format for Movies",
  "Already removed").
- Conflict rows have a checkbox, off by default, plus a header checkbox.
- Primary button "Apply 44 changes" (count updates as conflicts are ticked);
  Cancel closes with nothing written. Focus is trapped in the sheet and returns
  to the action bar on close.
- Plans over about 50 rows paginate client-side inside the sheet; the
  summary always covers all rows.

Preview endpoint is `POST /bulk/plan` (POST because the id list can be long and
it carries CSRF; it writes nothing, and says so in the code).

### Confirmations

Beyond the review itself, a typed or ticked confirmation only where the change
is hard to see the cost of: clearing a field on many rows, and removing
from the library (which also asks for the note). Everything else relies on
review plus undo; extra "are you sure" dialogs on top teach people to click
through them.

## Undo and the journal

Two tables (migration, folded into `create_database.sql` and the ledger per
`migrations/README.md`; take the next free number at the time, 030 is
reserved for ROADMAP 15.1):

```sql
CREATE TABLE bulk_edits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    action TEXT NOT NULL,            -- 'genre', 'status', 'shelf_add', ...
    summary TEXT NOT NULL,           -- 'Genre -> Cookbooks, 38 items'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    undone_at TIMESTAMP
);
CREATE TABLE bulk_edit_items (
    edit_id INTEGER NOT NULL REFERENCES bulk_edits(id) ON DELETE CASCADE,
    book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    old_value TEXT,                  -- NULL = there was nothing
    new_value TEXT,
    PRIMARY KEY (edit_id, book_id)
);
```

- One journal row per applied item, written in the same SAVEPOINT as the
  change, so the journal can never disagree with the data.
- **Undo is guarded, not blind.** `POST /bulk/<id>/undo` re-plans in reverse:
  an item is restored only if its current value still equals `new_value`. If
  the user (or a later bulk edit) changed it since, that item is skipped and
  reported ("3 restored, 2 changed since, left alone"). This is the same rule
  as the forward direction: never overwrite something the user did not just
  see.
- Everything is reversible by construction: genre/format/owned store the old
  column value; status stores old status or absence; shelf and tag adds are
  undone by removing exactly the rows the edit created (`old_value` = absent),
  not rows that already existed; removal stores nothing beyond `removed_at`
  becoming NULL again.
- Retention: 30 days, swept lazily on the next bulk apply (no new scheduler).
  A hard-deleted book's journal rows go with it (FK cascade).
- Where it shows: the result banner ("38 changed. Undo") for as long as the
  page is open, and Profile -> "Recent bulk edits" (last 10, with Undo on the
  ones not yet undone). A second Undo of the same edit is refused
  (`undone_at`).

## Feed side effects

Bulk edits must not spam friends. Plan:

- Genre, format, owned, removal and tag/shelf changes are invisible to the feed
  already (it reads `books.created_at`, `collections`, `read_data`, wishlist).
- **Status inserts are the problem** (fact 4). Add `collections.quiet INTEGER
  NOT NULL DEFAULT 0` (same migration); bulk and import inserts set it to 1;
  the feed's `collections` query adds `AND c.quiet = 0`. Changing an existing
  row's status does not re-announce today, so it does not need the flag. The
  Goodreads import then no longer needs to forge `created_at` to hide itself,
  though it keeps writing Date Added because it is the truthful date.
- Assumption stated rather than asked: quiet is right for bulk status. If Phil
  wants bulk "finished" items to appear, that is a one-line change to the
  flag's default.

## Granular Goodreads import (built on the same pieces)

Today `import_goodreads` parses, matches and writes in one pass and returns a
report afterwards. Split it:

1. **Parse + plan** (`POST /user/import_goodreads/plan`, replaces the single
   POST; same 3/hour limiter semantics, now counting the apply not the plan).
   The CSV is parsed (`parse_row`) and each row matched against the user's own
   books and household (`BookIndex`, never anyone else's). Rows are stored in a
   staging table, not sent back and forth through the browser and not kept in
   the cookie session (too big, and the browser should not be the source of
   truth for what is being imported):

   ```sql
   CREATE TABLE import_staging (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
       created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
       rows_json TEXT NOT NULL        -- the parsed rows, capped (say 5000)
   );
   ```
   One staging row per user (a new upload replaces the old), expires after 24
   hours, swept on the next upload. The file size limit for uploads stays.
2. **Review grid** on the shared review sheet, but full page, not a modal. One
   row per CSV row with: title, author, Goodreads shelf, rating, Date Read,
   and the **match** ("New", "In your library", "In your household's library",
   "On your wishlist") and the **destination**, defaulted from today's rules:
   - Library with status (read / currently reading / DNF)
   - Wishlist
   - Library, not owned (audiobooks default here)
   - Skip
   Sortable and filterable by shelf, match, outcome; select all in the view;
   bulk-set destination for the selected rows (this is the "select-mode
   pieces" Phil's ROADMAP item names: it is the same selection bar over the
   same row component, the cards being rows instead of covers).
3. **Conflicts are fields, not rows.** Where the book already exists, the grid
   shows the three things the importer could write and the library already
   holds side by side: status, rating, review/dates. Each differing field
   defaults to **keep mine** and can be flipped to **use Goodreads** per row
   (bulk flip for a selection). This replaces "the import never overwrites,
   rows silently become 'already'" with "the import never overwrites unless
   told, and shows you what it skipped".
   - The wishlist-then-read case from the ROADMAP is its own outcome, "On
     your wishlist, Goodreads says read", with the destination choices
     *Move to library as read*, *Mark read, keep wished for*, *Skip*, and the
     default **Ask** (the row blocks "Import" until chosen; a header filter
     "Needs a decision" lists them).
   - Collections (Goodreads shelves other than the exclusive ones) appear as a
     mapping panel above the grid: each Goodreads shelf name -> an existing
     custom shelf, a new shelf of that name, or ignore.
4. **Apply** (`POST /user/import_goodreads/apply`): the chosen destination and
   field choices per row, row ids only (the data is in staging). The existing
   `_Importer` logic, now driven by the per-row decision instead of deciding
   for itself, still one SAVEPOINT per row, one outcome per row, summary at
   the end with exactly one outcome per CSV row (the invariant
   `tests/test_goodreads.py` already asserts), journalled so the whole import
   can be undone too (books it created are removed only if nothing else hangs
   on them, by the same rule as hard delete).
5. Covers: the export has no cover URLs, so the result screen keeps starting
   the background `cover_jobs` fetch.

The default path stays one click for people who do not want a grid: "Import
everything with the defaults" runs plan then apply with the default decisions
and unresolved "Ask" rows skipped, giving today's behaviour. The new grid is
the "Review before importing" path.

## Back-end structure

- `utils/bulk.py` (new): `FIELDS` whitelist, `PlanRow`, `plan(conn, user,
  action, params, ids)`, `apply(conn, user, plan, accepted_conflicts)`,
  `undo(conn, user, edit_id)`, fingerprint (a hash of the plan rows'
  `(id, before, after, outcome)`), the sweeps. No Flask imports: takes a
  connection and a user, like `utils/households.py`, so tests drive it
  directly.
- `utils/grid_query.py` (new): the shared grid query (see fact 6). Extracted
  first, with tests, before any bulk work.
- `blueprints/bulk.py` (new, `/bulk`): `POST /plan`, `POST /apply`,
  `POST /<id>/undo`, `GET /genres`, `GET /history`. All `@login_required`,
  per-user rate limit (60 plans and 30 applies per hour: generous for a human,
  tight for a script), JSON in and out per the API response pattern. Register
  in `app.py`.
- Templates: `_bulk_bar.html` (action bar), `_bulk_review.html` (the sheet,
  also used by the import page). JS: `bulk.js` (selection, bar, review sheet,
  fetches) loaded on grid pages; the import grid gets its own small
  `goodreads_review.js` using the same sheet component. Page scripts read
  server values from `data-` attributes.
- Errors: log with `current_app.logger`, return a generic message, never
  `str(e)` (CLAUDE.md). Validation failures (unknown action, bad value, over
  the cap) are specific and user-written, as in `ImportFileError`.
- Transactions: the apply runs under `get_db()`, one `BEGIN`, SAVEPOINT per
  item, a single `commit()` at the end. A 500-row apply is a few milliseconds
  of SQLite work; the cap keeps it that way. `PRAGMA foreign_keys = ON` already.
- Concurrency: the fingerprint guards the preview-to-apply gap (another tab, a
  household member editing a shared item). Because plan is recomputed at apply
  time, a stale preview cannot write stale "after" values.

## Security and access checklist

- Ownership/permission decided **in SQL per item** at plan and again at apply:
  item edits `WHERE id = ? AND (added_by = ? OR ?admin)`; marks via
  `can_view_book`. A forged id list can only ever produce `blocked` rows.
- `ids_from_view` resolves through the same viewer-scoped query the grid uses,
  so it cannot reach rows the viewer's grid would not show; household and
  friend views resolve with their `owner_ids` rules, and a friend's shelf is
  read-only (no Edit toggle, and the endpoint refuses item edits on it).
- Strict input validation: action and field from the whitelist; status, format
  and shelf checked against the lookup tables and per-item type; genre/tag
  cleaned and length-capped; counts capped at 500.
- No path or URL fields exist in any bulk action, so the image-path and SSRF
  rules are not engaged. (If "set cover" is ever added it must go through
  `is_safe_upload_path`.)
- Admins: may edit any item, but the Edit toggle only operates on the admin's
  own views; there is no "bulk edit the whole database" surface. Admin
  placeholder-cover cleanup keeps its own page.
- The audit trail is the journal: who, what, when, old and new values.

## Tests (every bug fix and route gets a test, per CLAUDE.md)

- `tests/test_bulk.py`, using the `people` fixture:
  - plan is read-only (row counts and `PRAGMA data_version`-style before/after
    comparison identical);
  - Fill-empty vs Replace outcomes; conflict rows are untouched unless
    accepted;
  - alice (owner) edits her books, bob (household, not owner) gets `blocked`
    on alice's shared books but can set his own status/tag/shelf on them;
  - carol (friend) cannot edit alice's items; a forged id for a book outside
    the circle is `blocked`/not found, not changed;
  - type rules: `Audiobook` on a Movie row blocked; status `watched` on a book
    blocked; shelf of another section blocked;
  - fingerprint mismatch refuses to apply;
  - cap of 500; `ids_from_view` count mismatch refuses;
  - journal rows match changes; undo restores; undo skips items changed since;
    double undo refused; shelf/tag undo removes only rows the edit created;
  - bulk status inserts are `quiet` and absent from the feed; no reading
    sessions created;
  - removal and restore round trip; hard delete is not reachable;
  - one failing item leaves the rest applied (force it with a constraint).
- `tests/test_grid_query.py`: the extracted query returns exactly what
  `library_page` / `grid_page` did, for each filter and `Show` value (write
  these against the old code first).
- Goodreads: the existing invariants stay (one outcome per row, never
  overwrites by default); add: apply with default decisions equals the old
  one-click import row for row; "keep mine" vs "use Goodreads" per field; the
  wishlist-then-read decisions; staging expiry and replacement; apply of rows
  not in the user's staging refused.
- `test_every_page_loads` picks up the new GET routes; `test_csp.py` covers the
  new JS and templates. JS pure helpers (range selection, plan summary) get a
  node test in the style of `tests/test_scanner_js.py`.
- Manual: run on a copy of the DB (`DATABASE_PATH=/tmp/test.db python3
  app.py`), do the cookbook case end to end, undo it, and check the feed shows
  nothing new.

## Build order

Each step is shippable and tested on its own.

1. Extract `utils/grid_query.py` with no behaviour change. Pin with tests first.
2. Migration: `bulk_edits`, `bulk_edit_items`, `collections.quiet` (+ feed
   filter); `create_database.sql` and ledger.
3. `utils/bulk.py` with genre only: plan, apply, undo, tests. (The cookbook
   case, headless.)
4. `blueprints/bulk.py` + select mode on the Books shelf + action bar + review
   sheet, genre only. Phil can fix the cookbooks here.
5. Remaining item edits (format, owned, remove/restore) and marks (status,
   shelves, tags); Movies and Music grids; Household and search/collection
   views; history on Profile.
6. Select all across the view (`ids_from_view`).
7. Goodreads: staging table, plan/apply split, review grid, conflict fields,
   wishlist-then-read decisions, import journal.
8. Archive the phase in `docs/ROADMAP-ARCHIVE.md`; update CLAUDE.md's blueprint,
   utils and frontend lists.

## Decisions I made that Phil may want to change

- **Default mode is Fill empty only**, with Replace opt-in. Safer; the
  cookbook case needs one extra click.
- **No title/author bulk editing in v1** (matching and duplicate detection
  depend on them).
- **Bulk status is quiet in the feed** (a new `collections.quiet` column).
- **Bulk status adds no reading dates or sessions.**
- **Cap of 500** per operation.
- **No separate Genres manager**; filter + select all + set genre does it.
- **Undo window 30 days**, guarded per item.
- **Hard delete is never bulk.**

## Out of scope

Bulk metadata refetch from Google Books/Open Library (an overwrite of many
fields from an outside source; if wanted it plugs into the same plan/review
step as a "Replace" action, but the matching quality is its own problem, see
ROADMAP 8F), bulk cover editing, bulk wishlist actions, edit on a friend's
shelves, CSV round-trip editing, cross-user edits.
