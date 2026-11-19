# Lend an item (ROADMAP 16.0d)

From Phil, 2026-11-18: moved up from 17.1 (originally 15.2) so it is built
before the portfolio. Approved by Phil the same day ("go"). Branch
`phase-16d-lending-abs`, shared with 16.0e (docs/AUDIOBOOKSHELF-SPEC.md),
lending first.

## 1. What it is for

Record who physically has a copy: "Bob has my *Dune* since March". Any type
(books, movies, music). It is a note about the household's copy, not a
transaction: nothing is enforced, nobody accepts a loan, there are no
reminders. Lending inside a household is still worth recording (who has it
in their bag), so it isn't limited to friends.

## 2. Decisions (Phil, 2026-11-18)

- **Who lends:** the owner or any member of the owner's household (the people
  whose shared shelf it is on), or an admin. The same people mark it returned.
  `lent_by` records who handed it over, which may not be the owner. (Changed
  from the ROADMAP draft, where `lent_by` was the owner.)
- **Who can borrow:** a user in the lender's circle (`models.circle_ids`:
  household and friends), picked from a list, or anyone else typed as a name.
  The server re-checks that a picked user is in the circle.
- **Who sees a loan:** the shelf's people (owner and household), admins, and
  the borrower. Friends browsing the owner's shelves see nothing about loans:
  no badge, no filter, no banner. The borrower's name never reaches anyone
  outside that group.
- **Notifications:** the borrower (when a user) gets one when the item is
  lent. The owner gets one when someone else (a household member, an admin)
  lends their item or marks it returned, on their Notifications page. Nobody
  is notified of their own action, and the borrower isn't told of a return.

## 3. Data model (migration 042)

```sql
CREATE TABLE loans (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id       INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    lent_by       INTEGER REFERENCES users(id) ON DELETE SET NULL,
    borrower_id   INTEGER REFERENCES users(id) ON DELETE SET NULL,
    borrower_name TEXT NOT NULL,       -- typed name, or the user's name when lent
    lent_at       DATE NOT NULL,
    due_at        DATE,
    returned_at   DATE,
    note          TEXT,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CHECK (length(trim(borrower_name)) > 0),
    CHECK (due_at IS NULL OR due_at >= lent_at),
    CHECK (returned_at IS NULL OR returned_at >= lent_at)
);
-- One open loan per item.
CREATE UNIQUE INDEX loans_one_open ON loans(book_id) WHERE returned_at IS NULL;
CREATE INDEX loans_borrower ON loans(borrower_id) WHERE borrower_id IS NOT NULL;
```

- `borrower_name` is always filled. For a user it is their username at the
  time, so the row still reads "Lent to bob" if bob's account is deleted
  (`borrower_id` goes NULL). Pages show the live username while the account
  exists.
- Folded into `create_database.sql` with its ledger line, as 041 was.
- Hard-deleting a book removes its loans (CASCADE); deleting a user keeps the
  loans they made or received, with the name.

## 4. Rules

- **Lend** only an item on the shelf: `on_shelf` (owned, not removed) and not
  a wishlist entry. Any media type. One open loan at a time (the unique index;
  the route answers "Already lent to bob" rather than a 500).
- **Mark returned** with a date (default today, not before `lent_at`).
- **Delete** a loan, for mistakes (`data-confirm`). No edit: delete and lend
  again. Deleting also deletes the unread notifications about it.
- **Loans don't follow shelf state.** Removing, unowning or transferring an
  item leaves its loan as it is; a removed item that is still lent says so on
  its page until someone marks it returned. Only Lend checks the shelf. This
  keeps every other write path (edit, bulk edit, transfer, Goodreads undo)
  untouched.
- **Seeing the item:** `models.can_view_book` gains one branch: you are or
  were the borrower of a loan of it. That covers a household member lending
  to their own friend who isn't in the owner's circle; the borrower can then
  mark it read or review it, as anyone who can view an item can.

## 5. Where it shows

All of these only for the shelf's people, admins and (where stated) the
borrower.

### Item page (`book_detail.html`, `books.render_item_page`)
- A banner in the style of the Removed / Unshelved one: "Lent to bob since
  3 Mar 2026, due 1 Apr 2026", or "... overdue since 1 Apr 2026". The
  borrower sees "Borrowed from alice since 3 Mar 2026".
- Buttons, next to the owner tools: **Lend** (opens a panel like Remove's:
  borrower select (circle, household first) or "Someone else" with a name
  field, lent date (today), optional due date, note) and, while lent, **Mark
  returned** (date field, today). These two widen `can_manage` to the shelf's
  people (`can_lend`); everything else in that block stays owner or admin.
- **Loan history**: a collapsed list (`<details>`, "Loans (3)") of every loan,
  newest first, with dates, note, who lent it and a Delete button. The
  borrower sees only their own loans of it.

### Grids
- A **Lent** badge on the cover, **top centre** (Phil, 2026-11-18; the
  design is open to change once it's on screen), in the Unshelved badge's
  pill style (borrower name in the `title` and the accessible label), on your
  own and your household's grids only. Top centre keeps it clear of the
  Removed / Unshelved badge (top left) and the bulk check mark, so both can
  show; step 3 ends with screenshots in every style for Phil to judge. Server: a per-page `lent_map(book_ids)`
  template global in `_book_grid.html` (one query, as `viewer_marks` is);
  infinite scroll: `card_json` gains `lent_to`, `script.js` `createBookCard`
  draws it.
- **Show: Lent out** (`show=lent`) in `book_utils.SHOW_CHOICES` and
  `shelf_filter` (`EXISTS` an open loan). Books, Movies & TV, Music and bulk
  edit's "select all in this view" all get it through the existing paths.
  Not offered on a friend's grids, and ignored there if typed into the URL.

### Collections page
- A **Lent out** row on each type's tab (`utils/shelves.py`, `_shelf_rows.html`)
  when anything of that type is lent: covers with the borrower as the `by`
  caption, linking to the grid with `?show=lent`. (`base.shelves` only
  redirects to a grid; the row page is Collections.)

### Profile
- **Borrowed**: a row on your own profile's Overview (after Wishlist) of what
  you have borrowed and not returned, captioned with the lender. Your own
  view only; friends visiting don't see it.

### Do I have this? (`utils/have.py`)
- `yours` / `household` labels get the loan: "On your shelf, lent to bob since
  Mar 2026". The verdict doesn't change.
- A new `borrowed` verdict after `household`: "Borrowed from alice since Mar
  2026", so a borrower scanning the book they're holding gets a straight answer.

### Notifications
- On lending to a user: `INSERT INTO notifications (user_id, type, message,
  related_book_id, from_user_id)` with type `loan` and "alice lent you Dune".
- To the owner, when the lender or returner isn't them: type `loan_owner`,
  "bob lent your Dune to dave" / "bob marked your Dune returned".
- One helper, `loans.notify(...)`, writes both; it skips a notification to
  the person who acted.
- `notifications.html` links the message to the item when `related_book_id`
  is set (it never does today; likes would gain the link too).

### Exports
- Library CSV: three columns at the end (older readers keep working): Lent
  to, Lent on, Due (the open loan, if any).
- Data ZIP: `loans.csv` with every loan of items you own or lent, and every
  loan to you.
- Personal library backups leave loans out: a loan belongs to the household's
  copy rather than one person, and a restore of one member's backup shouldn't
  rewrite it. Site backups hold them.

## 6. Code

- `utils/loans.py` (no Flask): `can_lend(conn, user, book)`, `can_see(conn,
  user, book)`, `borrower_choices(conn, user)`, `open_loan`, `history`,
  `lend`, `mark_returned`, `delete`, `lent_map(conn, book_ids, viewer)`,
  `borrowed_by(conn, user_id)`, `lent_out(conn, user, media_type)`.
- `blueprints/loans.py` (`/loans`, registered in `app.py`): `POST
  /loans/<book_id>/lend`, `POST /loans/<loan_id>/return`, `POST
  /loans/<loan_id>/delete`. CSRF, `@login_required`, `@limiter.limit("60 per
  hour")`; the permission is checked in the SQL; redirects back to the item
  page's `#loans` with a flash.
- `docs/ARCHITECTURE.md` (blueprint, utility, table), the access table in
  `CLAUDE.md` (a Lend / Mark returned row).

## 7. Steps (one commit each)

1. Migration 042 (+ `create_database.sql`), `utils/loans.py`, its tests.
2. Routes, item page (banner, Lend panel, Mark returned, history),
   `can_view_book`, the notification and its link.
3. Grid badge, `show=lent`, the Collections row, the profile's Borrowed row.
4. Do I have this?, exports.
5. Docs; screenshots in every style, both modes, phone and desktop.

## 8. Tests (`tests/test_loans.py`, conftest `people`)

- alice lends to carol (friend); bob (household) marks it returned; carol
  could view it, got exactly one notification, none on return; alice got one
  for bob's return and none for her own lending.
- A user outside the lender's circle is refused as borrower; a free-text name
  is fine; an empty one is refused.
- A second open loan is refused with a message; after return a new loan works.
- Lend refused on a removed, unowned or wishlist item, and for someone who
  isn't the owner, household or admin.
- bob lends alice's book to his own friend dave (not alice's): dave can view it.
- carol, browsing alice's grid as a friend: no badge, `show=lent` ignored,
  no banner on the item page.
- Do I have this? labels for owner, household and borrower; both exports.
- Delete removes the unread notifications about that loan. Migration 042: no FK violations,
  `create_database.sql` matches the migrated schema.

## 9. Not in this phase

Reminders or emails when overdue (17.4 would make it possible); a borrower
asking to borrow; bulk lend; loans on the feed or in stats.

## 10. Open questions for Phil

None open. Answered 2026-11-18: the badge is top centre (open to change on
screen); the owner is notified when someone else lends or returns their item.
