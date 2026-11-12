# Goodreads Import Brief (ROADMAP 14b)

Status: draft for Phil, 2026-11-11. Brief only; the spec
(`GOODREADS-IMPORT-SPEC.md`, shaped like `BULK-EDIT-SPEC.md`) follows once this
is agreed. Supersedes nothing yet: `BULK-EDIT-SPEC.md` section 16 stays the
outline until the spec replaces it.

## Problem

Today the import is one POST that parses, matches and writes in a single pass
(`utils/goodreads.py`). You see what it did only afterwards, and can't take it
back. Specifically:

- **Re-importing skips what changed.** A book that already has any status here
  is `already` and the whole row is dropped: the read you finished on
  Goodreads, the new rating, the review, the re-read's date, new shelves.
- **It decides ownership for you.** Every `read` row creates an owned book on
  your shelf (only audiobooks come in not owned), and a wishlisted book you've
  since read is moved off the wishlist into the library as owned. Both break
  "the shelf never shows not-owned as owned".
- **Every Goodreads shelf becomes a collection**, `2019-reading-challenge` and
  `kindle` included, with no way to say no.
- **No undo.** A bad import is hours of hand cleanup.

## Who and when

1. **Phil, re-importing** a fresh export into a library that already holds
   most of it. Wants: only the differences, the routine ones applied without
   fuss, the real conflicts shown, and nothing he already settled overwritten.
2. **A new user, first import.** Wants: one click to get everything in, with a
   chance to fix destinations (owned or not, wishlist or skip) in bulk first.

## Success

- I see every row's outcome before anything is written, and can change it
  per row or for a selection, using the same selection bar and grouped review
  as bulk edit.
- A re-import shows the few rows that differ; the 380 unchanged ones are a
  count, not a list.
- Where Goodreads and Libaraxia disagree, I see both and mine wins unless I
  say otherwise.
- A read I logged on Goodreads lands as a dated session here on re-import, does not remove or duplicate existing sessions
- I can undo a whole import from Profile -> Recent bulk edits for 30 days,
  guarded per item like any bulk edit.
- "Import everything with the defaults" is still one click.

## Constraints

From CLAUDE.md: raw `sqlite3`, no new dependencies; migration **032** (030 is
reserved for 15.1, 031 is taken); books only (`media_type = 'book'`); matching
only through `BookIndex` (your books and your household's, never all of
`books`); created books removed on undo only via the
`other_users_with_book_data` rule; `owned` / `removed_at` semantics as they
are; no inline JS, POST + CSRF, ownership checked in SQL, no `str(e)` to the
client; page extends `base.html`, semantic classes only, all four styles;
tests with every route. Prod deploys and migrates itself on merge to `main`.

From 14a: plan / apply / undo with a fingerprint and `StalePlan`; one
SAVEPOINT per item with its journal row inside it; never write what wasn't
shown; never overwrite a later change (apply and undo re-check); the browser
sends ids and decisions, never columns; statuses written `quiet = 1`;
keyboard-complete, usable at 375 px. From the importer: exactly one outcome
per CSV row (`tests/test_goodreads.py`). Pipeline: worktree on a branch, one
step at a time, Phil commits.

## In scope

- Plan / apply split with a staging table (per user, replaced by a new upload,
  swept after 24 h, capped at ~5000 rows).
- Full-page review: per row a match (New / Yours / Household's / On your
  wishlist / Unchanged) and a destination (Library, Library not owned,
  Wishlist, Skip); filters; bulk-set destination on a selection.
- Per-field differences on matched books, split into **additions** (no value
  here yet: default apply) and **conflicts** (both have a value: default keep
  yours).
- Wishlist-then-read as its own decision; Goodreads shelf -> collection
  mapping panel (existing, new, ignore).
- Undo through the existing `bulk_edits` journal; result keeps starting the
  `cover_jobs` fetch; the 3/hour limit counts applies, not plans.

## Out of scope

- **Other sources** (StoryGraph, LibraryThing, Letterboxd, Discogs): one
  format first. Staging and review are source-agnostic, so a parser can plug
  in later.
- **Choosing a different match by hand:** that's a second matcher beside
  `BookIndex`. Revisit if the re-import shows wrong matches.
- **Metadata or cover lookup during import:** slow and rate-limited, and 8F's
  problem; `cover_jobs` runs after, as now.
- **Private notes on library books:** there's no column for them; a separate
  feature.
- **Sync or scheduled import:** Goodreads has had no public API since 2020.
- **Per-row undo from history:** undo is per import, as for bulk edits.

## Open questions

1. **Remember decisions between imports?** The export has a stable
   `Book Id`. Recommend yes: a small per-user table (Goodreads id -> book id,
   plus "skipped" and shelf mappings), so a re-import matches exactly and
   doesn't re-offer the 50 to-read rows or `kindle` shelf you said no to.
   Changes the schema; worth the small risk.
2. **One click vs Ask.** The outline wants wishlist-then-read to default to
   Ask *and* one-click to equal today "row for row"; those contradict.
   Recommend: one-click skips Ask rows and says how many; the equivalence test
   is restated as "today's behaviour, minus these". Alternative: one-click
   uses "Mark read, keep wished for" (safe, claims no ownership).
3. **Default for a new `read` book:** owned (today) or not owned? Recommend
   owned by default, with "Library not owned" one selection away and the
   review saying how many are being added as owned. Goodreads' Owned Copies
   is too rarely set to trust.
4. **Re-reads:** add a session when Date Read isn't already one of your
   session dates on that book? Recommend yes, as an addition (default on).
   Read Count beyond that is ignored on re-import, since it can't be dated.
5. **Undo journal:** reuse `bulk_edits` with action `import` and one item per
   book (a composite snapshot of your rows on it), or a separate import
   journal? Recommend reuse: one history list, one guarded undo.

## Phil asked for / Claude proposed

**Phil (this request and ROADMAP 14b):** granular import; reuse bulk edit's
review and undo, not a fork; the two personas; brief before spec.

**From the 14a spec's section 16 outline** (first draft; the repo doesn't say
which of these were yours): staging table, review grid with destination per
row, conflicts per field defaulting to keep yours, wishlist-then-read
defaulting to Ask, shelf mapping, undoable, one-click defaults, covers via
`cover_jobs`.

**Claude, in this brief:** additions vs conflicts; Unchanged rows collapsed
to a count; remembering decisions by Goodreads `Book Id` (Q1); the one-click
contradiction (Q2); the ownership problem with `read` and wishlist-then-read
(Q3); dated re-read sessions (Q4); journal reuse (Q5); migration 032.

## Answers (Phil, 2026-11-11)

Goodreads is a reading-history snapshot; Libaraxia has been the record for
over a year. So: new read books default to **not owned** (Q3 reversed); **no
collections** from Goodreads shelves and no Want to Read status for owned
to-read books; Q1 yes, and every touched book is marked **permanently** so it
can be filtered ("From Goodreads") and bulk edited later; Q2 as recommended;
Q4 yes, sessions are only ever added; Q5 reuse. Spec:
[GOODREADS-IMPORT-SPEC.md](GOODREADS-IMPORT-SPEC.md).
