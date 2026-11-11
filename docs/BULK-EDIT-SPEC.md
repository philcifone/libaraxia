# Bulk Edit Spec (ROADMAP Phase 14)

Status: approved by Phil 2026-11-10, section 13 as written. Supersedes the
first draft (`FABLE-BULK-EDIT-SPEC.md`, deleted). ROADMAP Phase 14 links here;
its checklist mirrors the build order below.

**Who this is for.** Phil reviews. A Sonnet session builds, one step at a
time, following "Development pipeline" exactly. Builder: read this whole file,
then `CLAUDE.md`, then `ROADMAP.md`, before writing any code. Where this spec and
the code disagree, the code is the truth: stop, say what you found, and wait.
Don't guess your way round it.

---

## 1. Purpose

Bulk edit is housekeeping for a personal catalog that grew fast (Goodreads
import, barcode scanning, three media types). It has three jobs:

1. **Fix metadata in bulk.** The motivating case: Phil's dev copy holds 417
   books with 74 distinct genres. Cookbooks are spread across "Cooking",
   "Cookbook", "Cookery" and empty. Select them, set "Cookbooks", done.
2. **Organise in bulk:** put 30 records on a custom shelf, tag a run of
   books, mark a box of DVDs "watched".
3. **Deaccession in bulk:** a box of books went to the charity shop. Remove
   them from the library with one note.

A fourth job, the granular Goodreads import, reuses the same pieces. It is
**Phase 14b** (section 14) and is specified again after 14a ships, once Phil
has used the selection UI for real.

### What success feels like

- Calm. Selecting is quick and obviously reversible. Nothing jumps, nothing
  navigates by accident, nothing asks "are you sure?" twice.
- No surprises. Before anything is written, the user sees what will change,
  grouped so that 44 changes read as three lines rather than 44.
- Control without chores. The user can leave out a whole group ("the 2 that
  say Reference") with one click, or a single item, but never has to tick 40
  boxes to do the obvious thing.
- Recoverable. Every bulk edit can be undone for 30 days, and undo never
  clobbers something changed since.

### Non-goals

Bulk editing of title, author or ISBN; bulk hard delete; bulk cover changes;
bulk metadata refetch from online sources; editing a friend's items; CSV
round-trip editing. (Reasons in section 15.)

## 2. Principles, in priority order

When two of these pull against each other, the higher one wins.

1. **Never write what the user hasn't seen.** Every write goes through a
   review that shows it.
2. **Never overwrite a later change.** Apply and undo both re-check the
   current value and skip what moved.
3. **Pleasant beats clever.** Fewer controls, plain words, sensible defaults.
   If a feature needs a paragraph of explanation in the UI, cut it.
4. **Reuse the existing rules.** Permission, status and format validity, shelf
   scoping and tag cleaning come from the existing helpers, not a parallel
   copy.

## 3. Constraints

- Raw `sqlite3`, no ORM, no new Python or JS dependencies, nothing from a CDN.
- No inline JS (CSP; `tests/test_csp.py`). Vanilla JS in `/static/`, wired with
  `data-click` / `data-change` / `data-submit` and `registerActions`
  (`common.js`). Server values reach scripts through `data-` attributes.
- Every write is a POST with CSRF (fetch sends `getCSRFHeaders()`). Permission
  is decided per item, in SQL, on the server, at plan, apply and undo time.
- The browser says "these ids, this action, this value". It never names a
  column, table or path.
- All four styles (House, OG, Outrun, Shelf), light and dark: semantic
  classes and CSS variables only, no raw colours. Shelf-specific rules are
  scoped `:root[data-style="shelf"]`.
- Keyboard-complete, usable at 375 px, `prefers-reduced-motion` respected.
- Errors are logged with `current_app.logger.exception` and returned as a
  generic message, never `str(e)`. Validation errors are specific and written
  for a person ("Pick a genre first").
- No emojis in code, docs or UI. Comments explain why, not what.

## 4. What the code already does (checked 2026-11-10)

These facts shape the design. The builder should re-check any that a step
depends on before relying on it.

1. **Editing an item is owner or admin.** `books.edit_book` checks
   `current_user.is_admin or book['added_by'] == current_user.id`; the media
   sections do the same. Household members can see each other's items but
   can't edit them.
2. **Marks are per user** and allowed on any item `models.can_view_book`
   passes: status (`collections`), tags (`book_tags`), custom shelves
   (`collection_books`). `collections.add_to_status_collection` is the
   single-item status route: it checks `can_view_book`, then
   `media.is_valid_status`; `'untracked'` deletes the row.
3. **`books.genre` is free text.** Grid filters compare `LOWER(genre)`; stats
   group by `LOWER(genre)`. 74 distinct values on 417 books in the dev DB.
4. **Tags are lowercased and trimmed** in `blueprints/tags.py`
   (`tag.strip().lower()`).
5. **Formats:** `media.FORMATS` per type. A plain book stores `format` NULL,
   an audiobook `'Audiobook'` (`media.book_format`). Videos `VHS`/`DVD`
   (shown "Cartridge"/"DVD" via `media.format_label`), records
   `LP`/`EP`/`7in`/`10in`/`12in`/`CD`/`Cassette`.
6. **The feed reads `collections` at query time** (`blueprints/feed.py`):
   rows whose status is one of `currently reading`, `want to read`, `watched`,
   `want to watch`, `listened`, `want to listen`, ordered by
   `collections.created_at`. A new row appears to every friend. An UPDATE
   keeps the old `created_at`, so it changes the wording of an old feed line
   but doesn't add a new one. `read` isn't announced (reviews do that).
7. **Grids differ in how they load.** The Books grid (`base.library_page`)
   pages by infinite scroll (30 a page, JSON via `X-Requested-With`). The
   Movies and Music grids (`media_section.grid_page` ->
   `Section.filtered`) render every matching row at once (`has_more=False`).
   Search (`books.search`) and the status collection pages
   (`collection_status.html`) have their own queries.
8. **Filter, search and sort changes reload the page** (`script.js` sets
   `window.location.href`). A selection made in JS dies with the page, which
   is what we want.
9. **All grids share `_book_grid.html`** with `#book-container`
   (`data-media`, `data-view` grid/list), and `_view_bar.html` above it.
10. **The Goodreads importer** (`utils/goodreads.py`, `_Importer`) uses one
    SAVEPOINT per row and reports exactly one outcome per row. Copy that
    transaction pattern; don't invent a new one.
11. **Migrations:** latest is `029_reading_goals.sql`; **030 is reserved for
    ROADMAP 15.1**. `manage.py` applies every file missing from the ledger in
    name order, so taking **031** now and 030 landing later is fine. Two files
    with the same number are refused.

## 5. The experience, start to finish (the cookbook case)

This is the reference flow. Every UI decision below serves it.

1. On Shelves -> Books, Phil filters genre "Cooking". 24 cards.
2. He presses **Select** in the view bar. The floating `+` slides away; a bar
   rises from the bottom: "0 selected · Select all · Done". Cards show an
   empty check box on the cover's top-left corner.
3. He presses **Select all**: "24 selected". (On the Books grid with more not
   yet loaded, the bar also offers "Select all 57 in this view".)
4. He clears the filter, searches "cook", and the page reloads, which drops
   the selection. That's fine and expected: a selection belongs to the view
   it was made in. (He learns to filter by search first, then select.)
   He selects the 47 cookbooks from the search results with Select all.
5. In the bar he picks **Genre**. A sheet opens: a genre field with the
   existing genres listed by use ("Fiction 88", "Cooking 24", ...). He types
   "cookb", sees "Cookbook 12" and picks it, or types "Cookbooks" and sees
   "New genre". He presses **Review**.
6. The same sheet turns to the review:

   ```
   Set genre to "Cookbooks"                                  [Change]

   44 will change · 1 already set · 2 skipped

   [x] Cooking -> Cookbooks                       24   [show]
   [x] Cookbook -> Cookbooks                      12   [show]
   [x] Cookery -> Cookbooks                        6   [show]
   [ ] Reference -> Cookbooks                      2   [show]   <- he unticks it
   [x] (no genre) -> Cookbooks                     2   [show]
       Already "Cookbooks"                         1
       Skipped: not yours (household)              2   [show]

                                   [Cancel]  [Apply to 44 items]
   ```

   "show" expands a group into its items (cover thumb, title, creator, each
   with its own checkbox). The Apply button's count follows every tick.
7. He presses **Apply to 42 items**. The page reloads where he was, with a
   banner: "Genre set to Cookbooks on 42 items. [Undo] [Dismiss]".
8. Next week he notices a mistake. Profile -> Recent bulk edits -> Undo.
   "40 restored, 2 changed since and left alone."

## 6. Select mode

### Entering and leaving

- A **Select** button (text, plus a new `check-square` icon added to
  `_icons.html` in the Lucide style the others use) in `_view_bar.html`, on these pages: your Shelves grids in all three
  sections, the Household grids, Search, and status collection pages. Not on
  a friend's grids (read-only), not on the Collections overview or Reviews
  (no grid).
- Select mode is `data-select="on"` on `#book-container`, next to
  `data-view`. Grid view, list view and the Shelf style's cover boxes all
  style it from CSS; there is no second template.
- The button becomes **Done** (`aria-pressed="true"`). Leaving clears the
  selection without asking: a selection is cheap to rebuild and nothing has
  been written.
- **Esc** closes the innermost thing: an open sheet first, else select mode.

### Cards in select mode

- Clicking or tapping anywhere on a card toggles it. Links inside the card
  are inert in select mode (click handled in the capture phase,
  `preventDefault`), so a mis-tap can't navigate away and lose the
  selection. The status/quick menus on cards are hidden in select mode.
- **The look** (all styles, from variables):
  - Unselected: a small square check box on the cover's top-left corner,
    outlined in `--rule-strong`, on a `bg-secondary` pad so it reads on any
    cover. Nothing else changes: covers stay full brightness.
  - Selected: the box fills with the accent and shows a check
    (`text-on-accent`); the cover gets a 3 px accent outline, offset 2 px.
    Shelf style: the outline goes round `.cover-box`, not the card. Outrun:
    the outline uses the neon accent and its existing glow variable.
  - List view: the check box is the row's first column; the selected row
    gets the accent outline.
  - Transitions 120 ms on outline and fill only; none under reduced motion.
- **Mouse:** click toggles; **Shift-click** selects the range from the last
  clicked card in page order; **Ctrl/Cmd-click** also toggles (same as plain
  click, kept for muscle memory).
- **Keyboard:** the grid is a `role="listbox"` with
  `aria-multiselectable="true"`, cards `role="option"` with `aria-selected`,
  roving `tabindex`. Arrow keys move focus (Left/Right one card; Up/Down by
  the grid's current column count, measured from layout). **Space** toggles,
  **Shift+Space** or **Shift+Arrow** extends a range, **Ctrl/Cmd+A** selects
  all loaded. Focus ring as elsewhere in the app.
- **Touch:** tap toggles. The check box hit area is the whole card, so small
  covers at 375 px are easy targets. Long-press to enter select mode is out
  of v1 (it fights the iOS image callout); see section 15.

### The selection bar

- Fixed to the bottom of the viewport, full width of the content column
  (not under the sidebar), above page content, below sheets and the sidebar
  overlay. Uses `bg-secondary`, a top border `border-card`, the style's
  shadow. It replaces the floating `+` (FAB hidden while in select mode) so
  they never stack.
- Content, left to right: **count** ("12 selected", `aria-live="polite"`),
  **Select all** / **Clear** (one or the other is shown: Clear when anything
  is selected), then the actions.
- Actions on wide screens: text buttons **Genre**, **Status**, **Shelf**,
  **Tag**, and a **More** menu with **Format**, **Owned**, **Remove from
  library** / **Restore**. On phones (below `sm`): one **Actions** button
  opening a bottom sheet list. Actions are disabled (not hidden) at 0
  selected, with `title`/`aria-disabled` explaining why.
- Actions that can't apply to any selected item are still offered; the
  review says why each item was skipped. (Hiding them would make the bar's
  layout jump as the selection changes.)
- The page gets bottom padding equal to the bar's height, so the last row of
  cards is never hidden under it.

### "Select all"

- **Select all** selects every card currently in the DOM.
- On the Books grid with `has_more`, the bar then shows a second line:
  "All 30 loaded are selected. **Select all 57 in this view**". Choosing it
  switches the selection to a *view selection*: the bar says "All 57 in this
  view", and individual toggles are disabled until Clear (mixing "all
  matching" with exceptions is a known source of confusion; the review is
  where you leave things out).
- A view selection sends `{view: "book:mine", args: "<query string>"}`
  instead of ids. The server resolves it at **plan** time with the same
  query the grid uses (section 11, `grid_query.py`) and the plan carries the
  resolved ids. Apply uses those ids, so a view that changes between review
  and apply can't widen what gets written.
- Movies, Music, Search and collection pages: Select all is all, because the
  page already holds everything (Search: confirm in step 1; if Search pages,
  it gets the view selection too, or Select all is limited to what's loaded,
  and the builder reports which).
- **Cap: 500 items per operation.** Above it the bar says "Too many for one
  edit (612). Narrow the view." and the actions are disabled. Reason:
  SQLite has one writer, and a bounded edit is a bounded mistake.

## 7. The action sheet: choose, then review

One component, `_bulk_sheet.html` + `bulk.js`, used by every action. A
`<dialog>` (modal: focus trapped, Esc closes, focus returns to the bar
button that opened it). Centred, max-width 40rem on wide screens;
full-height bottom sheet on phones. Two stages in the same dialog, never two
stacked dialogs.

### Stage 1: Choose

The title says what you're doing ("Set genre"). One input per action
(section 8), then **Review** (primary) and **Cancel**. Enter submits when the
value is valid. Review is disabled until it is.

### Stage 2: Review

Returned by `POST /bulk/plan`. Layout as in section 5:

- **Header:** the action in words, with **Change** to go back to stage 1
  (value kept).
- **Summary line**, words first, colour second: "44 will change · 1 already
  set · 2 skipped". Not colour-only anywhere.
- **Groups**, one per distinct current value, sorted by count (largest
  first), with "(no genre)"-style empty groups last:
  - **Change groups:** a checkbox, "Before -> After", count, and **show**,
    which expands the group's items (cover via `coverSrc`, title, creator,
    each with a checkbox). Ticking a group ticks all its items; a partly
    ticked group shows the indeterminate state.
  - **Already set:** one quiet line with a count, no checkbox.
  - **Skipped:** one line per reason ("Not yours", "Not a format for Movies",
    "Not a status for Music", "Shelf is for Books", "Already removed"),
    collapsed, no checkbox.
  - **Notes** under the groups, only when relevant: "No reading dates are
    added", "Audiobooks don't count toward pages read", "These leave your
    shelf; reviews and ratings stay".
- **Defaults:** every change group starts **ticked**. The review is
  mandatory and grouped, so a differing value can't be overwritten without
  being on screen; ticking by default makes the obvious case one click.
  (The first draft defaulted to "fill empty only" behind a mode switch; the
  grouped review gives the same control, one click per group, without a
  setting to understand first. See section 13.)
- Groups start expanded when the whole plan has 12 items or fewer, else
  collapsed. An expanded group longer than 50 items shows 50 and "Show
  all".
- **Footer**, sticky inside the dialog: **Cancel** and the primary button,
  whose label is the verb and the live count: "Apply to 44 items", "Remove
  44 from library" (danger style for removal), "Add 30 to Jazz". Disabled at
  0.
- **There are no extra confirmations.** The review is the confirmation, and
  the button says exactly what it does. Undo is the safety net.

### When the data moved under you

Apply re-plans on the server. If the plan's fingerprint no longer matches
(another tab, a household member's edit), the server answers 409 with the
**new plan**, and the sheet shows it in place with a one-line notice: "Some
items changed since you looked. Here's the updated list." Group choices carry
over by their before value; nothing is applied until the user presses Apply
again. No "reload the page" dead ends.

### After apply

- On success the page reloads at the same URL. The server has put the edit's
  id in `session['bulk_result']`; `_bulk_result.html` (included by the grid
  pages) shows it once as a banner at the top of the content: "Genre set to
  Cookbooks on 42 items. [Undo] [Dismiss]". Scroll position is not
  preserved; the banner is at the top, which is where the eye should go.
- Banner **Undo** posts `/bulk/<id>/undo`, reloads, and shows the undo
  result the same way: "Undone: 40 restored, 2 changed since and left alone."
- Partial failures (one item's SAVEPOINT rolled back) are named in the
  banner: "41 changed, 1 failed (logged)."

## 8. Actions (v1)

`utils/bulk.py` holds the whitelist. The request carries the action key; the
SQL's table and column come from the whitelist entry, never the request.

### Item edits (the `books` row; owner or admin)

| Key | Stage 1 input | Rules |
|---|---|---|
| `genre` | Genre picker (below). Choosing "(no genre)" clears. | All three types. Cleaned by `clean_genre`. |
| `format` | Select, grouped by type, labels via `media.format_label` ("Cartridge"). Only the types present in the selection are listed. | Valid only for the item's own type (`media.FORMATS`); others skipped "Not a format for Movies". Book: Book stores NULL, Audiobook `'Audiobook'` (`media.book_format`). Note shown when books become audiobooks. |
| `owned` | Two radio buttons: Owned / Not owned. | `books.owned`. Note shown when items leave the shelf. Doesn't touch `removed_at`. |
| `remove` | Optional note (one for all, 200 chars). | Deaccession: sets `removed_at` (now) and `removed_note`. Already-removed items: "Already removed". Reviews, statuses and tags stay. |
| `restore` | None. Offered only when the view shows removed items (`show=removed` / `everything`). | Clears `removed_at` and `removed_note`. |

### Marks (your own rows; any item `can_view_book` allows)

| Key | Stage 1 input | Rules |
|---|---|---|
| `status` | Select of the statuses valid for the types in the selection, labels from `media.STATUS_LABELS`, plus "No status" (`'untracked'`, worded per type via `NO_STATUS_LABEL`). | `media.is_valid_status` per item; others skipped "Not a status for Music". Insert or update `collections`; `'untracked'` deletes the row. New rows are written `quiet = 1` (section 10). Never creates reading sessions or ratings. |
| `shelf_add` / `shelf_remove` | Add/Remove toggle; select of your custom shelves for the section, plus "New shelf..." (inline name field, created on apply, same validation as the Collections page). | Only shelves whose `user_collections.media_type` matches the item; others skipped "Shelf is for Books". Mixed-type selection: the select lists one section's shelves at a time (section picker shown only when the selection is mixed). Already on / not on: "Already set". |
| `tag_add` / `tag_remove` | Add/Remove toggle; tag field with your existing tags suggested. | Cleaned exactly as `tags.py` does (strip, lowercase), length-capped as there. |

### Genre picker

- `GET /bulk/genres?type=book|video|record` returns your genres for that type
  on your own items: `[{value, count}]`, grouped by `search.fold` (case and
  accent insensitive), each group shown with its most-used spelling, sorted
  by count. Mixed-type selection: the union.
- The input is a combobox (`role="combobox"` + listbox, not `<datalist>`,
  which can't show counts everywhere). Typing filters the list by `fold`.
- A typed value that folds equal to an existing genre snaps to the existing
  spelling, with a line under the field: "Using existing spelling
  'Cookbooks'". Otherwise: "New genre".
- `clean_genre`: trim, collapse inner whitespace, reject control characters,
  cap at 80 characters. No title-casing ("Sci-Fi" stays "Sci-Fi").
- Renaming or merging genres needs no separate page: filter by genre, Select
  all, Set genre.

## 9. Undo and the journal

### Tables (migration 031, folded into `create_database.sql` and its ledger INSERT)

```sql
-- One row per applied bulk edit (ROADMAP 14).
CREATE TABLE bulk_edits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    action TEXT NOT NULL,          -- whitelist key: 'genre', 'status', ...
    params TEXT NOT NULL,          -- JSON of the action's value(s)
    summary TEXT NOT NULL,         -- 'Genre set to Cookbooks on 42 items'
    item_count INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    undone_at TIMESTAMP
);
CREATE INDEX idx_bulk_edits_user ON bulk_edits(user_id, created_at);

-- What each item was before and after, so undo can put it back.
CREATE TABLE bulk_edit_items (
    edit_id INTEGER NOT NULL REFERENCES bulk_edits(id) ON DELETE CASCADE,
    book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    before TEXT,                   -- JSON snapshot; NULL = no row existed
    after TEXT,                    -- JSON snapshot; NULL = no row exists now
    PRIMARY KEY (edit_id, book_id)
);

-- Rows written by bulk edits (and later the import) stay out of the feed.
ALTER TABLE collections ADD COLUMN quiet INTEGER NOT NULL DEFAULT 0;
```

### Rules

- **Snapshots, not single values.** `before`/`after` are JSON of every
  column the action touches, so undo is exact. Examples: genre
  `{"genre": "Cooking"}`; remove `{"removed_at": null, "removed_note":
  null}`; status `{"status": "want to read", "created_at": "...", "quiet":
  0}` or NULL when there was no row; shelf/tag add `before` NULL (undo
  deletes only that row); shelf/tag remove `before` the deleted row.
- Journal rows are written in the **same SAVEPOINT** as the change, so the
  journal can't disagree with the data. Only `change` items are journalled.
- **Undo is guarded.** `POST /bulk/<id>/undo`, owner of the edit only:
  1. Refuse if `undone_at` is set ("Already undone").
  2. Per item, re-check permission now (the book may have been transferred),
     then compare the current state to `after`. Equal: write `before`.
     Different: skip, counted as "changed since".
  3. One SAVEPOINT per item, set `undone_at`, commit, report.
  Undo is not itself journalled and can't be undone (keeps it simple; the
  forward edit can be re-applied).
- **Retention: 30 days.** Swept lazily at the start of each apply (`DELETE
  FROM bulk_edits WHERE created_at < datetime('now', '-30 days')`; items go
  by cascade). No scheduler.
- **Where undo lives:** the result banner (section 7) and **Profile ->
  Recent bulk edits**: the last 10 within 30 days, newest first, each with
  its summary, relative time and Undo (or "Undone"). Placed in Profile's
  data/account area next to the exports; the builder picks the exact spot to
  match the existing layout and says where.

## 10. Feed side effects

Bulk edits must not spam friends.

- Genre, format, owned, removal, restore, tag and shelf changes don't touch
  anything the feed reads. Nothing to do.
- **Status inserts would appear** (fact 6). New `collections` rows from bulk
  are written `quiet = 1`; the feed's collections query adds
  `AND c.quiet = 0`. Status *updates* by bulk leave `quiet` as it was.
- **The single-item status route resets `quiet = 0` on update**
  (`collections.add_to_status_collection`). Otherwise an item bulk-set to
  "want to read" would stay invisible after the user starts reading it by
  hand. (Its feed line keeps the old `created_at`, exactly as today's
  updates do.)
- Bulk status never redirects to the review page and adds no reading dates;
  the review says so. Dated reads are the import's job, where dates exist.

## 11. Back end

### Modules

- **`utils/grid_query.py`** (new, step 1). `view_ids(conn, user, view,
  args)` returns the ids a grid shows, in grid order, for a whitelisted
  `view` key: `book:mine`, `book:household`, `video:mine`,
  `video:household`, `record:mine`, `record:household` (plus `book:search`
  if Search paginates). Household views resolve owners with
  `households.member_choice`, as the grids do.
  - Books: move the WHERE-building out of `base.library_page` into a function
    `books_query(owner_ids, args, data_user) -> (sql, params)` that both
    `library_page` and `view_ids` call. **No behaviour change**: tests pin
    the current results first.
  - Movies and Music already have one implementation, `Section.filtered`;
    `view_ids` calls it. Don't duplicate it.
- **`utils/bulk.py`** (new). No Flask imports: takes `conn` and a user (id
  and `is_admin`), like `utils/households.py`, so tests drive it directly.
  - `ACTIONS`: the whitelist (key -> validator, planner, writer, undoer).
  - `PlanRow(id, title, creator, cover, media_type, before, after, outcome,
    reason)`; outcome is `change`, `same` or `skip`.
  - `plan(conn, user, action, params, ids) -> Plan` (read-only; groups,
    counts, notes, fingerprint). The fingerprint is a SHA-256 of the sorted
    `(id, before, after, outcome)` tuples plus action and params.
  - `apply(conn, user, action, params, ids, fingerprint, excluded_ids) ->
    Result`: re-plan, compare fingerprint (raise `StalePlan(new_plan)`),
    sweep old journals, insert `bulk_edits`, then per `change` row not in
    `excluded_ids`: SAVEPOINT, write, journal, RELEASE (ROLLBACK TO on error,
    log, count as failed). One commit at the end.
  - `undo(conn, user, edit_id) -> Result`, `history(conn, user, limit=10)`,
    `genres(conn, user, media_type)`, `clean_genre`.
- **`blueprints/bulk.py`** (new, `/bulk`), registered in `app.py`. All
  `@login_required`, JSON in and out per the API response pattern:

| Route | Body / args | Limit (per user) |
|---|---|---|
| `POST /bulk/plan` | `{action, params, ids}` or `{action, params, view, args}` | 200/hour |
| `POST /bulk/apply` | `{action, params, ids, fingerprint, excluded_ids}` | 60/hour |
| `POST /bulk/<id>/undo` | none | 60/hour |
| `GET /bulk/genres` | `?type=` | none |
| `GET /bulk/history` | none (Profile renders it server-side; this is for JS if needed) | none |

  `/plan` is POST because the id list can be long; it writes nothing, and its
  docstring says so. Excluded ids are sent rather than included ids, so the
  default (everything ticked) is an empty list. Groups are a UI concept:
  unticking a group just adds its ids to `excluded_ids`.
  `/apply` on success sets `session['bulk_result']` and returns
  `{success, edit_id, summary}`; on a stale plan returns 409 with
  `{success: false, stale: true, plan}`.
- **Templates:** `_bulk_bar.html` (Select button + bar), `_bulk_sheet.html`
  (the dialog), `_bulk_result.html` (banner). Included from the grid pages
  (`index.html`, `shared_library.html`, `media_grid.html`, `search.html`,
  `collection_status.html`), not from `base.html`.
- **JS:** `static/bulk.js`, loaded in those pages' `{% block scripts %}`.
  Pure helpers (range between two indexes, group tick state, summary
  wording, column count from layout) at the top as plain functions, exported
  for node tests the way `scanner.js` and `cover_crop.js` do. `script.js`'s
  infinite scroll fires an event (e.g. `cards-added`) after appending cards
  so `bulk.js` can mark newly loaded selected cards and give them select-mode
  attributes. `createBookCard` itself doesn't learn about selection.
- **CSS:** in `static/styles.css`, a "Bulk select" block (and a Shelf-scoped
  rule for `.cover-box`). Rebuild `static/css/output.css` with
  `npm run build:css` and include it in the step's changes.

### Permission in SQL

- Item edits: `UPDATE books SET ... WHERE id = ? AND (added_by = ? OR ? = 1)`
  with the admin flag; plan marks non-owned rows `skip: "Not yours"` with the
  same predicate.
- Marks: `can_view_book(conn, user, id)` per item at plan, apply and undo.
- A forged id outside the user's reach can only ever produce a `skip` row
  ("Not found"), never a write. Plan rows for items the user can't view
  carry no title or cover (don't leak another user's catalog through the
  review).
- Admins edit any item through the same grids, but no page offers "bulk edit
  the whole database".

## 12. Tests

Add with each step, never after. `pytest` must pass at the end of every step.

- **`tests/test_grid_query.py`** (step 1, written against the old code
  first): for each filter (`search_term`, `genre`, `format`, `read_status`,
  `rating`, `tags[]`, each `show` value, `member`) and sort, `view_ids`
  returns exactly the ids the grid renders, in the same order, for books,
  movies and music, own and household.
- **`tests/test_bulk.py`** (using the `people` fixture: alice admin, alice +
  bob household, carol alice's friend):
  - plan is read-only (`conn.total_changes` unchanged);
  - groups and counts; `same` and `skip` reasons; excluded ids untouched;
  - bob gets `skip: Not yours` on alice's books but can set his own status,
    tag and shelf on them; carol can't touch alice's items; a forged id for a
    book outside the circle is "Not found" with no title leaked;
  - type rules: Audiobook on a video, `watched` on a book, a Books shelf on a
    record are all skipped;
  - stale fingerprint raises with a new plan; cap of 500 (ids and view);
  - view selection resolves to the grid's ids and refuses a view key outside
    the whitelist or a friend's view;
  - journal matches changes; undo restores; undo skips items changed since;
    undo re-checks permission; double undo refused; another user's edit id
    refused; shelf/tag undo removes only rows the edit created; status undo
    restores a deleted row with its original `created_at` and `quiet`;
  - status inserts are `quiet = 1` and absent from the feed; the single-item
    route resets `quiet` on update; no reading sessions created;
  - remove and restore round trip; no route reaches hard delete;
  - one failing item (forced with a constraint) leaves the rest applied and
    is reported;
  - 30-day sweep.
- **Routes:** each `/bulk/*` route: login required, CSRF-protected in the
  POST sense (tests run with CSRF off; check the routes aren't exempted),
  JSON shape, 409 shape.
- **`tests/test_bulk_js.py`**: the pure helpers under node, in the style of
  `tests/test_scanner_js.py`.
- `test_every_page_loads` covers the new GET routes; `test_csp.py` covers the
  new JS and templates; `test_migrations.py` covers 031 on an existing DB.

## 13. Decisions Phil may change

Each is one constant or one line; listed so they're easy to find.

1. **Change groups default to ticked** (grouped review instead of a "fill
   empty only / replace" mode switch). Flip: `DEFAULT_TICKED = False` in
   `bulk.js`, or per group for groups with a non-empty before value.
2. **No confirmation dialogs** beyond the review; the Apply button names the
   verb and count.
3. **Bulk status is quiet** in the feed.
4. **Bulk status adds no reading dates, sessions or ratings.**
5. **Cap of 500** per operation.
6. **Undo kept 30 days**, guarded per item, not itself undoable.
7. **No title/author/ISBN bulk editing** (matching and duplicate detection
   depend on them).
8. **No hard delete in bulk.**
9. **Selection doesn't survive a page reload** (filter, search, sort).
10. **Migration number 031**, leaving 030 to ROADMAP 15.1.

## 14. Development pipeline (builder: follow this exactly)

Production deploys itself: a push to `main` with green CI reaches prod within
about five minutes, **and prod runs `manage.py migrate` on the way**. So
nothing in this phase goes near `main` until Phil merges it.

### Branch and worktree

Phil's main checkout (`/home/phil/coding/libaraxia`) runs his own HTTPS dev
server on port 5000 with debug reload. Switching branches there would reload
his server onto half-built code and an unmigrated DB. So the work happens in
a **separate git worktree** on its own branch:

```bash
cd /home/phil/coding/libaraxia
git worktree add -b phase-14-bulk-edit ../libaraxia-bulk main
cd ../libaraxia-bulk
```

Branch name: `phase-14-bulk-edit` (matches the existing `phase-N` branches).
Do all work in `/home/phil/coding/libaraxia-bulk`. Don't touch the main
checkout, its `library.db` or its running server.

### Worktree setup (once)

Git-ignored files aren't in a new worktree. Link or copy them:

```bash
cd /home/phil/coding/libaraxia-bulk
ln -s ../libaraxia/venv venv                   # same Python deps
ln -s ../libaraxia/node_modules node_modules   # Tailwind
cp ../libaraxia/.env .env                      # keys; FLASK_ENV=development
# Covers: link, read-only use. Bulk edit never writes images.
ln -s ../../libaraxia/static/uploads static/uploads
# A private DB copy, taken safely while Phil's server may be writing:
sqlite3 ../libaraxia/library.db ".backup bulk-dev.db"
```

Check `ls -l static/uploads/` resolves to real covers before going on. Use
`venv/bin/python` and `venv/bin/pytest` for everything.

### Dev server

Use port **5000 if it's free, else 5001**. Today 5000 is normally Phil's own
server, so expect 5001. Check first:

```bash
ss -ltn | grep -E ':(5000|5001)\b'      # anything listening?
```

Then start it on the free port, bound to all interfaces (`app.py` binds
`0.0.0.0` and reads `PORT`), against the private DB:

```bash
DATABASE_PATH=bulk-dev.db venv/bin/python manage.py migrate   # after step 2
DATABASE_PATH=bulk-dev.db PORT=5001 venv/bin/python app.py
```

Run it in the background, then tell Phil the port and the LAN URL
(`hostname -I` for the address, e.g. `http://192.168.x.y:5001/`). Plain HTTP
is fine: bulk edit needs no camera. If neither port is free, stop and ask;
don't kill anything you didn't start. Stop your server when the step ends
unless Phil wants it left running.

### Each step

1. Read the step's section of this spec and the code it touches.
2. Write the tests first where the step says so (always for step 1).
3. Build. Keep changes inside the step's scope; note anything else you see
   in the report instead of fixing it.
4. `venv/bin/pytest`: all green. Run `npm run build:css` if CSS changed.
5. For UI steps: start the dev server, walk the step's acceptance check
   yourself as far as you can (fetch the pages, check for template errors in
   the log), and list what Phil should look at in a browser: all four
   styles, light and dark, a phone width.
6. **Stop and report**, then wait for Phil:
   - what was built, file by file, one line each;
   - test count before and after, and the `pytest` summary line;
   - anything in the spec that didn't match the code, and what you did;
   - the LAN URL and what to click.

### Git rules

- **Don't commit, push, merge, rebase or open PRs.** Phil reviews `git diff`
  in the worktree after each step and commits himself. No Claude attribution
  in anything.
- Don't add or edit migrations other than this phase's own (031).
- If `main` moves while the branch is open, say so in the report; Phil
  decides whether to merge it in.
- `static/css/output.css` is generated: on any conflict, rebuild it, don't
  hand-merge.

### Merging (Phil)

Two merge points, each reviewed and tried on the dev server first:

- **M1 after step 4:** genre bulk edit on the Books grid, with undo. Useful
  on its own (the cookbooks), and it puts migration 031 through prod early,
  while it's small.
- **M2 after step 7:** everything else in 14a.

Before each merge: full `pytest`, `manage.py --db <copy of prod DB> migrate`
on a fresh copy, and the manual cookbook run (section 5) on the dev server.
Then push the branch, open a PR so CI runs on it, merge when green. When 14a
is done: `git worktree remove ../libaraxia-bulk` and delete the branch.

## 15. Build order (Phase 14a)

Each step is shippable and tested on its own. Stop after each.

1. **Grid query extraction.** `utils/grid_query.py` and `books_query`, no
   behaviour change; `tests/test_grid_query.py` written against the old code
   first and passing before and after. Check how Search and the status
   collection pages load (paged or not) and report it.
   *Accept:* full suite green; no template or route output changed.
2. **Migration 031.** `bulk_edits`, `bulk_edit_items`, `collections.quiet`;
   folded into `create_database.sql` and the ledger INSERT; feed filter
   `c.quiet = 0`; single-item status route resets `quiet`. Apply to
   `bulk-dev.db`.
   *Accept:* `test_migrations` and feed tests green; `manage.py status`
   clean on the dev copy.
3. **`utils/bulk.py`, genre only, headless.** plan, apply, undo, history,
   genres, `clean_genre`, sweep. Tests drive it directly.
   *Accept:* the cookbook case passes as a test, including undo and a stale
   fingerprint.
4. **The UI, genre only, Books grid.** `blueprints/bulk.py`, Select button,
   selection bar, action sheet (choose + review), result banner, genre
   picker, keyboard, phone layout, all four styles.
   *Accept:* Phil does section 5 on the dev server. **M1.**
5. **Remaining actions:** format, owned, remove, restore, status, shelves
   (with "New shelf..."), tags.
   *Accept:* each action's plan/apply/undo tests; review notes shown.
6. **Everywhere else:** Movies and Music grids, Household grids (with
   `member`), Search, status collection pages; Profile -> Recent bulk edits.
   *Accept:* `test_every_page_loads`; Select absent on friends' grids.
7. **Select all in view** (`view` + `args`, Books grid, and Search if it
   pages). Cap messages.
   *Accept:* view-resolution tests; 57-item case works across pages. **M2.**
8. **Wrap-up.** Tick ROADMAP 14's items, archive the phase in
   `docs/ROADMAP-ARCHIVE.md`, add `bulk` to CLAUDE.md's blueprint, utils and
   frontend lists (and `collections.quiet` to the schema notes).

## 16. Phase 14b: granular Goodreads import (outline, re-spec after 14a)

Kept from the first draft, corrected, so the 14a pieces don't paint it into a
corner. Not to be built from this outline.

- **Split decide from write.** Today `import_goodreads` parses, matches and
  writes in one pass. 14b: `POST /user/import_goodreads/plan` parses
  (`parse_row`), matches against your books and household (`BookIndex`,
  never anyone else's) and stores the rows in an `import_staging` table (one
  per user, replaced by a new upload, swept after 24 hours, capped around
  5000 rows). Not in the session cookie, not round-tripped through the
  browser.
- **Review page** (full page, not the dialog), reusing the selection bar and
  the grouped review: one row per CSV row with title, author, Goodreads
  shelf, rating, Date Read, **match** (New / In your library / In your
  household's / On your wishlist) and **destination** (Library with status,
  Wishlist, Library not owned, Skip), defaulted by today's rules (to-read ->
  wishlist, audiobook -> not owned). Filter by shelf, match, destination;
  select rows and set destination in bulk.
- **Conflicts are fields.** Where the item exists, status, rating and
  review/dates show "yours" beside "Goodreads", defaulting to **keep yours**,
  flippable per row or for a selection. The importer still never overwrites
  unless told, but now shows what it left alone.
- **Wishlist-then-read** (ROADMAP 14): its own outcome, choices *Move to
  library as read*, *Mark read, keep wished for*, *Skip*, default **Ask**;
  Import is blocked until each is answered ("Needs a decision" filter).
- **Goodreads shelves -> custom shelves:** a mapping panel above the grid
  (existing shelf, new shelf of that name, or ignore).
- **Apply** (`POST /user/import_goodreads/apply`) takes row ids and
  decisions only; `_Importer` writes as told, one SAVEPOINT and one outcome
  per row (the invariant `tests/test_goodreads.py` asserts), statuses
  `quiet = 1`, journalled so the import can be undone (created books removed
  only if nothing else hangs on them, as hard delete requires). The 3/hour
  limit counts applies, not plans.
- **One click still works:** "Import everything with the defaults" (Ask rows
  skipped) equals today's behaviour row for row, tested.
- Covers: the export has none; the result keeps starting the `cover_jobs`
  fetch.

## 17. Out of scope, with reasons

- **Title / author / ISBN bulk edits:** they drive `book_matching.py`,
  duplicate detection and the wishlist match; a mass rewrite is the likeliest
  way to break the catalog quietly. Revisit as find-and-replace with the same
  review if needed.
- **Hard delete in bulk:** it exists for mistakes, one at a time, behind the
  "other users have data on it" check.
- **Bulk metadata refetch** (Google Books / Open Library): match quality is
  ROADMAP 8F's problem; if wanted later, it plugs into plan/review as a
  replace action.
- **Bulk covers, wishlist actions, friends' items, cross-user edits, CSV
  round-trip editing.**
- **Later polish, not v1:** long-press to enter select mode on touch;
  "Select these again" on the result banner; keeping the selection across a
  filter change; publisher/year edits.
