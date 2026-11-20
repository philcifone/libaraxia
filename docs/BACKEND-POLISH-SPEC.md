# Backend polish (ROADMAP 16.0g)

Approved 2026-11-20, from Phil's notes of the same day; his answers are
folded in below. Findings come from a
read of the code and a few measurements on dev.
Suggested branch `phase-16g-backend-polish`, one commit per step. It lands
before the code review (16.0h), so the review sees the finished backend.

Six parts, independent of one another: performance, routing, covers
without orphans, AVIF, upload sizes, and a choice of book metadata sources. Nothing here removes a feature.

---

## 1. Performance

### 1.1 Measure first

A dev-only request log, `PROFILE_REQUESTS=1` in `.env`: for each request,
the path, the time in ms and the number of SQL statements (counted with
`sqlite3.Connection.set_trace_callback` on `get_db()`'s connection). Off by
default and never on in prod. Walk every page (the `test_every_page_loads`
list) in two styles on dev's DB, and record the slow ones (over 150 ms, or
over 50 queries) in an appendix to this spec. Then fix those, usually an N+1
loop turned into one query or a missing index. Nothing in 1.2 to 1.5 waits
on this; they're wins whatever the measurements say.

### 1.2 Minify the CSS

`build:css` gets `--minify`. Measured on 2026-11-20:

| `output.css` | raw | gzipped |
|---|---|---|
| today | 326 KB | 77 KB |
| minified | 188 KB | 34 KB |

`output.css` is committed and generated, so nobody reads its diffs.
`test_every_rule_in_styles_css_ships_in_output_css` compares selectors as
text; minifying rewrites `a > b` as `a>b`, so the test's `_css_selectors`
learns to normalise whitespace around combinators first. If the minifier
renames anything else the test catches it, which is the point of the test.

### 1.3 Cache static files

Today Flask sends no `max-age`, so the browser revalidates every script,
stylesheet, font and cover on every page (each answered 304, but still a
round trip: one per cover on a shelf page, plus the scripts, CSS and
fonts).

- **Versioned URLs** for everything under `static/` except `uploads/`: an
  `@app.url_defaults` hook adds `v=<first 10 hex of the file's hash>` to every
  `url_for('static', ...)`, so no template changes. Hashes are computed once
  per process (prod restarts on every deploy, so a new file gets a new hash).
- **Long cache headers:** `get_send_file_max_age` returns one year
  (`Cache-Control: public, max-age=31536000, immutable`) when the request
  carries `v`, or the path is under `uploads/` or `fonts/`. Fonts are
  linked from the CSS by plain path (`url('/static/fonts/...')`), so they
  can't carry `v`; their file names already name the font, weight and style,
  and a changed font file gets a new name (a comment in `styles.css` says
  so). Covers, photos, faces and
  avatars all get fresh random names when they change (checked: `cover_`
  plus a uuid, `photos/<id>/<random>`, `faces/<random>`, avatars a unique
  name), so a cached file is never stale. Anything else keeps today's
  behaviour.
- JS-built URLs (`coverSrc` for local uploads) need nothing: uploads are
  cached by path.
- Prod has no reverse proxy (Phil, 2026-11-20): gunicorn on the LAN, and a
  Cloudflare tunnel (`cloudflared`) for outside access. So the app sends the
  headers itself, and Cloudflare's edge honours them.

### 1.4 SQLite WAL

- `PRAGMA journal_mode=WAL` once, in `manage.py migrate` (it's stored in the
  file, so it persists); `PRAGMA synchronous=NORMAL` and
  `PRAGMA busy_timeout=5000` per connection in `get_db_connection()`.
- Why: in the default mode a write locks out readers. With 4 gunicorn
  workers, a bulk edit or an import blocks every page load until it
  commits. In WAL, readers carry on during a write. This is the standard
  setting for SQLite behind a web app.
- What changes: two files beside the DB (`library.db-wal`, `-shm`). The
  site backups and `manage.py` already use the online backup API, which
  handles WAL. A ZFS snapshot is atomic across the dataset, so it's safe. A
  plain `cp library.db` while the app runs is **not** safe any more; the
  README and `deploy/README.md` say so.
- Dev: the same, through `migrate` on service start.

### 1.5 Scripts per style

`cyberpunk.js` (10 KB) and `shelf.js` load in `<head>` without `defer` on
every page in every style, and block the first paint.

Correction (2026-11-20, while screenshotting 16.0f): changing style does
**not** reload the page. `setAppearance` (sidebar.js) swaps `data-style` on
`<html>` in place and reloads only when a shelf page's catalog cabinet has
to be laid out again. So a plain `{% if theme_style == 'cyberpunk' %}`
would leave a page switched to Cyberpunk without its glitch until the next
page load. Options, in order of preference:

- **`defer` both** and keep loading them everywhere. They're small and
  cached (1.3); what costs is blocking the paint, and `defer` ends that.
  `cyberpunk.js` sets `data-boot` before the first paint so the boot screen
  covers the page; that one line moves into the server's render
  (`<html data-boot="on">` when the boot meta is present), so deferring the
  rest is safe.
- Or include each only in its own style **and** have `setAppearance` reload
  when switching into or out of Cyberpunk or Shelf (as it already does for
  the cabinet). Simpler, at the cost of a reload on those switches.

Proposed: the first. `tilt.js` is already deferred.

### 1.6 Compression and the tunnel

- **Through the tunnel:** Cloudflare compresses text responses (gzip or
  brotli) at its edge on its own, so visitors from outside already get
  compressed HTML, CSS and JS. To confirm, from outside the LAN:
  `curl -sI -H 'Accept-Encoding: br, gzip' https://<public host>/static/css/output.css | grep -i content-encoding`.
- **On the LAN** the browser talks to gunicorn directly, uncompressed. On a
  LAN that's milliseconds; not worth middleware.
- **The tunnel is a proxy, as far as the app is concerned.** Every request
  reaches gunicorn from `cloudflared` on 127.0.0.1, with the visitor's IP in
  `X-Forwarded-For`. If prod's `TRUSTED_PROXY_COUNT` is 0, the app sees
  every outside visitor as 127.0.0.1, so they all share **one** rate-limit
  bucket: a stranger guessing passwords locks the login out for everyone,
  and the logs can't tell visitors apart. With `TRUSTED_PROXY_COUNT=1` the
  app reads the real IP. LAN requests carry no such header and are counted
  by their own address either way. **Phil to check prod's `.env`** (question
  1); if it's 0, set it to 1 and restart. A step of this spec adds a line to
  `deploy/README.md` and the public setup docs (16.2): "behind a Cloudflare
  tunnel or any proxy, set `TRUSTED_PROXY_COUNT=1`".
- A tunnel is a sound setup, not a wrong one: no open ports, TLS at the
  edge. The trade-off is that Cloudflare terminates TLS, so it can read the
  traffic. A privacy-minded self-hoster could use a self-hosted tunnel or
  WireGuard to a VPS instead; the public docs can mention both.

### 1.7 Not a problem

The JS is 96 KB gzipped across all page scripts together, and each page
loads only its own (plus `common.js`, 30 KB raw). Not worth bundling or
trimming.

---

## 2. Routing: one shape for every type

### 2.1 What's uneven today

| What | Books | Movies | Music |
|---|---|---|---|
| Shelf | `/base/index` | `/videos/` | `/records/` |
| Household shelf | `/base/shared-library` | `/videos/shared` | `/records/shared` |
| A friend's shelf | `/base/library/<username>` | `/videos/user/<username>` | `/records/user/<username>` |
| Item page | `/books/book/<id>` | `/videos/<id>` | `/records/<id>` |
| Add | `/books/add` | `/videos/add` | `/records/add` |
| Edit | `/books/edit/<id>` | `/videos/edit/<id>` | `/records/edit/<id>` |

Movies and music already share one shape (`media_section.py`'s
`add_url_rule` list); books predate it.

Also:
- Remove and Restore (`/books/remove/<id>`, `/books/restore/<id>`, shared by
  every type) redirect to `books.show_book`, which redirects a movie or album
  again to its own page. Two hops; harmless but sloppy.
- Action URLs come in four shapes: `/books/remove/<id>`, `/loans/<id>/lend`,
  `/photos/photo/<id>/delete`, `/read/delete_reading_session/<id>`.
- Several actions return to `request.referrer` (wishlist notes and quick
  add, transfer, and others), so where you land depends on where you came
  from. Sometimes that's right (quick add from a friend's wishlist), sometimes
  accidental.
- Cover uploads: `book_utils.ALLOWED_EXTENSIONS` is png, jpg, jpeg, gif,
  while avatars also take webp. Not a route, but the same kind of unevenness;
  fixed in section 4.

### 2.2 Proposed

1. **Books match the others:** shelf `/books/`, household `/books/shared`,
   a friend's `/books/user/<username>`, item `/books/<int:id>`, add and edit
   unchanged. The old URLs stay as **301 redirects** (bookmarks, links in old
   notifications, the `shelf_section` cookie). `/books/<int:id>` can't clash
   with `/books/search` or `/books/add`, since it only matches digits.
   Endpoint names stay (`base.index`, `books.show_book`), so templates don't
   change; only the rules move. The reserved-names rule is unaffected
   (`user/<username>` is already the pattern under `/videos`).
2. **Every action lands on its item's own page**, through
   `media.item_endpoint`, never a second redirect.
3. **One shape for new routes:** `/<thing>/<id>/<verb>` (as `/loans/<id>/lend`).
   Existing POST routes are renamed only where touched for another reason;
   they're only called by the app's own forms, so a rename is safe, but it's
   churn. A test lists every POST rule and fails on a new one that isn't
   `<id>/<verb>` shaped, with today's as an allowlist.
4. **A landing table** in this spec's appendix, generated from
   `app.url_map`: every POST action, where it lands for each type. Each
   `request.referrer` becomes a deliberate choice: either an explicit `next`
   field from the form (checked as same-site, as `utils/errors` already
   does) or a fixed page.

### 2.3 Tests

- Each old book URL 301s to the new one, query string kept.
- Remove, Restore, Ownership, Delete on a movie and an album land on that
  type's page in one hop.
- `test_every_page_loads` keeps passing with the new rules.

---

## 3. Covers without orphans

### 3.1 Today

A cover is saved into `static/uploads/` the moment it's fetched:

- a search result's cover (`books.select_search_result` → `save_best_cover`);
- a movie or album lookup's cover (`media_covers`, `music_lookup`,
  `discogs_lookup` → `save_best_cover`);
- every candidate "Find a better cover" downloads (`books.fetch_cover`, one
  file per candidate).

The Edit page deletes the replaced cover when the new one is saved (checked),
so edits are clean. The orphans are the candidates nobody picked, and covers
fetched for an add that was abandoned or given a different cover. Today only
Admin → Orphaned images finds them.

### 3.2 Proposed

- **Fetched covers go to staging,** `uploads/staged/<random>.<ext>`, beside
  the crop tool's `uploads/crop/` and swept the same way: files older than
  24 hours are deleted. `save_best_cover` gets a `staged=True` mode, used by
  every lookup and the cover finder.
- **Saving the item promotes the one in use.** Wherever a form's cover path
  is accepted (`books.add`, `books.edit`, `media_section` add and edit, the
  wishlist add), a staged path is moved (`os.replace`, same filesystem) to
  `uploads/cover_<uuid>.<ext>` and that path is stored. A stored path is
  never a staged one; a test pins it. The path check is a strict pattern
  match, like `cover_crop.is_staged`, never a prefix test.
- **The sweep** runs where staging happens (as `stage_upload` already calls
  `sweep_staged()`), so no timer is needed; at most a day's abandoned
  candidates sit on disk.
- **Admin → Orphaned images stays** as the second line of defence, and
  ignores `staged/` and `crop/` (they clean themselves).
- Edge: a staged cover swept while a form sat open for a day. Saving finds
  the file gone and saves the item without a cover, with a flash ("The
  cover you picked expired; find it again"). Rare, and visible.

### 3.3 Tests

- A lookup's cover lands in `staged/`; adding the item moves it to
  `uploads/`; the stored path is the moved one.
- Unpicked candidates are swept after 24 hours (time faked).
- A path outside `staged/` with the right shape is still refused.

---

## 4. AVIF

### 4.1 Measured (2026-11-20)

40 of dev's covers, decoded and saved again (Pillow 13.0.0, the version in
`requirements.txt`, which writes AVIF natively):

| Format | Total | Per cover to encode |
|---|---|---|
| JPEG (as stored, quality 85) | 1755 KB | n/a |
| WebP, quality 80 | 1085 KB | 12 ms |
| AVIF, quality 60 | 855 KB | 40 ms |

Re-encoding an already-lossy JPEG understates the gain; from a fresh
download or upload, AVIF does a little better again.

### 4.2 Proposed

- **New covers, item photos, placeholder faces and avatars are saved as
  AVIF.** The transparent case (a disc cut by the crop tool, `save_alpha`,
  WebP today) goes AVIF too, since AVIF keeps alpha.
- **No WebP fallback.** Every current browser shows AVIF (Safari since 16,
  2022; Firefox, Chrome and Edge earlier). A `<picture>` fallback would mean
  two files per image and markup in every cover template, for browsers more
  than three years out of date. Not worth it.
- **Existing JPEGs stay** as they are. Converting a JPEG to AVIF stacks a
  second loss on the first, for about half of 25 MB. An optional
  `manage.py convert-covers` could do it later if disk ever matters.
- **Uploads accept AVIF and WebP** for covers as well as avatars (fixing the
  extension mismatch in 2.1), so one list `image_utils.UPLOAD_EXTENSIONS`
  replaces the two.
- **Kept as JPEG:** `book_utils.thumbnail_jpeg` (search-result thumbnails,
  served once and thrown away, where encode speed matters more than size)
  and the crop tool's live preview. The crop tool's staged source
  (`uploads/crop/`, quality 90) stays JPEG as well: it's an intermediate
  that's re-encoded on save.
- **Where AVIF is read back:** the crop tool, 3D faces and the edge colour of
  a vinyl sleeve, the personal export and backups. All of these open the file
  with Pillow, which reads AVIF. The personal export hands photos to the
  user as files; most current tools open AVIF, older Windows ones may need an
  extension. The export's README line says so.
- **Settings in one place:** `image_utils.COVER_FORMAT`,
  `COVER_QUALITY`, so a change of mind is one line.
- Prod needs nothing new: the Pillow wheel bundles libavif. A startup check
  (`features.check('avif')`) logs a warning and falls back to JPEG if a
  build lacks it.

### 4.3 Tests

- Saved covers, photos and faces are AVIF and carry no metadata (the
  existing EXIF-stripping test, extended).
- A transparent crop saves as AVIF with alpha.
- An AVIF upload is accepted for a cover; a `.txt` renamed `.avif` is
  refused (Pillow can't open it).
- Tests that assert a `.jpg` name (`test_photos`, `test_faces`,
  `test_records`, and others) go through the format constant instead.

---

## 5. Upload sizes

Decided (Phil, 2026-11-20): **covers up to 800 px tall** (`MAX_IMAGE_SIZE`
from 500x1000 to 800x1600), sharper on phones and high-DPI screens, at
about what a JPEG cover costs today once it's AVIF. Photos stay at 2000 px.
Existing covers keep their size; a new fetch or upload gets the new one.
Sources often have less than 800 px; a cover is never scaled up.

---

## 6. Book metadata sources: Google, Open Library, or both

### 6.1 Today

Open Library is still there; it has no key, so nothing in `.env` names it.
`book_utils` asks **Google Books first** for search, ISBN lookups and covers,
and falls back to Open Library when Google has nothing or is down (a 5
minute cooldown after an error). Open Library also fills fields Google left
blank, and is in the cover finder's steps. `GOOGLE_BOOKS_API_KEY` is
optional: without it Google is still called, anonymously, with a lower quota.
So there is **no way to keep a self-hosted install from calling Google.**
Movies (TMDb) and music (Discogs, MusicBrainz) aren't part of this.

### 6.2 Proposed

- `BOOK_SOURCES` in `.env`, an ordered list: `google,openlibrary` (the
  default, today's behaviour), `openlibrary,google` (Open Library first,
  Google as the fallback), or `openlibrary` (Google never called: search,
  ISBN, covers, thumbnails, Do I Have This? online, the cover finder).
- One helper, `book_utils.sources()`, read by every place that picks a source
  today (`search_google_books`, `search_books_page`, `fetch_book_details_from_isbn`,
  `cover_search_steps`, `have_online`); the Search tab's "try Open Library"
  link only shows when there's another source to switch to.
- `.env.example` and the public setup docs say plainly: Google has the better
  covers and descriptions for recent books; Open Library is open data, run
  by the Internet Archive, no account, no key, and sees only the ISBN or
  title you look up.
- Open Library asks clients to identify themselves; the User-Agent already
  says `Libaraxia/1.0`. Adding a contact (a URL to the repo) is polite and
  free.
- A per-user choice is possible later (Settings), but a site setting covers
  the self-hosting case, and it's what 17.6's feature switches would build on.

### 6.3 Tests

- `openlibrary` alone: search, ISBN lookup and the cover finder make no
  request to a Google host (the network is blocked in tests, so a call
  raises).
- `openlibrary,google`: Open Library first, Google on a miss.
- Default unchanged: today's tests pass as they are.

---

## Steps (one commit each)

1. Request profiling (dev only); walk the pages; findings appended here.
2. Minified CSS and the test's normalising.
3. Versioned static URLs and cache headers (or the proxy config, per
   question 1).
4. WAL and the connection pragmas; README and deploy notes.
5. Scripts per style.
6. Fixes from step 1's findings, if any.
7. Routing: book URLs and redirects; one-hop landings; the landing table and
   the referrer decisions; the POST-shape test.
8. Covers: staging, promotion, sweep, orphan page ignores staging.
9. AVIF: the format constants, every save site, uploads accept AVIF and
   WebP, tests.
10. Covers up to 800 px tall.
11. `BOOK_SOURCES`, `.env.example`, the User-Agent contact.
12. `TRUSTED_PROXY_COUNT` for the tunnel in `deploy/README.md`.
13. `docs/ARCHITECTURE.md` (image handling, URLs, sources), tick ROADMAP 16.0g.

## Not in this phase

- A CDN, a service worker, HTTP/2 push, bundling JS.
- Converting existing JPEGs.
- Renaming every existing POST route.

## Answered (Phil, 2026-11-20)

1. Prod: gunicorn on the LAN plus a Cloudflare tunnel, no reverse proxy
   (section 1.6).
2. WAL: yes; the app's backups and ZFS snapshots are what matter.
3. Book URLs move to the shared shape, with redirects.
4. AVIF, no fallback, existing JPEGs left alone.
5. Covers up to 800 px tall.

6. `TRUSTED_PROXY_COUNT` is 1 on prod: the tunnel's visitors are counted by
   their real IP already. The docs line in 1.6 still goes in.
7. `BOOK_SOURCES`: the default stays `google,openlibrary`, and Phil's install
   keeps it. The public setup docs (16.2) and `.env.example` spell out all
   three options and why someone might choose Open Library only: keeping a
   personal catalogue away from big tech is the project's point, so the
   choice should be easy to find, not buried.

Approved by Phil, 2026-11-20 ("go ahead").
