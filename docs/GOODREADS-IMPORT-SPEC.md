# Goodreads Import Spec (ROADMAP Phase 14b)

Status: approved by Phil 2026-11-11. Built from `GOODREADS-IMPORT-BRIEF.md` and
Phil's notes on it the same day. Replaces the outline in `BULK-EDIT-SPEC.md`
section 16. ROADMAP 14b links here once approved; its checklist mirrors the
build order below.

**Who this is for.** Phil reviews. A Sonnet session builds, one step at a
time, following "Development pipeline" exactly. Builder: read this whole file,
then `CLAUDE.md`, then `ROADMAP.md`, then `BULK-EDIT-SPEC.md` sections 2, 3, 9
and 14 (this phase reuses them), before writing any code. Where this spec and
the code disagree, the code is the truth: stop, say what you found, and wait.

---

## 1. Purpose

Goodreads is a **snapshot of reading history**, not a catalogue. For years
Phil read his own books, library books and audiobooks and reviewed them all
there; then he built Libaraxia to catalogue the physical books in the house,
and for over a year it has been where he reviews. Goodreads stopped then.

So an import has to bring the history in without pretending it's a shelf, and
a re-import has to add what's missing without touching what Libaraxia has
since recorded. Today's import can't: it writes in one pass, puts every read
book on the shelf as owned, turns every Goodreads shelf into a collection,
drops whole rows once a book has a status, and can't be undone.

### What success feels like

- **Visible before written.** After the upload you see your Goodreads file
  sorted into a few plain-English boxes ("Read, not in your library", "On
  your Goodreads want-to-read list", ...), each row with what will happen to
  it. Nothing is written until you press Import.
- **Libaraxia wins.** Where your Libaraxia data and Goodreads disagree, yours
  stays, and the review shows what was different. Imports only ever **add**:
  a missing rating, a missing review, a missing reading session. Nothing you
  have is changed or deleted.
- **Honest shelf.** A book you read but never owned comes in as read, not
  owned: in your reading stats and history, findable under Show: Not owned,
  never on the shelf.
- **Traceable forever.** Every book an import touched is marked, for you,
  with what it wrote. Months later: filter the Books grid to "From
  Goodreads", or open a book and read "From your Goodreads import, 14 Nov
  2026: review, rating, 2 reading sessions".
- **Undoable for 30 days**, guarded per book, like a bulk edit.
- **Still one click** if you trust the defaults: upload, Import.

### Non-goals

Other import sources; picking a different match by hand; metadata or cover
lookup during the import; Goodreads shelves becoming collections; overwriting
anything in Libaraxia with Goodreads values. (Reasons in section 17.)

## 2. Principles, in priority order

1. **Never write what the user hasn't seen** (from 14a).
2. **Add, never overwrite.** The import fills empty fields and adds missing
   rows. It never changes or deletes a value that exists. Two things look
   like changes and are shown per row: the wishlist-then-read decisions,
   which move a wishlist entry, and an earlier Goodreads review, which is
   appended below yours, leaving your text untouched (section 6).
3. **Never overwrite a later change** (from 14a): apply and undo re-check.
4. **The shelf is what you own.** Nothing is added as owned unless the user
   says so.
5. **Pleasant beats clever.** A few boxes with plain words; sensible
   defaults; no per-field toggles.
6. **Reuse the existing rules and machinery:** `parse_row`, `BookIndex`, the
   bulk journal and its guarded undo, `on_shelf` / Show: Not owned.

## 3. Constraints

Everything in `BULK-EDIT-SPEC.md` section 3 applies unchanged (raw
`sqlite3`, no new dependencies, no inline JS, POST + CSRF, permission in SQL,
the browser sends ids and choices never columns, all four styles light and
dark, keyboard-complete, 375 px, reduced motion, generic error messages, no
emojis). In addition:

- **Books only.** Every query this phase writes on `books` adds
  `media_type = 'book'` or `media.only(BOOK, ...)`.
- **Matching** only through `BookIndex` (your books and your household's
  shelf), plus this phase's own Goodreads Book Id memory, which only ever
  points at books `BookIndex` could have matched. Never all of `books`.
- **Deleting a created book on undo** goes through
  `models.other_users_with_book_data`, and its cover file through
  `delete_image_file()`.
- **Statuses** written by the import are `quiet = 1` (031), so a 400-row
  import doesn't fill friends' feeds.
- **Migration 032** (030 is reserved for 15.1, 031 is bulk edit). Additive
  only: new tables, no rebuilds, so it can go through prod early and safely.
- **One outcome per CSV row** (the invariant `tests/test_goodreads.py`
  asserts): every row of the file is accounted for in the result.

## 4. What the code already does (checked 2026-11-11)

Re-check any fact a step depends on before relying on it.

1. **Parsing is reusable as is.** `goodreads.parse_row(row)` returns clean
   values plus a decided status (`read`, `currently reading`,
   `did not finish`, `wishlist`, or None for an unknown shelf with no sign of
   reading) and an `audiobook` flag. `decode_csv`, `REQUIRED_COLUMNS` and the
   `ImportFileError` check are reusable too. It ignores the export's
   **`Book Id`** column, which is Goodreads' stable id for the book.
2. **`BookIndex`** (`utils/book_matching.py`) indexes your own book rows
   (wishlist entries, `owned = 0` and removed rows included, each tagged
   `is_wishlist_entry`) and your household's shelf (`library_books`, never
   their wishlist). `match(isbns, title, author)` returns `(book, whose)`,
   ISBN first, your own before the household's, on-shelf before removed.
3. **Today's writer** is `_Importer.row`: for a matched book that already has
   any status it returns `already` before reaching the rating, review,
   sessions or shelves, so a re-import adds nothing to it.
4. **Ownership today:** `books.owned` defaults to 1. A new `read` row creates
   an owned book (only audiobooks get `owned = 0`). A matched wishlist entry
   that Goodreads says is read has its `wishlist` row deleted, which puts it
   on the shelf as owned.
5. **Shelves today:** every Goodreads shelf except the status ones becomes a
   Books custom collection (`user_collections`), created if missing.
6. **Reading stats count `reading_sessions`** whatever the book's ownership
   or wishlist state (`utils/stats.py`: reading goal, year by year). So a
   read-not-owned book, or a wishlist entry with a session, counts as read.
7. **Show: Not owned** already exists on the Books grid
   (`book_utils.SHOW_CHOICES`, `shelf_filter`). That is the "read, but not in
   your library" place: no new section needed.
8. **`wishlist.remove_from_wishlist`** keeps a read item as `owned = 0` and
   puts it on a "Read but not owned" custom collection. The import does not
   copy that collection behaviour (Phil: no automatic collections).
9. **Bulk journal** (`utils/bulk.py`): `bulk_edits` / `bulk_edit_items`
   (PK `edit_id, book_id`), `undo()` calls the action's `current()` and
   `restore()` per item after `can_view_book`, `undoable()` and `recent()`
   feed Profile -> Recent bulk edits, journals older than 30 days are swept
   at the start of each `apply()`. Actions are looked up in `ACTIONS` by key.
10. **The result screen** (`static/goodreads_import.js`) shows per-row
    outcomes and offers to start the background cover fetch
    (`covers_missing`, `cover_jobs`).
11. **`tests/test_goodreads.py`** has 20 tests, several asserting today's
    defaults (owned read books, collections from shelves, Want to Read for
    owned to-read books). Those change in this phase on purpose (step 3).

## 5. The experience, start to finish (Phil's re-import)

1. Profile -> **Import from Goodreads** (same page as today, text updated).
   Choose `goodreads_library_export.csv`, press **Review import**. Nothing is
   written; the file is parsed into a staging table and you land on the
   review page.
2. The review page opens with a summary line and the boxes in section 6:

```
 IMPORT FROM GOODREADS                       goodreads_library_export.csv
 612 rows. Nothing is saved until you press Import.

 [ Import 214, leave 12 undecided ]

 ┌ NEEDS A DECISION (12) ────────────────────────────────────────────────┐
 │ Currently reading on Goodreads (9). Where are you with these now?     │
 │ [ ] Normal People · Sally Rooney · added 2024-02-10                   │
 │     ( Ask ▾ )  Still reading / Finished / Did not finish / Skip       │
 │ Read on Goodreads, on your Libaraxia wishlist (3)                     │
 │ [ ] The Overstory · Richard Powers · read 2023-04-02 · ★5             │
 │     ( Ask ▾ )  Read it, still want it / Read it, don't want it /      │
 │                Bought it / Skip                                       │
 └───────────────────────────────────────────────────────────────────────┘
 ┌ READ, NOT IN YOUR LIBRARY (171) ──────────── Add as read, not owned ─┐
 │ Comes in read, with your rating, review and reading dates. Off the    │
 │ shelf; under Books -> Show: Not owned.                                │
 │ [ ] Piranesi · Susanna Clarke · read 2022-01-09 · ★5 · review        │
 │ [ ] Dune · Frank Herbert · audiobook · read 2021-06-30 · ★4          │
 │ ... Show all 171                                                      │
 └───────────────────────────────────────────────────────────────────────┘
 ┌ ALREADY IN LIBARAXIA, SOMETHING TO ADD (28) ───── Add what's missing ┐
 │ [ ] Cat's Cradle · yours · adds: a reading session (2019-03-11)      │
 │ [ ] Beloved · Bob's copy · adds: rating ★4, review                   │
 │ [ ] Cat's Cradle · yours · adds: session (2011-05-02), Goodreads     │
 │     review below yours                                    [preview]  │
 └───────────────────────────────────────────────────────────────────────┘
 ┌ ON YOUR GOODREADS WANT-TO-READ LIST (40 to add, 22 nothing to do) ───┐
 │ Not in Libaraxia (40) ...................... Add to wishlist          │
 │ Nothing to do (22): you own it now (14) · already on your wishlist   │
 │ (5) · you read it here (2) · you let it go (1)            [Show]     │
 └───────────────────────────────────────────────────────────────────────┘
 ┌ NOT SURE (2) ─────────────────────────────────────────────── Skip ───┐
 │ On a Goodreads shelf with no reading recorded: "kindle-deals".       │
 └───────────────────────────────────────────────────────────────────────┘
 ┌ NOTHING TO DO (346) ────────────────────────────────────── [Show] ───┐
 │ In Libaraxia and nothing missing (325) · 6 ratings differ, yours kept│
 │ skipped last time (12) · same book as another row (2) · no title (1) │
 └───────────────────────────────────────────────────────────────────────┘

 Filter: [All boxes ▾] [Goodreads shelf ▾] [search titles      ]
```

3. Phil ticks rows (click, shift-click for a range, "Select all in this
   box"), and the selection bar offers the choices valid for all of them:
   "Add to my library" for the eleven he does own after all, "Skip" for a
   run of to-reads he no longer wants. Choices save as he goes (a reload
   keeps them).
4. He answers the decisions: selects the 9 currently-reading rows, sets 6
   to Did not finish and 3 to Finished; answers the 3 wishlist ones. Any he
   leaves on Ask are **not imported** this time; the button says so ("Import
   214, leave 12 undecided"), and they come back in this box the next time he
   uploads an export.
5. **Import**. The result: one line per outcome, counts that add up to
   612, **Undo this import**, and "Fetch covers for 171 books" (today's
   cover job). The import also appears in Profile -> Recent bulk edits.
6. Later: Books -> filter **From Goodreads**, Show: Everything, bulk edit
   anything that needs it. A review looks wrong: the book page says what the
   import wrote, and when.

A **first-time user** sees the same page with almost everything in "Read, not
in your library" and the want-to-read box; Import with the defaults gives
them their history (not owned) and their wishlist, and they move the books
they own onto the shelf with "Add to my library" before importing, or with
bulk edit's Owned action afterwards.

## 6. Classification: boxes, defaults, choices

Each staged row is classified fresh every time the review page loads (from
the staging row plus the database now), so it is never out of date.

### Matching, in order

1. **Goodreads Book Id memory:** the latest not-undone `goodreads_rows` row
   (section 9) for this user and `Book Id` whose `book_id` still exists and
   is your own book (`added_by` = you) or on your household's shelf. Exact,
   and survives a retitled or re-ISBN'd book.
2. Else **`BookIndex.match`** as today.
3. A row whose matched book (or `Book Id`) was already matched by an earlier
   row in the same file is **"Same book as line N"**, nothing to do. (Today
   the second row comes out `already`; same effect, clearer words.)

Match kinds: `none`, `wishlist` (your wishlist entry), `shelf` (yours, owned,
not removed), `not_owned` (yours, `owned = 0`), `removed` (yours, removed),
`household` (a household member's shelf copy).

### What Goodreads says

From `parse_row`: **read-like** (`read`, `currently reading`,
`did not finish`), **to-read** (`wishlist`), **unknown** (None), or **no
title** (nothing to do, as today).

### The boxes

| Box | Goodreads | Match | Default | Other choices |
|---|---|---|---|---|
| Needs a decision: currently reading | `currently reading` | `none`, or a match where you have no status | `ask` | `still_reading`, `finished`, `dnf`, `skip` |
| Needs a decision: wishlist | read-like | `wishlist` | `ask` | `keep_wished`, `drop_wish`, `bought`, `skip` |
| Read, not in your library | `read`, `did not finish` | `none` | `not_owned` | `library`, `skip` |
| Already in Libaraxia, something to add | read-like | `shelf`, `not_owned`, `removed`, `household` | `fill` | `skip` |
| Want-to-read: not in Libaraxia | to-read | `none` | `wishlist` | `skip` |
| Want-to-read: nothing to do | to-read | any other | (none) | (none) |
| Not sure | unknown | `none` | `skip` | `not_owned`, `wishlist` |
| Nothing to do | see below | | (none) | see below |

**Nothing to do** collects: read-like matches with nothing missing (with a
count of those that differ, yours kept, expandable to show both values);
unknown-shelf rows that match something you have; rows skipped in an earlier
import (section 9: default `skip`, but they keep their box's choices so a
past skip can be undone); same book as another row; no title.

**Want-to-read, nothing to do** reasons: you own it now (`shelf` or
`household`), already on your wishlist (`wishlist`), you read it here
(`not_owned`), you let it go (`removed`). Shown, not written. Today an owned
to-read book got the *Want to Read* status; that stops (Phil: the status is
hardly used, and the import adds no statuses beyond what Goodreads recorded
as read).

### What each choice writes

All new statuses `quiet = 1`, `created_at` / `updated_at` = Goodreads Date
Added when present (as today). Sessions as today: Read Count sessions, at
least one, the last dated Date Read, earlier ones undated; only for `read`.

| Choice | Writes |
|---|---|
| `not_owned` | new book, `owned = 0` (format Audiobook if `audiobook`), status, rating + review, sessions |
| `library` | the same with `owned = 1` |
| `wishlist` | new book + `wishlist` row, note = Private Notes, `added_at` = Date Added; rating/review if any (as today) |
| `fill` | only what's missing (below), on the matched book |
| `keep_wished` | on the wishlist entry: status, rating/review if missing, sessions; stays on the wishlist |
| `drop_wish` | delete the `wishlist` row, set `owned = 0`, then as `keep_wished` |
| `bought` | delete the `wishlist` row, keep `owned = 1`, then as `keep_wished` |
| `still_reading` / `finished` / `dnf` | the status you chose (`currently reading` / `read` / `did not finish`) instead of Goodreads'; on a new book, created not owned; with `finished`, one undated session (Goodreads has no finish date for it) plus rating/review; on a match, as `fill` with your status |

**Currently reading is decided at import time** (Phil, 2026-11-11):
Goodreads' "currently reading" is as old as the export, so the import asks
rather than guessing. A currently-reading row that matches a book where you
already have a status here is not asked: Libaraxia's status wins, and the
row is `fill` or Nothing to do like any other match. A currently-reading row
whose wishlist entry matches goes to the wishlist decision, with `finished`
semantics for its status.
| `skip` | nothing (remembered, section 9) |

**`fill`: what counts as missing.** Each item is shown on the row ("adds:
rating ★4, review, a reading session (2019-03-11)").
- **Status:** you have no status on it -> the Goodreads status. You have one
  -> kept; if different, listed as a difference.
- **Rating:** yours is NULL -> Goodreads'. Different -> difference, kept.
- **Review:** yours is NULL or empty -> Goodreads' (plain text, as today).
  Yours already contains the Goodreads text (compared folded: case,
  whitespace) -> nothing. Otherwise **appended below yours** (Phil,
  2026-11-11), as part of `fill`, no extra choice:

  ```
  <your review, unchanged>

  ----
  Goodreads review, read 2011-05-02, ★3:
  <the Goodreads review>
  ```

  For a book re-read and reviewed again here: one review per user per book
  (`read_data`), so this keeps the old one without a second field. Reviews
  render as plain text with `pre-wrap`, so the `----` shows as a divider
  line. The date is Date Read, or Date Added when there is none ("added
  ..."); the stars only when Goodreads has a rating. Your rating is never
  changed. The row's [preview] shows the combined text. On a re-import the
  Goodreads text is found inside yours, so it's never appended twice. Undo
  restores your review exactly (the `read_data` snapshot). Don't want it on
  one book: Skip that row.
- **Reading sessions** (Phil's addendum: added to, never overwritten or
  duplicated):
  - You have **no sessions** on the book and Goodreads says `read`: add Read
    Count sessions exactly as for a new book.
  - You have sessions: add **one** session dated Date Read if no session of
    yours on the book has that `date_completed`. Nothing else: undated
    Goodreads reads can't be told apart from yours.
  - Existing sessions are never edited or deleted.
- Private Notes are still not imported for library books (no column).
- A row whose `fill` would add nothing goes to Nothing to do.

`keep_wished` / `drop_wish` / `bought` use the same `fill` rules for the
status, rating, review and sessions on the wishlist entry.

### Validity

The server owns the table above as data (`goodreads_plan.CHOICES` per box).
A choice not valid for a row's box is refused with a message, never silently
coerced. `ask` is only ever a default, never something the user sets.

## 7. The review page

Full page at `GET /user/import_goodreads/review`, extends `base.html`,
`crumbs([('Profile', ...), ('Goodreads Import', ...)], 'Review')`.
No staging -> redirect to the import page with "Upload your export first."

- **Boxes** in the order of section 6, each a `card` with a heading, one
  sentence of explanation, its default shown in the header ("Add as read,
  not owned"), and its rows. A box with more than 12 rows starts closed with
  its first 12 shown and "Show all N" (bulk's `OPEN_ALL_UP_TO` idea). Empty
  boxes are not shown.
- **A row:** title, author, match (`yours` / `Bob's copy` / `on your
  wishlist` / `not owned` / `removed`, linked to the book), Goodreads shelf
  and Date Read, rating, "review" if it has one, "audiobook", what `fill`
  adds or what differs, and its choice as a small select. Covers only for
  matched books (the export has none), using `coverSrc` and the
  `upload_exists` fallback.
- **Selecting** reuses bulk edit's interaction: a checkbox per row, click,
  shift-click range (`rangeBetween`), Escape clears, "Select all in this
  box". The **selection bar** (`_bulk_bar.html`'s look, its own markup)
  shows "N selected" and buttons for the choices valid for every selected
  row; choosing posts once for all of them.
- **Filters** above the boxes: box, Goodreads shelf (every shelf in the
  file, so "kindle" or "2019-challenge" rows can be found and set
  together), title/author search (`fold`). Client-side: the page holds every
  row (5000 cap).
- **Choices persist** server-side on the staging row
  (`POST /user/import_goodreads/choose`), so a reload or a phone lock loses
  nothing. Optimistic in the page; on failure the select reverts and a flash
  says why.
- **Import button** at top and bottom: "Import N" where N is the rows that
  will write something; with undecided rows it names them: "Import 214,
  leave 12 undecided". Undecided rows write nothing and are not remembered
  as skipped, so the next upload asks again. No confirmation dialog: the page is the
  review. **Start over** (POST, discards the staging) and **Cancel** (back to
  the import page; the staging stays for 24 hours).
- **Stale:** apply re-plans and compares the fingerprint; if your data moved
  (you added a review in another tab), the page reloads with "Some rows
  changed since you looked; check them and import again." Choices survive.
- Keyboard: every row control reachable by Tab, Space toggles a row's
  checkbox. At 375 px a row stacks: title line, details line, select.

### The result

Shown in place of the boxes after apply (the staging is deleted, so
reloading the review URL afterwards goes back to the import page). One line per outcome with counts that add up to the file's rows
(section 8), "Show rows" per outcome, **Undo this import**, and the cover
fetch offer exactly as today (`covers_missing`, `cover_jobs`). A link to
Books filtered to From Goodreads.

## 8. Outcomes (one per CSV row)

Replace `OUTCOMES` with:

```python
OUTCOMES = {
    'not_owned': 'Added as read, not owned',
    'library':   'Added to your library',
    'wishlist':  'Added to your wishlist',
    'filled':    'Added what was missing to a book you have',
    'decided':   'Imported as you decided (currently reading, or wishlist and read)',
    'later':     'Left for later (needs a decision)',
    'nothing':   'Nothing to do',
    'skipped':   'Skipped',
    'error':     'Failed, nothing saved for this row',
}
```

The counts always add up to the number of data rows in the file. The result
can show each row's detail ("same book as line 41", "you own it now").

## 9. Data: staging, provenance, undo

### Migration 032 (`032_goodreads_import.sql`, folded into `create_database.sql` and its ledger INSERT)

```sql
-- A Goodreads upload waiting for review (ROADMAP 14b). One upload per user:
-- a new one replaces it. Swept after 24 hours. Not in the session cookie.
CREATE TABLE goodreads_staging (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    line INTEGER NOT NULL,          -- CSV line, 2 = first data row
    data TEXT NOT NULL,             -- parse_row() output plus goodreads_id and shelves, JSON
    choice TEXT,                    -- NULL: the box's default
    filename TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, line)
);

-- One row per applied import. Permanent (unlike bulk_edits, swept at 30 days).
CREATE TABLE goodreads_imports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    edit_id INTEGER REFERENCES bulk_edits(id) ON DELETE SET NULL,  -- undo, while it lasts
    filename TEXT,
    row_count INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    undone_at TIMESTAMP
);
CREATE INDEX idx_goodreads_imports_user ON goodreads_imports(user_id);

-- What each CSV row of an import did: the provenance behind the "From
-- Goodreads" filter, the book page note, and the next import's Book Id match.
CREATE TABLE goodreads_rows (
    import_id INTEGER NOT NULL REFERENCES goodreads_imports(id) ON DELETE CASCADE,
    line INTEGER NOT NULL,
    goodreads_id TEXT,              -- the export's Book Id; NULL if missing
    book_id INTEGER REFERENCES books(id) ON DELETE SET NULL,
    outcome TEXT NOT NULL,          -- an OUTCOMES key
    wrote TEXT,                     -- JSON list: book, status, rating, review, sessions, wishlist
    shelves TEXT,                   -- the row's Goodreads shelves, comma-separated
    PRIMARY KEY (import_id, line)
);
CREATE INDEX idx_goodreads_rows_book ON goodreads_rows(book_id);
CREATE INDEX idx_goodreads_rows_gid ON goodreads_rows(goodreads_id);
```

Why tables and not a yes/no column on `books` (Phil's first idea): a book row
is shared with the household, so a column can't say whose import touched it;
and it couldn't mark a review or session added to a book that already
existed. `goodreads_rows` records, per user, exactly what each row wrote.

Rows recorded: every row that matched or created a book, **including
"nothing to do" matches** (`wrote` empty). So after one 14b import, every
book that appears in your Goodreads export is findable under From Goodreads,
including those brought in by the old importer. Skipped rows are recorded
with `book_id` NULL (that's the "skipped last time" memory). No-title and
error rows are not recorded.

### Staging rules

- `POST /user/import_goodreads/plan` replaces the user's staging rows in one
  transaction. Cap 5000 data rows ("This file has 6200 rows; the import takes
  up to 5000. Split it in a spreadsheet and import twice.").
- Swept lazily: at the start of each plan, delete staging older than 24
  hours (every user's). No scheduler.
- Deleted after a successful apply, and by Start over.

### Undo, through the bulk journal

- Apply writes one `bulk_edits` row, action **`goodreads`**, summary e.g.
  "Goodreads import: 171 added as not owned, 40 to your wishlist, 28 filled",
  and one `bulk_edit_items` row **per book written** (rows with an empty
  `wrote` and skips get none), in the same SAVEPOINT as the row's writes.
  `goodreads_imports.edit_id` points at it.
- **Snapshots** hold only what the row wrote, keyed by part:
  `{"book": {...}, "status": {...}, "read_data": {...}, "sessions": [ids],
  "wishlist": {...}}`. `before` holds those parts as they were (None where
  no row existed; for a created book `before` is NULL). The book part covers
  `title, author, isbn, format, genre, owned, removed_at` (not the cover:
  the cover job will have set one, and that must not block undo).
- **`current()`** returns the same parts as they are now; undo's existing
  guard (`current == after`) then decides, per book, as for any bulk edit.
- **`restore()`**: put back each part (`before` None -> delete that row; a
  session list -> delete those session ids; wishlist moves -> re-insert the
  `wishlist` row and the old `owned`). For a **created book**, delete it only
  if, in addition, `other_users_with_book_data` finds nobody and you have no
  tags, collection entries or other sessions on it; delete its cover file
  through `delete_image_file()`. Otherwise leave it, counted "changed since".
- `bulk.py` changes, small: `_action('goodreads')` resolves to the Action in
  `goodreads_plan.py` (imported inside the function, avoiding a circular
  import), and `Action` gains an optional `after_undo(conn, user, edit_id)`
  hook, which the import uses to set `goodreads_imports.undone_at`. Undo of
  an import shows in Profile -> Recent bulk edits like any other edit, and
  is not itself undoable (14a rule).
- An undone import's `goodreads_rows` stay but are ignored by the filter,
  the book page note and the Book Id memory (`undone_at IS NULL`).
- After 30 days the journal is swept as usual; the import can no longer be
  undone, and its provenance stays.

## 10. Provenance in the UI

- **Books grid filter: From Goodreads** (`?from=goodreads`, a checkbox in
  the filter panel, books only). In `utils/grid_query.py` so bulk edit's
  "select all in this view" matches the page. SQL: `EXISTS (SELECT 1 FROM
  goodreads_rows r JOIN goodreads_imports i ON i.id = r.import_id WHERE
  r.book_id = b.id AND i.user_id = ? AND i.undone_at IS NULL)`, with the
  viewer's id. Works with every Show choice (the not-owned history is under
  Show: Not owned or Everything). Counts in `is_narrowed`.
- **Book page note**, for your own provenance only, quiet text near your
  review/sessions: "From your Goodreads import, 14 Nov 2026: review, rating,
  2 reading sessions." or "Matched by your Goodreads import, 14 Nov 2026;
  nothing added." Latest not-undone import first; one line per import.
- Not in the export, the feed, friends' views or the household's view.

## 11. Feed side effects

None new. Statuses are `quiet = 1`; reviews already appear only through
their own paths; created books keep Date Added as `created_at` (as today), so
they don't show as "added today". Wishlist entries: as today.

## 12. Back end

### Modules

- **`utils/goodreads.py`**: keeps parsing (`decode_csv`, `parse_row` plus
  `goodreads_id` and raw `shelves` added to its output, and the helpers). The
  writing helpers in `_Importer` (`create_book`, status, review, sessions,
  wishlist) become plain functions taking `conn, user_id`, used by the
  planner; they gain `owned` and `quiet` arguments. `add_to_collections`,
  `import_goodreads()` and `_Importer.run` are deleted with the old route.
- **`utils/goodreads_plan.py`** (new; no Flask context, like `bulk.py`):
  - `stage(conn, user, text, filename)`: check columns, parse, cap, replace
    staging, sweep. Raises `ImportFileError`.
  - `plan(conn, user)`: load staging, `BookIndex`, the Book Id memory and
    your rows on matched books in a handful of queries (not per row), and
    return a `Plan`: rows with box, match, default, choice, what `fill` adds,
    differences, plus counts per box and a fingerprint (as bulk's: sha256 of
    each row's line, match id, before snapshot and effective choice).
  - `choose(conn, user, lines, choice)`: validate per row against its box,
    write `goodreads_staging.choice`. Returns per-line results.
  - `apply(conn, user, fingerprint)`: re-plan, `StalePlan` if moved, sweep
    the bulk journal (as `bulk.apply` does), one transaction, one SAVEPOINT
    per row (writes + `bulk_edit_items` + `goodreads_rows` inside it), report
    with one outcome per row, delete staging, commit. Returns the report and
    the edit id.
  - The undo `Action` (`current`, `restore`, `summary`, `after_undo`).
  - `CHOICES`, `BOXES`, `OUTCOMES` as data.
- **`blueprints/user.py`** (next to the old route, which is removed):

| Route | Method | Notes |
|---|---|---|
| `/user/import_goodreads_page` | GET | as today; text updated; shows "You have an import waiting for review" with a link if staging exists |
| `/user/import_goodreads/plan` | POST | upload; `@limiter.limit("10 per hour")`; redirects to review (form post) or returns JSON with its URL (fetch) |
| `/user/import_goodreads/review` | GET | the page |
| `/user/import_goodreads/choose` | POST | JSON `{lines: [...], choice}` |
| `/user/import_goodreads/apply` | POST | JSON `{fingerprint}`; `@limiter.limit("3 per hour")` (applies, not plans) |
| `/user/import_goodreads/discard` | POST | Start over |

  Undo uses the existing `POST /bulk/<id>/undo`.
- **Templates:** `goodreads_import.html` (upload, text updated),
  `goodreads_review.html` (new), partials as the builder sees fit.
- **JS:** `static/goodreads_review.js` (new) for the review and result;
  `static/goodreads_import.js` shrinks to the upload. The review page loads
  `bulk.js` first for its pure helpers (`rangeBetween`, `fold`): check that
  its browser part does nothing without `#book-container`; if it doesn't,
  stop and ask rather than copying helpers. Pure helpers in
  `goodreads_review.js` (which choices a selection allows, filter matching)
  are tested under node like `bulk.js`.

### Permission

Everything is the current user's own: staging and choices by `user_id` in
SQL; writes only to the user's own rows, or a household shelf copy they can
view (`can_view_book`, checked again at apply, as today's matching implies).
Undo by `bulk_edits.user_id` (existing).

## 13. Tests

- **Changed on purpose** (step 3 lists each, before and after, for Phil):
  read rows not owned by default; no collections from shelves; no Want to
  Read for owned to-read rows; matched-with-status rows now `fill`.
- **Classification:** one test per box and per want-to-read reason; Book Id
  memory beats a changed title; duplicate rows; household match; removed
  match; skipped-last-time default.
- **`fill`:** each part added only when missing; differences kept and
  listed; a differing review is appended after `----` and the dated label,
  your text and rating unchanged, a re-import doesn't append again, undo
  restores exactly; sessions: none -> Read Count sessions; some -> one dated session
  only if that date is absent; never edits or deletes a session.
- **Choices:** valid per box; invalid refused; persisted; `ask` rows write
  nothing, aren't remembered as skipped, and are asked again next upload.
  Currently reading: asked when new or no status here; not asked when you
  have a status; `finished` adds one undated session.
- **Apply:** one outcome per row and counts add up to the file; a failing row
  leaves nothing (SAVEPOINT) and the rest carry on; stale fingerprint;
  statuses quiet; `goodreads_rows` and journal written per row; staging gone.
- **One click:** apply with all defaults on a mixed file gives the expected
  outcome for every row (the restated equivalence: today's behaviour with
  this phase's defaults).
- **Undo:** created books deleted (cover file too) when untouched; kept when
  you've tagged one, added a session, or a household member reviewed it;
  filled parts removed only where unchanged; wishlist moves reversed; undone
  import ignored by filter, note and memory; second undo refused.
- **Re-import:** importing the same file twice: second plan is all Nothing
  to do (plus previous skips), writes nothing.
- **Access:** another user's staging, choices and apply are unreachable;
  provenance never shown to others; From Goodreads filter only your rows.
- **Pages:** `test_every_page_loads` covers the review page (with and
  without staging); CSP test passes.
- **Migration:** `test_migrations` green; 032 on a copy of the dev DB.

## 14. Development pipeline (builder: follow this exactly)

`BULK-EDIT-SPEC.md` section 14 applies with these names:

- Branch **`phase-14b-goodreads-import`**, worktree
  **`../libaraxia-import`**, private DB **`import-dev.db`**
  (`sqlite3 ../libaraxia/library.db ".backup import-dev.db"`).
- Worktree setup as there (venv, node_modules, `.env`, uploads link: note
  this phase's undo **deletes cover files** of created books, so in the
  worktree point `static/uploads` at a **copy**, not a link to the real
  folder: `cp -a ../libaraxia/static/uploads static/uploads`. Check
  `git status` doesn't show it; it is ignored).
- Dev server port 5001 if 5000 is busy, bound to 0.0.0.0, against
  `import-dev.db`; tell Phil the LAN URL.
- Each step: tests first where stated, `venv/bin/pytest` green, stop and
  report (what changed, test counts, spec mismatches, what to click).
- Dev server: port 5001 (Phil, 2026-11-11: whatever is on 5001 may be
  stopped; never touch 5000, his own server).
- Only migration 032.

### Git (changed by Phil, 2026-11-11; replaces "Phil commits")

Phil works on `main` and doesn't want to manage the branch. The builder
does all the git work; Phil only reviews and pushes.

- **Per step:** build, tests green, report. Leave the step uncommitted until
  Phil approves it (on the dev server for UI steps, or by saying so). Then
  commit it on `phase-14b-goodreads-import`, in the worktree, with the
  ROADMAP tick in the same commit. Commit messages like Phil's (subject line,
  short body), **no Claude attribution or trailers**. Stage files by name,
  never `git add -A` (the worktree holds `import-dev.db` and an uploads copy).
- **Docs the step needs from `main`:** if `main` gained commits the branch
  needs, `git merge main` in the worktree. Say so in the report.
- **Never push**, never open PRs, never rebase or force anything.

### Merging (builder, when Phil says so; Phil pushes)

- **M1 after step 2:** migration 032 alone (additive tables, nothing reads
  them yet). Puts it through prod while it's trivial.
- **M2 after step 7:** the feature, after the dry run.

How: in the main checkout (`/home/phil/coding/libaraxia`), first check
`git status` is clean (if Phil has uncommitted work there, stop and ask),
then `git merge --no-ff phase-14b-goodreads-import`, `venv/bin/pytest`, and
`venv/bin/python manage.py --db <a fresh backup copy of library.db> migrate`.
Then tell Phil to `git push`: **the push deploys to prod** (CI, then
`deploy.sh`, which runs the migration). The branch and worktree stay until
M2; after M2, `git worktree remove ../libaraxia-import` (ask first: it
deletes `import-dev.db` and the uploads copy) and `git branch -d` the
branch.

### The dry run on a prod copy (step 7, Phil)

The safety net for "scared to mess with prod":

1. On the server: `sqlite3 <prod db> ".backup /tmp/prod-copy.db"`; copy it
   to the worktree as `prod-copy.db` (never commit it).
2. `DATABASE_PATH=prod-copy.db venv/bin/python manage.py migrate`, then run
   the dev server on it.
3. Upload the real export. Read every box. Import. Explore: From Goodreads
   filter, Show: Not owned, book page notes, stats. **Undo**, check it's back
   as it was, import again.
4. Anything wrong: report it, fix on the branch, repeat from 1.
5. Only then M2. On prod, take a backup (or ZFS snapshot) before importing;
   undo is there for 30 days, the backup for anything undo can't do.

## 15. Build order (Phase 14b)

1. **Pin the parser.** Add `goodreads_id` and `shelves` to `parse_row`;
   tests for both. No behaviour change.
   *Accept:* suite green.
2. **Migration 032**, folded into `create_database.sql` and the ledger;
   applied to `import-dev.db`. *Accept:* `test_migrations` green, `manage.py
   status` clean. **M1.**
3. **`goodreads_plan.py`, stage + plan, headless.** Classification and
   `fill` (section 6), choices, fingerprint. Tests first, from section 13,
   including the list of old tests whose expectations change and why.
   *Accept:* Phil's re-import cases pass as tests; nothing writes yet.
4. **Apply and undo, headless.** Writers refactored out of `_Importer`;
   apply with SAVEPOINTs, provenance, journal; the `goodreads` Action and
   `after_undo` hook in `bulk.py`. *Accept:* apply/undo/re-import tests.
5. **Routes and the review page.** Upload -> review -> choose -> apply ->
   result with undo and covers; the old route and `_Importer.run` removed;
   import page text rewritten for the new defaults. *Accept:* Phil walks
   section 5 on the dev server with his own export, all four styles, light
   and dark, phone width.
6. **Provenance in the UI:** From Goodreads filter (grid_query), book page
   note. *Accept:* filter + bulk select-all-in-view agree; note shows on an
   imported book, not on a friend's view.
7. **Dry run on a prod copy** (section 14, Phil), fixes from it, then
   wrap-up: ROADMAP 14b ticked and archived, `docs/ARCHITECTURE.md`
   (`goodreads_plan`, the three tables, routes, JS), CLAUDE.md data-model
   line for `goodreads_rows`. **M2.**

## 16. Decisions Phil may change

1. **New read books come in not owned** (`not_owned` default). Flip one
   constant in `CHOICES` to restore today's owned default.
2. **No collections from Goodreads shelves.** The shelves are kept in
   `goodreads_rows.shelves` and filterable on the review page, so a later
   "Goodreads shelf" grid filter or mapping is possible without re-import.
3. **No Want to Read status** for to-read books you already own.
4. **Undecided rows don't block Import.** The button names them ("Import
   214, leave 12 undecided"); they write nothing and are asked again on the
   next upload. Flip: disable Import while any row is on Ask.
5. **Differences are shown, never applied.** Ratings and statuses: yours
   always. A differing review is appended below yours after `----`, never
   replacing it.
6. **Sessions:** only a missing Date Read is added once you have sessions.
7. **Undo 30 days** (the bulk journal's), provenance permanent.
8. **Staging 24 hours, 5000 rows**; no 500 cap on apply (an import is
   bounded by its file and fully reviewed).
9. **Goodreads "currently reading" is asked at import time** (Still reading
   / Finished / Did not finish / Skip), unless you already have a status on
   the book here.
10. **Migration 032**, M1 alone.

## 17. Out of scope, with reasons

- **Other sources** (StoryGraph, LibraryThing, Letterboxd, Discogs): one
  format first. Staging, boxes and provenance are generic enough that a
  second parser could feed them later.
- **Choosing a different match by hand:** a second matcher beside
  `BookIndex`; revisit if the dry run shows wrong matches.
- **Overwriting Libaraxia values with Goodreads ones:** Libaraxia is the
  newer record (principle 2).
- **Metadata or cover lookup during import:** slow and rate-limited; 8F's
  problem; the cover job runs after, as today.
- **Collections from shelves, a Goodreads-shelf grid filter:** Phil's call,
  and the data is kept for later (decision 2).
- **Private notes on library books:** no column; a separate feature.
- **Sync or scheduled import:** Goodreads has had no public API since 2020.
- **Per-row undo, undo of an undo:** as for bulk edits.
- **Provenance in the data export:** later, if wanted; one column.
