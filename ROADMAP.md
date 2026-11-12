# Roadmap

The single list of **open** work for Libaraxia, in the order to do it. Tick items (`[x]`) as they land; when a phase is finished, move it to [docs/ROADMAP-ARCHIVE.md](docs/ROADMAP-ARCHIVE.md) with its date and keep only its line in the table below.

Finished phases (0–8F, 10, 11–13b and 14a) are in the archive, verbatim and with their original numbers, because code comments cite them ("ROADMAP 7.2b", "8B.3", "10.1"). Grep the archive for those.

Priority key: 🔴 do soon · 🟠 important · 🟢 nice to have

## Phases at a glance

| # | Phase | Status |
|---|---|---|
| 0–8F | Design refresh, prod upkeep, data foundations and correctness, access, Goodreads import, page structure, design polish, physical media (movies, music), ownership and formats, collections, Do I have this?, cover quality | Done 2026-11-02 to 2026-11-08, [archive](docs/ROADMAP-ARCHIVE.md) |
| 10 | More styles: Shelf (with the movie rack), Outrun, font choice; Shelf polish | Done 2026-11-08 (polish 2026-11-11), [archive](docs/ROADMAP-ARCHIVE.md#phase-10-more-styles) |
| 11–13b | Shelves hub and Friends page, profile and stats, reading goals, Reviews section, Do I have this? across all types | Done 2026-11-08 to 2026-11-09, [archive](docs/ROADMAP-ARCHIVE.md#phase-11-shelves-one-home-for-every-section) |
| 14a | Bulk edit: select on every grid, eight actions, review, undo | Done 2026-11-11, [archive](docs/ROADMAP-ARCHIVE.md#phase-14a-bulk-edit) |
| 14b | [Granular Goodreads import](#phase-14-bulk-edit-and-granular-import) | In progress (spec approved 2026-11-11). Was Phase 9 |
| 15 | [Movies & TV, lending, cover crop](#phase-15-movies--tv-lending-cover-crop) | After 14 |
| 16 | [Portfolio: README, showcase site, demo](#phase-16-portfolio-readme-showcase-site-demo) | Last: screenshots of the finished app |

**Numbering:** the old Phase 9 is now 14 (2026-11-08), so the open phases run in order after the finished ones. 11 was once the archive fork (dropped, see Not planned); the number is reused. On 2026-11-09 the portfolio phase moved from 15 to 16 so it stays last.

**Why this order:** 14's select mode lives on the grids that 11 built. 15 is three independent features; 15.1 comes first in it because it's a migration and renames the section. 16 photographs the result, so it goes last (the README was already deferred to after bulk edit).

---

## Loose ends

Housekeeping that doesn't belong to a phase. Tick and remove as done.

- [ ] **Prod, Phil, from about 2026-11-09:** in `/home/phil/library-catalog`, delete `library-prod.db`, `libaraxia.db`, `library.db.backup-20251104` and the `library.db.backup-20261102-*` files from the Phase 2 deploy.
- [ ] **Prod, Phil:** Admin → placeholder covers → clear them, then fetch missing covers (the October blank strips, 8F).
- [ ] **Dev DB provenance:** `library.db` in the repo may be an old Goodreads import test rather than a prod copy (Phil, 2026-11-08). Before using it as evidence about prod, or for the 16.1 screenshots, take a fresh anonymised copy of prod's DB.
- [x] **Prod: keep uploads outside the repo folder** (Phil, 2026-11-11; done on prod 2026-11-11). Git treats ignored files as disposable: on 2026-11-11 a fast-forward replaced the dev checkout's ignored `static/uploads` with a committed symlink and deleted every cover in it. Prod's deploy fast-forwards in the same folder as its real covers.
  **Decided 2026-11-11: a symlink, no code change.** Covers move to `/var/lib/libaraxia/uploads` and `static/uploads` becomes a symlink to it. Checked against the code: the delete and crop guards (`image_utils.delete_image_file`, `cover_crop._source_file`) `realpath` both the uploads root and the file, so both resolve through the link; Flask serves static files through it; `.gitignore`'s `static/uploads` (no trailing slash) matches a symlink, so `deploy.sh` still sees a clean tree. If git ever replaces the link, the covers are untouched. Runbook, in `/home/phil/library-catalog`:
  1. `systemctl show -p User library-catalog.service` (the new folder must be writable by that user).
  2. `sudo systemctl stop libaraxia-deploy.timer`
  3. `sudo mkdir -p /var/lib/libaraxia/uploads && sudo chown -R <user>: /var/lib/libaraxia`, then `rsync -a static/uploads/ /var/lib/libaraxia/uploads/` (trailing slashes matter).
  4. `sudo systemctl stop library-catalog.service`, the same `rsync` again, `mv static/uploads ~/uploads.pre-move-20261111` (outside `static/`, so it isn't served), `ln -s /var/lib/libaraxia/uploads static/uploads`, `sudo systemctl start library-catalog.service`.
  5. Check: `ls -l static/uploads` shows the link; `git status --short` is empty; covers show; a new cover or avatar lands in `/var/lib/libaraxia/uploads`. If a reverse proxy serves `/static/` itself, it must follow symlinks (nginx does unless `disable_symlinks` is set).
  6. `sudo systemctl start libaraxia-deploy.timer`. Back up `/var/lib/libaraxia` (ZFS snapshot or nightly rsync). Delete `~/uploads.pre-move-20261111` after a week.
  Rollback: stop the service, `rm static/uploads` (no trailing slash: removes the link only), `mv ~/uploads.pre-move-20261111 static/uploads`, start.
- [ ] **Dev, Phil: the same move on the dev checkout.** Today `static/uploads` is still a real folder (backup copy in `~/Pictures/libaraxia/static/uploads`). Same steps with `~/.local/share/libaraxia/uploads` (stop the dev server, `mv` the folder there, `ln -s` it back, keep Pictures as the rsync'd backup). Give the `../libaraxia-bulk` worktree the same link, or remove it (its branch is merged).
- [ ] **Later, optional: `UPLOAD_FOLDER` as an env setting** instead of the symlink. `app.py` hard-codes `static/uploads`, and the image helpers assume it (`is_safe_upload_path`, `delete_image_file`, `image_utils.STATIC_ROOT` / `cover_missing`, orphan cleanup, cover crop staging, exports); it would also need a route to serve the files. Only worth doing if the symlink ever gets in the way. `DATABASE_PATH` already lets the DB live outside the repo. Also: `test_clear_placeholder_covers` writes two temporary files into the real `static/uploads` (and removes them); point it at a temp folder.
- [ ] **Search should match the grid you're on** (Phil, 2026-11-10). Today every Books search goes to `/books/search`, which covers you and your household, whichever grid you searched from, and it drops the filters. On your own shelf it should search only your books, on the Household grid the household's, and the Movies and Music grids likewise (they already stay on their own page). Then the search box's count ("Search your 120 books") is exactly what gets searched. Also decide whether a search keeps the filters and sort you had. Relevant to bulk edit, which selects within the current view; `utils/grid_query.py` is the place to share the query.

---

## Phase 14: Bulk edit and granular import

From Phil, 2026-11-08 (was Phase 9, then 13). Its own phase: a whole selection-and-actions UI, not a tweak.
**Spec: [docs/BULK-EDIT-SPEC.md](docs/BULK-EDIT-SPEC.md)** (approved 2026-11-10). Built on branch `phase-14-bulk-edit` in the worktree `../libaraxia-bulk`, one step at a time; Phil commits and merges (spec section 14).

14a (bulk edit) is done: [archive](docs/ROADMAP-ARCHIVE.md#phase-14a-bulk-edit).

### 14b Granular Goodreads import 🟢
**Spec: [docs/GOODREADS-IMPORT-SPEC.md](docs/GOODREADS-IMPORT-SPEC.md)** (approved 2026-11-11; brief: [docs/GOODREADS-IMPORT-BRIEF.md](docs/GOODREADS-IMPORT-BRIEF.md)). Branch `phase-14b-goodreads-import`, worktree `../libaraxia-import` (set up 2026-11-11). Claude does the git work: commits each step on the branch once Phil approves it, merges into `main` at M1/M2 when Phil says; Phil pushes (spec section 14, "Git").
- **To start a step**, in a fresh session (replace N with the next unticked step; the first sentence only when the previous step was approved):
  > Step N-1 is approved: commit it on the branch first. Then Phase 14b, step N: granular Goodreads import. Read docs/GOODREADS-IMPORT-SPEC.md in full, then CLAUDE.md, ROADMAP.md (14b), and BULK-EDIT-SPEC.md sections 2, 3, 9 and 14 (where they differ, the Goodreads spec's section 14 wins). Work in the worktree ../libaraxia-import on branch phase-14b-goodreads-import, following the spec's section 14 pipeline. Build step N only. Where the spec and the code disagree, stop and tell me. Leave step N uncommitted; stop and report when it's done.
- [x] Re-spec after 14a (replaces BULK-EDIT-SPEC section 16).
- [x] 1. Parser: `goodreads_id` and `shelves` from `parse_row`.
- [ ] 2. Migration 032 (staging, imports, rows). **Merge point M1.**
- [ ] 3. `utils/goodreads_plan.py` stage + plan, headless (boxes, fill, choices).
- [ ] 4. Apply and undo, headless (provenance, bulk journal).
- [ ] 5. Routes and the review page; old route removed.
- [ ] 6. Provenance in the UI: From Goodreads filter, book page note.
- [ ] 7. Dry run on a prod copy (Phil), wrap-up. **Merge point M2.**

---

## Phase 15: Movies & TV, lending, cover crop

From Phil, 2026-11-09 (loose notes, sorted). The format icons from the same note (turntable for LP, disc-2 for CD, cassette-tape for Cassette on the Music grid) were done the same day, in `_format_icon.html`.

### 15.1 Movies & TV 🟠
Decided 2026-11-09 (Phil). Today a TV season box set is a video row like any film, so the section says "Movies" about things that aren't. Same physical object (a DVD or tape), same statuses (watched / want to watch), same shelf: it doesn't get its own media type, which would mean another view, blueprint section, statuses, stats tab and lookup for one distinction. Renaming the section back to "Video" was the other option: less work, but no movie/TV filter.
- [ ] **Migration 030:** `books.video_kind` (`'movie'` / `'tv'`; NULL means movie, so existing rows need no backfill) and `books.season` (free text: "Season 2", "Complete series"). A lookup table for the kinds, like `media_types`, if it stays in step with `utils/media.py`; a CHECK is fine for two values. Fold it into `create_database.sql` and the ledger. Check `library_videos` (and the other views) expose the new columns; the export and `card_json` carry them.
- [ ] **UI wording:** the section is **"Movies & TV"** (sidebar, headings, flashes, feed, the Books | Movies | Music switch if it fits at phone width, else "Movies" there only), through `media.media_labels()`. Code, URLs and the DB keep "video". Item wording per kind where it reads oddly ("Add TV show", "Director" becomes "Creator" for TV).
- [ ] **Form:** Kind (Movie / TV) and Season on the add and edit form (`_item_fields.html`); Season only shown for TV.
- [ ] **Grid:** a "TV" badge on the cover beside the format badge, a Kind filter in the panel, "S2" or the season text in list view.
- [ ] **Lookup:** TMDb searches `/search/movie` and `/search/tv` together; a candidate's kind fills Kind (also in Do I have this? online candidates, `utils/have_online.py`). Runtime for a set is the total, or left empty.
- [ ] Stats: hours watched stay one number; a by-kind split is a nice-to-have.
- [ ] Tests: migration on an existing DB (NULL = movie), the form round-trip, filter, TMDb TV candidate, wording.

### 15.2 Lend an item 🟠
Record who has a physical copy, for any type.
- [ ] A `loans` table (migration): `book_id` (CASCADE), `lent_by` (the owner), `borrower_id` (a user in your circle, nullable) or `borrower_name` (free text, for someone not on the site), `lent_at`, `due_at` (optional), `returned_at`, `note`. One open loan per item.
- [ ] Item page: Lend / Mark returned (POST, owner or household member, as the shelf it's on). A "Lent to Bob" badge on the cover, a Show: lent filter, and a "Lent out" row on Shelves.
- [ ] Do I have this? answers "yours, lent to Bob since March". The borrower (if a user) sees "Borrowed from Alice" on the item page and a list on their profile; a notification when lent, none when returned.
- [ ] Loan history kept (returned loans stay, shown on the item page). Exports include loans.
- Lending within a household is still worth recording (who physically has it), so it isn't limited to friends.

### 15.3 Free-form cover crop and perspective tool 🟢 (done 2026-11-10)
For fetched covers with borders, scans of a whole sleeve and phone photos taken at an angle.
- [x] A full-screen `<dialog>` on Add and Edit (Books, Movies, Music and the wishlist's add), opened by "Crop / straighten" under the cover preview. Crop mode (drag the corners, any ratio) and Perspective mode (each corner on its own, pulled back to a rectangle); rotate left/right, ratio menu (Free, Original, 1:1, 2:3, 3:4, DVD) with portrait/landscape, Reset; Crop keeps the tool open for tweaks, then Undo / Cancel / Save. Pointer events (mouse, touch, pen), keyboard (arrows nudge a handle, Shift x10, Enter crops, Esc cancels, Ctrl+Z undoes) and a 3x loupe while dragging a corner.
- [x] Non-destructive until the form is saved: the browser sends only geometry (fractions of the image); `utils/cover_crop.py` renders from the server's copy (rect crop or a pure-Python homography for Perspective), previews are never stored, Save writes `crop_source` / `cover_crop` and the page's own Save stores the cover. A picked photo is staged once at up to 2400 px (`uploads/crop/`, EXIF and GPS stripped, swept after 24 h) so a phone photo isn't shrunk to 500x1000 before cropping. Old files go through `delete_image_file()`; only staged files are ever deleted because the browser named them.
- [x] Tests: `tests/test_cover_crop.py` (geometry validation, rendering, routes, all save routes, path safety) and `tests/test_cover_crop_js.py` (the JS helpers under node, checked against the server's renderer).
- Later ideas, not planned:
  - [ ] Keep a high-res original next to each saved cover, so a re-crop of a saved cover isn't limited to its 500x1000 copy.
  - [ ] Auto-detect the cover's corners for Perspective.
  - [ ] A fine-angle straighten slider.
  - [ ] Avatars.

---

## Phase 16: Portfolio: README, showcase site, demo

From Phil, 2026-11-08: for a portfolio, not commercial or public use.

### 16.1 README and screenshots 🟠
- [ ] Retake the README screenshots in every style (Negative Earth, OG, Shelf, Outrun) and both modes, from an **anonymised copy** of the DB (rename other users, clear their emails, bios, avatars and review text), never the live one. Bring the README up to date (sections, Do I Have This?, reviews, styles).

### 16.2 Showcase site spec 🟠 (medium)
- [ ] Write `docs/SHOWCASE-SPEC.md` first; build after it's agreed. A static site (Hugo or Astro, which Phil already uses) showing the project's progress as a **timeline**: a fancy changelog.
  - Sources: the git history, the archived phases and their dates (`docs/ROADMAP-ARCHIVE.md`), `docs/DEVLOG.md`, and before/after screenshots per phase (the 2026-11-02 set, the Phase 0 refresh, styles, sections).
  - A feature tour and a short "how it's built" page (raw SQLite with tracked migrations, CSP with no inline JS, the SSRF guard, the access model, auto-deploy on green CI).
  - Same privacy rule as 16.1: anonymised data only. No tracking scripts, self-hosted fonts, Phil's house style.
  - Where it lives: a subpath or subdomain of philcifone.com; decide in the spec.

### 16.3 Open demo server 🟢 (low)
- [ ] Only if the showcase (16.2) wants a live link. Best practice for a public demo:
  - a separate instance, user and systemd unit, its own `SECRET_KEY` and DB, no prod secrets (no API keys, or separate rate-limited ones);
  - seeded fake data, reset on a timer (copy a seed DB nightly or hourly);
  - a shared demo login, or per-visitor throwaway accounts that expire; registration, email and password change off;
  - uploads off or tightly capped, outbound lookups off or stubbed, rate limits on;
  - behind the existing reverse proxy, `noindex`, a banner saying data resets.

---

## Parked

Not scheduled; pick up only when Phil asks.
- Outrun: angled card and button corners via `clip-path` (it also clips borders and focus outlines, so draw those inside the shape). Animations: none yet; any added must respect `prefers-reduced-motion`.
- Audiobookshelf integration for audiobooks (docs/ARCHITECTURE.md, product direction).

## Not planned

- **The archive fork** ([FORK-SPEC.md](FORK-SPEC.md)): out of scope (Phil, 2026-11-08). It was Phase 11, parked; the spec stays for the record.
- **Docker** is reference-only, since prod runs gunicorn directly. If it's ever revived: move off `python:3.11-slim-bullseye` (Debian 11 is EOL), add a non-root `USER`, drop `gcc`, use `--log-level info`, and the consolidated schema from Phase 2.1.
