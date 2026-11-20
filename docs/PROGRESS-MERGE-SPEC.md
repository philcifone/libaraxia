# Manual reading progress and Merge two records (ROADMAP 16.0f)

Approved 2026-11-20 ("go ahead"), from Phil's notes of 2026-11-19 in
ROADMAP 16.0f; his answers are folded in below. Suggested branch
`phase-16f-progress-merge`: progress first, then the merge tool, then the
dash-subtitle leftovers.

Part A is a small feature for readers. Part B is an admin repair tool. They
share a phase because both should land before the code review (16.0h), not
because they share code.

---

# Part A: Manual reading progress

## A1. What it is for

Audiobookshelf already draws a progress ring on the cover of an audiobook
you're listening to (16.0e). Books it doesn't track (paper books, ebooks read
somewhere else) have no progress at all: only the status Currently Reading
and a session with a start date. A user should be able to say "page 140" or
"about 40 %" and see the same ring.

## A2. Decisions (Phil, 2026-11-20)

- **Per reading session, not per book.** Progress lives on the *open*
  session (started, not finished). A re-read starts its own session, so it
  starts again at 0, and the first read's history isn't touched.
- **You type a page; the app does the maths.** A book with a page count
  takes a page ("140 of 312") and the app works out the percent. Stored as
  `progress_page` plus `progress` (0 to 1, derived), so the ring always reads
  `progress`. 348 of the 466 books on dev have a page count. Without one, or
  for an ebook or an audiobook not on ABS (where page counts mean little),
  the field takes a percent instead.
- **No page count? Percent only.** The progress form doesn't edit the book's
  page count: only the owner can edit a book, and progress is anyone's.
- **Where you set it:**
  1. The item page's reading history (`#item-history`): the open session
     shows "On page [140] of 312 · 45 %" with a Save button. A plain POST
     form, no script (the chips there work the same way).
  2. ~~The session form gets the same field.~~ Dropped while building
     (2026-11-20): the field above already opens a session when there's
     none, so a second way in only added a field to the dates form.
  - Not in this phase: a quick control on the Currently Reading row in
    Collections. It's possible later, but the item page is one tap away.
- **Setting progress with no open session** opens one, started today, and
  sets the status to Currently Reading if it isn't already (the same rules
  as starting a session today). The date can be edited afterwards, as now.
- **Reaching the end** (last page or 100 %) doesn't finish anything on its
  own. The page shows "Finished? [Mark as read]", which completes the
  session through the existing route.
- **The ring:** the same `progress_ring()` on every cover, from one source.
  **When a book has both, the newer one wins.** Listening moves the ABS
  value; updating the page moves the manual one; whichever changed last is
  what the ring and the item page show, and the other is shown under it,
  smaller ("Audiobookshelf: 62 %, 3 days ago"). Needs a time on the ABS
  side: `abs_links.progress_at` (migration 046), set whenever Sync or the item
  page's live line stores a progress value that differs from the last one.
  ABS's own `lastUpdate` from its progress record is the better time when
  the live line has it, since it's when you actually listened.
- **Who sees it:** only the user whose progress it is, like the ABS ring. Not in the feed, not to
  friends, not in another user's view of the book. Reading progress in the
  feed is a possible Phase 17 idea, not this one.
- **Types:** books only (including audiobooks and ebooks without ABS).
  Movies and music have sessions too, but "page 3 of a season" isn't asked
  for; the code keys on `media_type = 'book'`.

## A3. Data model (migration 046)

```sql
ALTER TABLE reading_sessions ADD COLUMN progress REAL
    CHECK (progress IS NULL OR (progress >= 0 AND progress <= 1));
ALTER TABLE reading_sessions ADD COLUMN progress_page INTEGER
    CHECK (progress_page IS NULL OR progress_page >= 0);
ALTER TABLE reading_sessions ADD COLUMN progress_at TIMESTAMP;
ALTER TABLE abs_links ADD COLUMN progress_at TIMESTAMP;
```

Same pattern as 045 (`abs_links.progress`). Folded into `create_database.sql`
with its ledger row. The two `progress_at` columns decide which value is newer,
and give the "updated 3 days ago" note under the field. An existing
`abs_links` row has no `progress_at` until its next sync; until then, a
manual value wins if there is one.

A page beyond the page count is accepted and clamped to 100 % (page counts
are often a few pages off the edition in hand). A finished session keeps
whatever progress it had; nothing displays it.

## A4. Code

- `utils/reading_progress.py` (new): `set_progress(conn, user_id, book_id,
  page=None, percent=None)` (finds or opens the session, validates, clamps,
  stamps `progress_at`; the caller commits), `rings(conn, user_id)`
  (`{book_id: (0..1, progress_at)}` from open sessions with progress, merged
  with `abs_import.rings` by the newer `progress_at`).
- `app.py`: `abs_ring` becomes `progress_ring_for(book_id)` reading the
  merged map (one `g` cache per request, as now). The template global's old
  name stays as an alias until the templates are moved over.
- `read.py`: `POST /read/progress/<book_id>` (login, `can_view_book`, CSRF,
  back to `#item-history`), and the field in `manage_session`.
- `book_detail.html`: the field on the open session; the ABS note when ABS
  tracks it; "Finished? Mark as read" at the end.
- Exports: the reading sessions CSV gets `progress` and `progress_page`.
- `docs/ARCHITECTURE.md`: the module, the column, the ring's two sources.

## A5. Tests (`tests/test_reading_progress.py`)

- Page with a page count stores page and percent; without one, percent only;
  a page past the end clamps to 1; negative or junk refused.
- No open session: one is opened today and the status becomes Currently
  Reading; a finished session is never written to.
- A re-read's new session starts with no progress.
- Ring: manual alone shows; with both, the newer `progress_at` shows and the
  other is the small line; ABS finished (progress NULL), manual shows; an
  ABS row with no `progress_at` loses to a manual value.
- Someone else's progress never reaches your ring or page (bob's progress on
  a household book doesn't show for alice).
- A book you can't see is a 404; movies and music refuse the route.

---

# Part B: Merge two records into one (Admin → Maintenance)

## B1. What it is for

Two records for one work, where one of them holds the history:

1. **From before ownership** (2025-10, `added_by IS NULL`): Infinite Jest #10,
   Dune #9, Cat's Cradle #4, In Cold Blood #14, The Perks of Being a
   Wallflower #6 hold Phil's reviews, statuses and sessions, while his later
   copy (another edition, so `book_matching` didn't pair them) is the one on
   his shelf.
2. **An ABS listen that became its own Audiobook record** because the match
   missed (Blood in the Machine; the dash-subtitle fix of 2026-11-19 stops
   new ones), where it should have attached to the paper copy.

The tool moves everything that hangs on one record (the **folded** one) onto
the other (the **kept** one), then deletes the folded record.

## B2. Proposed decisions

- **Who may merge** (from Phil's "admin or a user's personal
  catalogue"): the same rule as a hard delete today, so there's one rule to
  learn.
  - **An admin**, any two records, from Admin → Maintenance.
  - **A user**, from the item page's Book tools ("Merge with another
    record…"), when the folded record is theirs (`added_by`) or unowned, the
    kept one is theirs or unowned, and **no other user has data on the
    folded record** (`models.other_users_with_book_data`, the check delete
    already uses). Otherwise the page says "Someone else has data on this
    record; ask an admin", which in practice covers the household cases.
  - Phil's case 1 (an unowned record holding his own reviews, beside his
    owned copy) passes the user rule, so he wouldn't need the admin page for
    it.
- **Same media type only.** A book and a movie never merge.
- **The kept record's details win.** Its blank fields are filled from the
  folded one (page count, description, narrator, subtitle, publisher, year,
  ISBN), each shown in the preview with a checkbox, ticked by default.
  Ownership (`added_by`, `owned`, `removed_at`), format, cover and value stay
  the kept record's: the kept one is normally the copy on the shelf.
- **An audiobook folded into a paper copy** becomes the paper copy's
  listening history, as an ABS "attach" does today: the sessions and review
  move, the `abs_links` row points at the paper copy, the Audiobook format is
  dropped with the folded record. The preview says so in words.
- **Clashes: you always pick** (Phil, 2026-11-20). Where both records have a
  row that can only exist once per user, the preview shows both side by side
  and the merge button stays off until every clash has a choice. Nothing is
  pre-selected; the table only says what's compared:

  | Table | Clash | Choice |
  |---|---|---|
  | `read_data` (rating, review) | same user rated or reviewed both | keep one review and one rating (they can come from different records) |
  | `collections` (status) | same user has a status on both | keep one |
  | `wishlist` | same user wishlisted both | keep one entry's notes, or join them |
  | `item_photos` (front, back, etc., one per kind) | both have one of a kind | keep one as that kind; the other joins the gallery |
  | `item_faces` | both set a face | keep one |

  When an admin merges, the admin picks for every user, and the preview
  names whose rows each clash is.

  Everything else has no clash and simply moves: `reading_sessions` (all of
  them; two sessions of the same read show side by side and can be deleted
  by hand afterwards), `book_tags` and `collection_books` (union, duplicates
  dropped), `loans`, `goodreads_rows`, `abs_links`, `notifications`,
  `activity_likes` and `dismissed_activities` (duplicates dropped).
  `cover_jobs` rows for the folded record are dropped. `bulk_edit_items` for
  the folded record are dropped too: older bulk edits can't undo that one
  item any more, and the preview says how many.
- **Photo files stay where they are.** `item_photos.path` is stored per row
  (`uploads/photos/<old id>/...`), so moving the rows is enough. The delete
  of the folded record must **not** call `delete_photo_folder(<old id>)`, or
  the moved photos are lost. A test pins this.
- **Safety:** a site backup first (`backups.create('merge', ...)`, a new
  entry in `backups.KINDS` so the Backups list labels it "Before a merge"),
  then everything in one transaction, with `foreign_key_check` before
  commit.
- **Undo through the bulk journal**, as the roadmap asks: a `bulk_edits` row
  with `action = 'merge'` and the whole record of the merge in `params`
  (JSON): the folded book's row, each moved row's table, key and old
  `book_id`, each dropped duplicate's full row, each filled field's old
  value. Undo re-inserts the folded book **under its old id** (`books.id` is
  `AUTOINCREMENT`, so ids are never reused), points the moved rows back,
  restores the dropped rows and blanks the filled fields. It refuses if the
  kept record has been deleted since, and says so. No migration needed.
  `bulk_edit_items` can't hold it, because its rows cascade away with the
  folded book.
- **Duplicates are never prohibited** (Phil owns several copies of some
  books, on purpose). The tool only acts when someone asks it to, and the
  suggestions below never include two owned copies of the same work.
- **Suggested pairs** on the Merge records start page, each with a
  Preview button. Built simpler than drafted (2026-11-20): not on item
  pages, and not dismissible, since owned copies are never suggested and
  the two cases below are nearly always real; a dismiss list can come
  later if a false pair turns up. On dev it finds Cat's Cradle #4, Dune #9,
  Infinite Jest #10 and the Blood in the Machine listen; In Cold Blood #14
  and Perks #6 have no owned copy on dev to pair with.
  1. Same normalised title and author (`book_matching`'s normalisation, with
     the dash-subtitle split), same media type, where at least one side is
     unowned with data on it, or both are in one household.
  2. `abs_links` with outcome `created` whose title now matches a copy on
     the same user's shelf (the listens imported before the dash fix).

  Plus a manual form: two item ids or links, for anything the suggestions
  miss.

## B3. The flow

1. Admin → Maintenance → Merge records (the suggestions and the manual
   form), or an item page's Book tools → Merge with another record… (a
   picker of your own and unowned records of the same type).
2. **Preview** (`GET /merge?keep=<id>&fold=<id>`, one page for both ways in): both records side by
   side; a Swap button; the fields to fill; per user, what moves; each clash
   with its choice; the counts that drop. Nothing is written.
3. **Merge** (`POST`): backup, apply in one transaction, journal, redirect to
   the kept record's page with "Merged *Dune* (#9) into this record. Undo".
4. **Undo** from that flash and from Admin → Maintenance's recent merges.

## B4. Code

- `utils/merge.py` (new): `plan(conn, keep_id, fold_id)` (pure read: moves,
  clashes, fills, drops), `apply(conn, plan, choices, admin_id)`,
  `undo(conn, edit_id)`, `suggestions(conn)`. One table per mover entry, so
  a new book-child table is one line; a test fails if a table with a
  `book_id` foreign key isn't in the list (read from
  `pragma_foreign_key_list`), so a future table can't be forgotten.
- `blueprints/merge.py` (new, `/merge`): preview, merge, undo, `@login_required`,
  rate limited; `merge.may_merge(conn, user, keep, fold)` holds the rule in
  B2 and is checked on every route. Admin → Maintenance links in.
- `templates/admin_merge.html`: the preview; `bulk.js`-style choices are
  plain radio buttons, no script needed.
- `utils/bulk.py`: `merge` registered for undo.
- `docs/ARCHITECTURE.md`: the module and the tool.

## B5. Tests (`tests/test_merge.py`)

- Every table with a `book_id` foreign key is handled (the pragma test).
- An unowned record with alice's review, status and sessions folds into
  her owned copy: all of it moves, the folded record is gone, nothing
  orphaned (`foreign_key_check` clean).
- Clashes: two reviews by one user stop at the preview; the chosen one
  survives, the other is in the journal.
- Photos: the folded record's photo files still exist after the merge.
- Undo restores the folded record under its old id with every row, and the
  kept record's filled fields go back to blank.
- A user may merge their own record with an unowned one; is refused when
  bob has data on the folded record; an admin may do both. Different media
  types are refused; merging a record into itself is refused.
- Two owned copies by the same user are never suggested.
- Suggestions find the five pre-ownership pairs' shape and an ABS `created`
  duplicate.

---

## Steps (one commit each)

1. Migration 046, `utils/reading_progress.py`, the route, tests.
2. The item page field, the ring from both sources (newer wins;
   `abs_links.progress_at` stamped by Sync and the live line), exports, docs.
3. `utils/merge.py`: plan and apply, the pragma test.
4. The preview, the admin entry and the item page's Book tools entry.
5. Journal and undo.
6. Suggestions, including the ABS duplicates; run on a copy of dev's DB,
   then Phil merges on prod himself.
7. Tick ROADMAP 16.0f, including the dash-subtitle leftover.

## Not in this phase

- A progress control on the Currently Reading row; progress in the feed or
  for friends; progress for movies (episodes) or music.
- Merging more than two records at once (do it twice).

## Answered (Phil, 2026-11-20)

1. Progress per session: type a page, the app does the percent.
2. The newer of ABS and manual wins.
3. Visible only to the user whose progress it is.
4. Merge by admins or by users on their own catalogue (rule proposed in B2).
5. Clashes: always pick.
6. Duplicates are never prohibited; owned copies are never suggested.

7. The user rule for merging in B2: approved with the spec ("go ahead").
