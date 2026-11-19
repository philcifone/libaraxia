# Audiobookshelf connection (ROADMAP 16.0e)

From Phil, 2026-11-18: moved up from 17.2 (parked before that) so it is built
before the portfolio. Approved by Phil the same day ("go"). Branch
`phase-16d-lending-abs`, after lending (docs/LENDING-SPEC.md).

## 1. What it is for

Audiobooks are books with format Audiobook, usually not owned (ROADMAP
8B.2/8B.3): they count in reading stats and take reviews, never sit on the
shelf. Phil's Audiobookshelf (ABS) server tracks listening better than this
project should, so Libaraxia reads from it instead of making you log listens
twice:

- **Import**: finished and in-progress audiobooks come in as unowned
  Audiobook books with a status and a listening session, after a review.
- **Live link**: on an imported item, your current ABS progress.

Read-only: nothing is ever written to ABS.

## 2. Decisions (Phil, 2026-11-18)

- One ABS server for the site, set in `.env`. Each user pastes only their own
  ABS API key in Settings.
- The import is review, then apply (the Goodreads import's shape), undoable.
- Both parts (import and live link).
- Audiobooks gain a **narrator** and a **length** (section 7).
- **Ebooks** come in too, as unowned books with a new format `Ebook`.
- A notification is not part of this phase (that was lending's question).

What comes in: by default only what you've started (finished or in
progress), not your whole ABS library. Sync has an "Also books I haven't
started" option, off by default, for the rest (section 8).

**Ownership (Phil's rule, 2026-11-18): nothing from ABS is ever owned unless
the catalogue already says so.** The import never writes `books.owned`:
- every book it creates is `owned = 0`, whatever its box or choice (the
  not-started option included);
- attaching to an existing row leaves its `owned` as it is: your owned paper
  copy stays owned, an unowned Audiobook row stays unowned;
- undo never touches `owned` either.
The only way an audiobook or ebook becomes owned is by hand, as today: "I Own
It Now" on the item page, or bulk edit's Owned action (ROADMAP 8B.3: "an
owned one, files you bought, counts as owned"). The review page shows no
ownership choice. A test asserts that no import path writes `owned`.

## 3. What Phil's server says (probed 2026-11-18, read-only)

ABS 2.32.1, plain HTTP on `192.168.1.171:13378` (TLS there fails, so
`.env` says `http://`; fixed by Phil the same day). With Phil's key:

- `GET /api/me` (344 KB): the user and every `mediaProgress` row: 663 rows,
  of which **639 are podcast episodes** (`mediaItemType` `episode`, an
  `episodeId`). **24 are books**: 14 finished, 9 in progress, 1 opened at 0 %.
  Progress fields: `libraryItemId`, `progress` (0 to 1), `currentTime`,
  `duration` (seconds), `isFinished`, `startedAt`, `finishedAt`, `lastUpdate`
  (milliseconds since the epoch), `ebookProgress`. Every finished row has
  `finishedAt`.
- `/api/me` also returns the user's legacy `token`. The client drops the
  response as soon as it has read the progress rows; it is never stored,
  logged or passed on.
- `POST /api/items/batch/get` with the 24 book ids: 1 MB (audio files,
  chapters and tracks come along). Metadata: `title`, `subtitle`, `authors`
  / `authorName`, `narrators`, `series`, `publisher`, `publishedYear`,
  `genres`, `isbn`, `asin`, `language`, `description`; `media.duration`;
  `media.audioFiles`, `media.ebookFile`.
- **Identifiers are rare:** 0 of the 24 have an ISBN, 3 have an ASIN. Matching
  is title and author in practice, which is why the review step matters.
- Libraries: `audiobooks` (436 items: 431 with audio, 14 with an ebook too;
  23 started), `Books` (92 items, all ebooks, 3 with audio; 1 started) and
  `podcasts` (ignored).
- `GET /api/libraries/<id>/items?minified=1&limit=0`: every item of a library
  in one answer (740 KB and 140 KB here), with `numAudioFiles`, `duration`,
  `ebookFormat` and the metadata, `narratorName` included. This is cheaper
  than the batch call, so Sync reads the libraries instead.
- `GET /api/items/<id>/cover` (auth): WebP, about 9 KB.
  `GET /api/me/progress/<id>`: one progress row.

## 4. Configuration

```
# Optional: Audiobookshelf (docs/AUDIOBOOKSHELF-SPEC.md)
AUDIOBOOKSHELF_URL=http://192.168.1.171:13378      # what the server calls
AUDIOBOOKSHELF_PUBLIC_URL=https://books.example     # links in the browser (optional)
```

- **`AUDIOBOOKSHELF_URL` should be the LAN address.** Dev and prod both sit
  on that LAN: no round trip through Cloudflare, no dependency on the tunnel,
  and a Cloudflare Access login in front of the tunnel would block API calls.
  The tunnel URL also works if nothing gates it.
- **`AUDIOBOOKSHELF_PUBLIC_URL`** is only for "Open in Audiobookshelf" links a
  browser follows (a phone away from home); default the server URL.
- No URL set: the feature is hidden (no Settings card, no routes beyond 404).
- The configured origin is the allow-list. The client calls nothing else, so
  a private address is fine there and `book_utils._get_public` (which refuses
  private addresses) isn't used. A user can't type a URL, so there is no SSRF
  surface.
- `AUDIOBOOKSHELF_API_KEY` (in dev's `.env` today) is not read by the app. On
  dev it is used once, by hand, to connect the `claude` test user.
- Plain HTTP on the LAN sends the key unencrypted on the home network, as
  every ABS app on that network already does. Acceptable for a LAN address;
  the app logs a warning at startup for `http://` to a public host.

## 5. The client and the key

`utils/audiobookshelf.py`:

- `requests` session to the configured origin only; `allow_redirects=False`
  (a redirect is an error); the key only in `Authorization: Bearer`, never a
  URL; timeouts 10 s (sync), 1.5 s (the item page's progress); a size cap per
  response (`/api/me` 5 MB, a library listing 20 MB, a cover 10 MB, read
  streamed). Errors are logged without the key or response body, and the
  browser gets a generic message ("Audiobookshelf didn't answer").
- `me(token)` returns `{abs_user_id, username, books: [...]}` keeping only
  book progress rows; `library_items(token)` lists the book libraries
  (`/api/libraries`, `mediaType` `book`) and returns every item's trimmed
  metadata (minified listing); `progress(token, item_id)`; `cover(token,
  item_id)` bytes.
- **Storage:** table `abs_accounts`, not a `users` column (`SELECT * FROM
  users` is everywhere and feeds `current_user`). The key is encrypted with
  Fernet (`cryptography`, a new dependency) under a key derived from
  `SECRET_KEY` (HKDF, its own `info` label). A copied DB or site backup alone
  can't reach anyone's ABS; rotating `SECRET_KEY` makes stored keys
  unreadable, which shows as "Reconnect" in Settings. One well-known
  dependency for that is a risk worth taking.
- Never in exports, personal backups, templates, JSON or logs. The Settings
  form's key field is write-only.
- Phil's key belongs to his ABS user, which is `root`. ABS keys have no
  scopes, so the app only ever reads (GET, and the read-only batch POST).

## 6. Data model (migration 043)

```sql
-- An audiobook's narrator(s), as ABS writes them ("Ray Porter, Jane Doe").
ALTER TABLE books ADD COLUMN narrator TEXT;

CREATE TABLE abs_accounts (
    user_id      INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    token_enc    TEXT NOT NULL,
    abs_user_id  TEXT NOT NULL,
    abs_username TEXT NOT NULL,
    connected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_sync_at TIMESTAMP
);
-- What the last Sync fetched, waiting for review (one set per user, 24 h).
CREATE TABLE abs_staging (
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    abs_item_id TEXT NOT NULL,
    data        TEXT NOT NULL,          -- JSON: trimmed metadata + progress
    choice      TEXT,                   -- NULL = the box's default
    staged_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, abs_item_id)
);
-- What each ABS item became: re-runs, the item page note, the live link.
CREATE TABLE abs_links (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    abs_item_id TEXT NOT NULL,
    book_id     INTEGER REFERENCES books(id) ON DELETE SET NULL,
    outcome     TEXT NOT NULL CHECK (outcome IN ('created', 'attached', 'skipped')),
    asin        TEXT,
    session_id  INTEGER REFERENCES reading_sessions(session_id) ON DELETE SET NULL,
    finished_at TIMESTAMP,              -- ABS finishedAt last recorded
    linked_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, abs_item_id)
);
```

`abs_links.book_id` is SET NULL like `goodreads_rows.book_id`: a deleted book
leaves the memory, so the next Sync shows it as "imported before, since
deleted" (default skip) rather than offering it as new.

Length needs no column: `books.runtime_minutes` is unused for books today
(movies and music use it). The `Ebook` format needs no migration either
(`books.format` has no CHECK).

## 7. Narrator, length and the Ebook format, everywhere

These hold for any audiobook or ebook, typed in by hand or imported.

- **Formats:** `media.FORMATS[BOOK]` becomes Book, Audiobook, Ebook;
  `book_format()` stores `'Ebook'` as it does `'Audiobook'` (a plain book stays
  NULL). Picking Ebook on Add ticks "I don't own this", as Audiobook does. An
  ebook gets an item-page format icon (Lucide `tablet-smartphone`) and the
  Format filter lists it once there is one.
- **No box:** everything that leaves audiobooks out because they have no
  physical copy leaves ebooks out too (the 3D item, placeholder faces, a
  book's page-edge photo labels). One helper, `media.is_digital(row)`, so
  these checks don't each list both formats.
- **Pages:** an ebook keeps its page count and counts in pages read (it was
  read); an audiobook's stays out, as today.
- **Narrator:** on Add and Edit when the format is Audiobook (a `.when-audio`
  field shown by CSS `form:has(...)`, as Movies & TV's Season is, no script);
  on the item page under the author ("Narrated by Ray Porter"); in the grid
  search's columns; in the library CSV and data exports (a column at the end).
- **Length:** an "Hours and minutes" field for an audiobook on Add and Edit,
  stored in `runtime_minutes`; shown as "Length 12 h 30 m"
  (`media.format_runtime`) on the item page; exported.
- **Stats (Phil, 2026-11-18): an Audiobooks block in the Books tab** of the
  profile's Stats, under its own "Audiobooks" label, after the book tiles and
  before Longest. Inside Books rather than a tab of its own, because an
  audiobook is still a book you've read: it already counts in "Books read",
  the reading goal and reviews, and a separate tab would split those. Tiles
  (`stats.audiobook_stats`, the same `stat-tile` macro, so every style draws
  them as it draws the rest):
  - Audiobooks listened (finished, status Read), and this year;
  - Hours listened (sum of `runtime_minutes` over finished audiobooks, one
    listen each, as movie hours count each film once), and this year (by the
    finished session's date);
  - Listening now (Currently Reading audiobooks);
  - Longest listen (title and length).
  Shown only when you have a finished or in-progress audiobook. An audiobook
  with no length counts in the listened number but not the hours; if any are
  missing, a line under the tiles says "Hours from 12 of 14 (2 have no
  length)". The all-types overview's line ("1,234 pages read · 56 hours
  watched") gains "· 40 hours listened". Pages read stay without audiobooks,
  as today; ebooks are plain books in stats.
- Bulk edit's Format action offers Ebook through `FORMATS`.

## 8. The import

**Settings → Library: an Audiobookshelf card.** Not connected: a key field
(`autocomplete=off`) and Connect, which checks the key with `/api/me` and
says "Connected as phil". Connected: Sync, Disconnect (deletes the
`abs_accounts` row and staging; links stay), and the last sync time.

**Sync** (`POST /abs/sync`, 10 per hour): `/api/me` for the progress rows
(books only), the book libraries' item listings for metadata, joined on the
item id; store in `abs_staging`, go to the review. Four requests and about
1.2 MB for Phil today; fine inside a request.

- **What's included:** items you've started (progress above 0, or finished).
  With **"Also books I haven't started"** ticked, every other item of your ABS
  book libraries comes too, in its own box, default skip, choice "add as Want
  to Read" (504 items for Phil today, so off by default: it would put most of
  the server into the catalogue).
- **Audiobook or ebook:** an item with audio files is an Audiobook (its
  `progress` is the listening); one with only an ebook is an Ebook (its
  `ebookProgress`). An item with both is an Audiobook.

**Review** (`GET /abs/review`), boxes like the Goodreads review:

| Box | Which rows | Default | Other choices |
|---|---|---|---|
| New finished | finished, no match, no link | add unowned (Audiobook or Ebook), Read, one session | skip |
| New in progress | not finished, no match, no link | add unowned, Currently Reading, session with a start date | skip |
| Matches your copy | `BookIndex` match on your shelf or the household's | attach: status and session on that copy | add as a separate audiobook or ebook, skip |
| Finished since last sync | linked, ABS now finished (or finished again later than `finished_at`) | complete the open session (or add a new one for a re-listen) and set Read | skip |
| Not started (option) | no progress, no match, no link | skip | add unowned, Want to Read, no session |
| Imported before | linked, nothing new | hidden, counted | — |
| Skipped or deleted before | link with `skipped`, or `book_id` NULL | skip | add |

- **Matching:** `book_matching.BookIndex(conn, user_id).match(isbns=, title=,
  author=)`: your own books and your household's, never anyone else's. ISBN
  when ABS has one, else title (with subtitle forms) and author. **ASIN:**
  `books` has no ASIN column, so an ASIN can't match a book; re-runs are kept
  from duplicating by the ABS item id in `abs_links` instead, and the ASIN is
  kept there. Wishlist entries don't match: the listen becomes its own
  unowned Audiobook and the wishlist entry stays.
- **Attach to a paper copy** is the default because of the Goodreads import's
  rule: one book, one set of reviews and sessions. Its format stays Book, and
  narrator and length aren't written onto it. Attaching to an existing
  Audiobook row fills its narrator and length only where they are empty.
- **New books:** title, subtitle, author (`authorName`), narrator
  (`narratorName`, audiobooks only), length (`duration` seconds to whole
  minutes in `runtime_minutes`, audiobooks only), publisher, year, genres
  (first), ISBN if any, `format` `'Audiobook'` or `'Ebook'`, `owned = 0`,
  `added_by` = you, `created_at` = ABS `startedAt` so the feed isn't flooded;
  status with `quiet = 1`. Sessions use dates only (ABS milliseconds in the
  server's local time): `date_started` from `startedAt`, `date_completed` from
  `finishedAt`.
- **Covers** for new books come from ABS (`cover()`, through Pillow and
  `process_image` like any upload), inside Apply with a 15 s budget; any left
  are offered again by the next Sync ("3 covers to fetch").

**Apply** (`POST /abs/apply`, 3 per hour) follows `goodreads_plan.apply`:
a personal backup first (`personal_backups` kind `audiobookshelf`; refuse
without it); a fingerprint of the staged rows and your data (a stale review is
a 409 with the fresh plan); one transaction, a SAVEPOINT per row; each row
journalled in `bulk_edits` with action `audiobookshelf` and recorded in
`abs_links`. **Undo** is the bulk route: `bulk._action`'s special case for
`goodreads` becomes a small table of importer actions, and the undo reuses
the Goodreads rules (a created book is deleted only if nobody else has data
on it and you've added nothing since; journalled statuses and sessions are
put back).

## 9. The live link

- On an item you have an `abs_links` row for (yours only; nobody else sees
  anything), `#your-info` shows "Audiobookshelf: 43 %, 5 h 12 m left, last
  listened 2 days ago · Open in Audiobookshelf". Finished in ABS but not
  synced: "Finished in Audiobookshelf on 5 Jan 2026 · Sync".
- Filled after load by `book_detail.js` from `GET /abs/progress/<book_id>`
  (JSON; 404 unless the link is yours; 120 per hour; 60 s in-memory cache per
  user and item), so the page never waits on the LAN. Silent when ABS is
  down.
- The item page also gets a provenance note beside the Goodreads one:
  "Imported from Audiobookshelf on 18 Nov 2026".
- "Open in Audiobookshelf" goes to `AUDIOBOOKSHELF_PUBLIC_URL` + `/item/<id>`
  (the path is checked against Phil's server in step 6).

## 10. Code

- `utils/audiobookshelf.py`: config, client, encryption (`seal`, `open_`),
  `account(conn, user_id)`, `connect`, `disconnect`.
- `utils/abs_import.py` (no Flask): `stage`, `plan`, `choose`, `apply`,
  `ACTION` for undo, `provenance(conn, user_id, book_id)`.
- `blueprints/audiobookshelf.py` (`/abs`, registered in `app.py`):
  `POST /connect`, `/disconnect`, `/sync`, `/choose`, `/apply`, `/discard`;
  `GET /review`, `/progress/<book_id>`. All `@login_required`, CSRF on POSTs,
  per-route limits; 404 for everything when no URL is configured.
- `templates/abs_review.html`, the Settings card in `_settings_library.html`,
  `static/abs_review.js` (choices, the Goodreads review's helpers where they
  fit).
- `.env.example`, `requirements.txt` (`cryptography`), `docs/ARCHITECTURE.md`
  (blueprint, utilities, tables, env vars), the README at 16.1.

## 11. Steps (one commit each)

1. Migration 043 (`books.narrator` and the ABS tables), the Ebook format,
   narrator and length on the forms, item page, search and exports
   (section 7); useful on its own, before any ABS code.
1b. The Audiobooks block in Stats and "hours listened" in the overview.
2. `cryptography`, `utils/audiobookshelf.py` (client against a fake in tests;
   encryption), `.env.example`.
3. Settings card: connect, disconnect, the warning for a dead key.
4. Sync, staging, plan and the review page (with the not-started option).
5. Apply, undo, the personal backup, covers.
6. The live progress line and the provenance note; the item link path.
7. Docs; a real sync on dev as `claude` with Phil's key; screenshots in every
   style.

## 12. Tests

- Client (the network is blocked in tests; a fake `requests` adapter): a
  redirect is an error; the key is only ever in the header; a timeout or an
  oversized body is a clean failure; `me()` drops episodes and the legacy
  `token`.
- Encryption round trip; a different `SECRET_KEY` reads as "reconnect".
- Plan boxes for each row kind; matching to your copy and to a household
  copy, never to a friend's or a stranger's book; wishlist entries don't
  match.
- Ebook format: stored, ticks "I don't own this", left out of the 3D item
  and faces, pages still count; narrator and length saved, shown, searched
  and exported; the narrator field only for Audiobook.
- Stats: hours listened sum finished audiobooks' lengths once each; this
  year by session date; the block is hidden with no audiobooks; the "from 12
  of 14" line only when some lack a length; pages read still exclude
  audiobooks.
- An item with audio and an ebook is an Audiobook; ebook-only is an Ebook;
  not-started items appear only with the option, default skip.
- Ownership: every created book is `owned = 0`; attaching to an owned paper
  copy leaves it owned and to an unowned row leaves it unowned; undo leaves
  `owned` alone.
- Apply creates unowned Audiobooks and Ebooks with the right status, session
  dates, narrator and length;
  a second Sync + Apply creates nothing; in progress then finished completes
  the same session; a re-listen adds a session.
- Undo deletes created books only when nobody else has data; restores an
  attached copy's status and sessions.
- Settings and every JSON answer never contain the key; `/abs/progress` is a
  404 for someone else's link; everything is a 404 with no URL configured.

## 13. Open questions for Phil

None open. Answered 2026-11-18: `.env` now `http://`; ebooks come in as
unowned `Ebook`; narrator (new column) and length (`runtime_minutes`) added;
only started books by default, with an option for the rest; podcasts stay
out; a book at 0 % stays out until it has progress; hours listened go in an
Audiobooks block of the Books stats.
