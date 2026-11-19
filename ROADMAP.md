# Roadmap

The single list of **open** work for Libaraxia, in the order to do it. Tick items (`[x]`) as they land; when a phase is finished, move it to [docs/ROADMAP-ARCHIVE.md](docs/ROADMAP-ARCHIVE.md) with its date and keep only its line in the table below.

Finished phases (0–8F, 10, 11–13b, 14a, 14b, 14c and 15) are in the archive, verbatim and with their original numbers, because code comments cite them ("ROADMAP 7.2b", "8B.3", "10.1"). Grep the archive for those.

Priority key: 🔴 do soon · 🟠 important · 🟢 nice to have

## Phases at a glance

| # | Phase | Status |
|---|---|---|
| 0–8F | Design refresh, prod upkeep, data foundations and correctness, access, Goodreads import, page structure, design polish, physical media (movies, music), ownership and formats, collections, Do I have this?, cover quality | Done 2026-11-02 to 2026-11-08, [archive](docs/ROADMAP-ARCHIVE.md) |
| 10 | More styles: Shelf (with the movie rack), Outrun, font choice; Shelf polish | Done 2026-11-08 (polish 2026-11-11), [archive](docs/ROADMAP-ARCHIVE.md#phase-10-more-styles) |
| 11–13b | Shelves hub and Friends page, profile and stats, reading goals, Reviews section, Do I have this? across all types | Done 2026-11-08 to 2026-11-09, [archive](docs/ROADMAP-ARCHIVE.md#phase-11-shelves-one-home-for-every-section) |
| 14a | Bulk edit: select on every grid, eight actions, review, undo | Done 2026-11-11, [archive](docs/ROADMAP-ARCHIVE.md#phase-14a-bulk-edit) |
| 14b | Granular Goodreads import, site and personal backups, "Unshelved" | Done 2026-11-12, [archive](docs/ROADMAP-ARCHIVE.md#phase-14b-granular-goodreads-import) |
| 14c | Tweaks after 14b: CSRF, undated sessions, Settings for everyone, profile tabs, cyclers, Shelf bookcases and boxed covers, username collisions | Done 2026-11-12, [archive](docs/ROADMAP-ARCHIVE.md#phase-14c-tweaks-after-14b) |
| 15 | Movies & TV (a Kind and Season on videos, TMDb TV lookup), free-form cover crop | Done 2026-11-12 (15.3 on 2026-11-10), [archive](docs/ROADMAP-ARCHIVE.md#phase-15-movies--tv-cover-crop). Lending moved to 17.1 |
| 16 | [Portfolio: README, showcase site, demo](#phase-16-portfolio-readme-showcase-site-demo) | Photos, condition and value (16.0a) done 2026-11-15; left: lending and Audiobookshelf (16.0d, 16.0e, moved up from 17 on 2026-11-18), a final layout pass, a code review, then screenshots of the finished app |
| 17 | [Future roadmap](#phase-17-future-roadmap) | After the portfolio; shown on the showcase site as what's next |

**Numbering:** the old Phase 9 is now 14 (2026-11-08), so the open phases run in order after the finished ones. 11 was once the archive fork (dropped, see Not planned); the number is reused. On 2026-11-09 the portfolio phase moved from 15 to 16 so it stays last.

**Why this order:** 14's select mode lives on the grids that 11 built. 15 is Movies & TV (a migration and the section rename) plus the finished cover crop. 16 photographs the result, so the app is feature-complete before it (the README was already deferred to after bulk edit). 17 is after the portfolio on purpose: ideas worth doing that the showcase site lists as the future roadmap.

---

## Loose ends

Housekeeping that doesn't belong to a phase. Tick and remove as done.

- [x] **Cyberpunk style** (Phil, 2026-11-18; branch `cyberpunk`): a fifth style forked from Outrun (its fonts, dark only, accent selectable) with a Gruvbox CRT palette, HUD corners (filled on cards, cut on header bars, buttons, chips, avatars), segmented stats bars, a CRT layer and a boot screen once per login. Pass 2: boot readouts from the user's counts, a timed glitch (page title on load, a random cover or heading every 10 s), status lights, cover brackets, terminal flash messages, NO SIGNAL empty states, selection, scrollbars and caret; login flashes now wait for the boot screen. Also fixed for every style: the sort row painted over the open filter panel on shelf pages.
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
- [ ] **TMDb key in dev logs** (found 2026-11-12; low risk, optional: a free, read-only key that only reached local dev logs and a Claude transcript. Step 3 is done, so nothing new leaks; 1 and 2 whenever convenient). `TMDB_API_KEY` is a v3 key, which `media_lookup._tmdb` has to send as `?api_key=` in the URL. In dev, `app.py` sets the root logger to DEBUG when Flask's DEBUG is on, and urllib3 logs every request URL at DEBUG, so the key ends up in dev server logs (and it was printed in a Claude session). Prod runs at INFO, so prod's logs should be clean; worth a `grep api_key` on prod's journal to be sure. Fix, all three cheap:
  1. Rotate the v3 key on themoviedb.org (Settings → API) since it has been in logs.
  2. Put the v4 **API Read Access Token** in `TMDB_API_KEY` instead (same settings page). The code already sends a value longer than 40 characters as an `Authorization: Bearer` header, never in a URL, so nothing else changes. Do it in `.env` on dev and prod.
  3. Done 2026-11-15 (16.0a step 7): in `app.py`'s logging setup, `logging.getLogger('urllib3').setLevel(logging.INFO)`, so no third-party query string reaches a log even at DEBUG (Discogs' token is a header already; UPCitemdb has no key).

---

## Phase 14: Bulk edit and granular import

From Phil, 2026-11-08 (was Phase 9, then 13). Its own phase: a whole selection-and-actions UI, not a tweak.
**Spec: [docs/BULK-EDIT-SPEC.md](docs/BULK-EDIT-SPEC.md)** (approved 2026-11-10). Built on branch `phase-14-bulk-edit` in the worktree `../libaraxia-bulk`, one step at a time; Phil commits and merges (spec section 14).

14a (bulk edit) is done: [archive](docs/ROADMAP-ARCHIVE.md#phase-14a-bulk-edit).

14b (Goodreads import, backups, Unshelved) is done: [archive](docs/ROADMAP-ARCHIVE.md#phase-14b-granular-goodreads-import).

---

14c (tweaks after 14b) is done: [archive](docs/ROADMAP-ARCHIVE.md#phase-14c-tweaks-after-14b).

15 (Movies & TV, cover crop) is done: [archive](docs/ROADMAP-ARCHIVE.md#phase-15-movies--tv-cover-crop).

---

## Phase 16: Portfolio: README, showcase site, demo

From Phil, 2026-11-08: for a portfolio, not commercial or public use.

### 16.0 Final layout pass 🟠
Before the screenshots (Phil, 2026-11-12). Layout only, no new features: go app- and style-wide over the pages that grew piece by piece and still read as stacked cards: Activity Feed, Notifications, Friends, Wishlist, Settings and Admin, the review pages, Do I Have This?. Spacing, widths (the 4xl / 7xl mix), card nesting, headings, phone layouts, and the Shelf bookcase look where it belongs (in Shelf it's on headings, the feed, notifications and the item page so far). Check all four styles in both modes.
**Spec: [docs/STYLE-TWEAKS-SPEC.md](docs/STYLE-TWEAKS-SPEC.md)** (approved 2026-11-12, from Phil's style-tweaks brief): the bookcase rule, a refactor to shared tokens and one cover component, Shelf tweaks, Friends and profile changes, cover glare. Branch `phase-16-style-pass`, one commit per step (spec section 10).
- [ ] Walk every page at phone and desktop width in each style; list what's off; fix in one pass. After 16.0d and 16.0e, so it covers their pages too.
- [x] Feed: the dismiss X and the like/comment row sit in fixed corners; give them a place in the layout. Done 2026-11-13: the feed card is the Reviews list's card, the like in its own row (style pass steps 5 and the taste pass).

### 16.0a Photos, condition and value 🟢 (done 2026-11-15, merged to main)
Built on branch `phase-16a-photos-value` (migrations 036 to 040); the full list is in [docs/ROADMAP-ARCHIVE.md](docs/ROADMAP-ARCHIVE.md#phase-160a-photos-condition-and-value). Still open:
- [ ] Later, low priority: a cover-shape override for sets that aren't the standard shape (non-square disc sets), which the 3D box would take its proportions from; until then such a set is right as soon as its own photos are (the box follows the cover photo's shape).
- [ ] Later, low priority: the Disney clamshell's own shape (white plastic, rounded, opens like a book). Coloured tapes and plastic clamshells are placeholders in 16.0c.
- [ ] Phil's setup (spec section 7): Discogs seller settings (done 2026-11-17, price suggestions verified); an eBay developer account and production keys. The same steps go in the README at 16.1.

### 16.0c Faces and placeholders 🟠
From Phil, 2026-11-15. **Spec: [docs/FACES-SPEC.md](docs/FACES-SPEC.md).** Every face of every type takes a photo (a bottom too), and the plain faces become admin-chosen placeholder images, grouped into sets (White clamshell, Nickelodeon, clear or black DVD case) that an owner picks per item. A VHS with a top photo is a sleeve, without one a clamshell. Branch `phase-16c-faces`.
- [x] Before it: the crop tool opens in Perspective everywhere; the Shelf style's heading bookcase is taller and its books stand most of its height.
- [x] 1. Bottom kind; every face for every type; the 3D bottom face; flat box faces for every type.
- [x] 2. Admin → Placeholders: library and sets (a default set per body at first; dropped, see below).
- [x] 3. Choosing on the edit page and the add form; face resolution; sleeve or clamshell.
- [x] 4. Docs, screenshots.
- [x] Then: VHS tapes on the Movies heading, as the books on the Shelves one (same seed, your own Movies page).
- [x] Then (Phil, 2026-11-16): Admin → Placeholders as one tab per medium (VHS sleeves and clamshells together; the set names say which); no default sets, nothing automatic (an item shows a placeholder only where its owner picked one); a top or bottom uploaded upright is turned to lie wide, a spine or side to stand tall. Bulk edit's More menu applies a set to the selection (undoable). Shelf's flat box: a vinyl sleeve is 1px in its cover's edge colour; a CD shows its spine on its right side; a book's plain top and side are lined pages, as in 3D and on the heading.

### 16.0d Lend an item 🟠
Moved up from 17.1 (Phil, 2026-11-18; originally 15.2). Record who has a physical copy, for any type.
**Spec: [docs/LENDING-SPEC.md](docs/LENDING-SPEC.md)** (approved 2026-11-18). Decided: the owner or any household member lends and marks returned; a borrower who's a user is in the lender's circle, anyone else is a typed name; loans show to the shelf's people and the borrower only; the borrower is notified on lending, the owner when someone else lends or returns their item; the Lent badge sits top centre (open to change). Branch `phase-16d-lending-abs`, shared with 16.0e, lending first.
- [x] 1. `loans` table (migration 042), `utils/loans.py`.
- [x] 2. Item page: banner, Lend, Mark returned, history; `can_view_book` for borrowers; the notification.
- [x] 3. Grid badge, Show: Lent out, the Collections row, the profile's Borrowed row.
- [x] 4. Do I have this?, exports.
- [x] 5. Docs, screenshots (item page, grids and Collections in every style; the 16.0 walk covers the rest).

### 16.0e Audiobookshelf connection 🟠
Moved up from 17.2 (Phil, 2026-11-18). Read-only from Phil's Audiobookshelf server: an import of finished and in-progress audiobooks (unowned Audiobook books with a status and a session, after a review, undoable) and a live progress line on imported items.
**Spec: [docs/AUDIOBOOKSHELF-SPEC.md](docs/AUDIOBOOKSHELF-SPEC.md)** (approved 2026-11-18; the API was probed on Phil's server). Decided: one server for the site (`AUDIOBOOKSHELF_URL`, the LAN address), each user's own API key in Settings, encrypted at rest; review, then apply; started books by default (an option for the rest); ebooks too (a new `Ebook` format); a narrator and a length for audiobooks, and hours listened in Stats; podcasts and books at 0 % stay out; nothing from ABS is owned unless the catalogue already says so. Same branch, after 16.0d.
- [x] 1. Migration 043; the Ebook format, narrator and length on the forms and item page.
- [x] 1b. An Audiobooks block in the Books stats (hours listened).
- [x] 2. The client and key encryption.
- [ ] 3. Settings card: connect, disconnect.
- [ ] 4. Sync and the review page.
- [ ] 5. Apply, undo, covers.
- [ ] 6. Live progress line, provenance note.
- [ ] 7. Docs, a real sync on dev, screenshots.

### 16.0b Code review 🟠
The last step before the portfolio, once Phil calls the app feature-complete enough: spend one of the free Claude Code multi-agent cloud reviews on it. Phil runs it (it's user-triggered and billed; Claude can't start it): `/code-review ultra` on the branch, or `/code-review ultra <PR#>`. Triage the findings into fixes before 16.1, so the screenshots show the fixed app.
- [ ] Run the review, triage, fix.

### 16.1 README and screenshots 🟠
- [ ] README: the optional value sources' setup (Discogs seller settings, eBay keys), from docs/PHOTOS-VALUE-SPEC.md section 7.
- [ ] Retake the README screenshots in every style (Negative Earth, OG, Shelf, Outrun, Cyberpunk) and both modes, from an **anonymised copy** of the DB (rename other users, clear their emails, bios, avatars and review text), never the live one. Bring the README up to date (sections, Do I Have This?, reviews, styles).

### 16.2 Showcase site spec 🟠 (medium)
- [ ] Write `docs/SHOWCASE-SPEC.md` first; build after it's agreed. A static site (Hugo or Astro, which Phil already uses) showing the project's progress as a **timeline**: a fancy changelog.
  - Sources: the git history, the archived phases and their dates (`docs/ROADMAP-ARCHIVE.md`), `docs/DEVLOG.md`, and before/after screenshots per phase (the 2026-11-02 set, the Phase 0 refresh, styles, sections).
  - A "What's next" page from Phase 17 (scrobbling, email, the fediverse idea).
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

## Phase 17: Future roadmap

From Phil, 2026-11-12: after the portfolio (16), and listed on the showcase site (16.2) as the project's future roadmap. Not scheduled; each item gets a short spec or a prompt with its open questions before it's built. 17.1 (lending) and 17.2 (Audiobookshelf) moved up to 16.0d and 16.0e on 2026-11-18; the numbers aren't reused.

### 17.3 Scrobble listens to Last.fm / ListenBrainz 🟢
When you log a listen of a record (a reading session on a vinyl or CD, the album's Listening History), send it as scrobbles.
- [ ] Per-user opt-in in Settings, one or both services: ListenBrainz with a user token (simple, open, preferred); Last.fm needs an API key app-wide plus each user's session key (web auth flow).
- [ ] What gets sent: the album's tracks from its track list (Discogs / MusicBrainz data already stored), timestamps working back from the session's date, or one "album listened" if there's no track list. Only dated sessions; never back-fill old ones without asking.
- [ ] Sent in the background with retries; a failure never blocks saving the session. A note on the item page of what was sent, and no double scrobble when a session is edited.

### 17.4 Email on prod 🟢
The code is there (Flask-Mail, `utils/email_utils.py`: verification emails, `EMAIL_VERIFICATION_REQUIRED`, the `MAIL_*` settings in `.env.example`), but prod has no mail set up, so verification is off.
- [ ] Choose the sender: an SMTP relay (Phil's own domain mail provider, or a transactional service) rather than running a mail server on the container, which needs SPF, DKIM, DMARC and reverse DNS to be delivered at all. Prod sits behind a Cloudflare tunnel, which only matters for inbound; outbound SMTP on 587 must be allowed from the container.
- [ ] Set SPF / DKIM / DMARC for the sending domain; send a test; turn `EMAIL_VERIFICATION_REQUIRED` on.
- [ ] Write the steps in the README (a "Email (optional)" section: provider settings, DNS records, the `.env` lines, how to test, what users see) and in `deploy/README.md` for prod.
- [ ] While there: password reset by email, which needs the same setup.

### 17.5 Fediverse integration? 🟢 (low priority, low likelihood)
Added 2026-11-12 (Phil). Unsure it's possible or wanted; an idea to look into, not a plan. Low priority and unlikely to happen; do it last, if at all. BookWyrm (ActivityPub, books and reviews) is the nearest existing thing, so this would be a small slice of what it does, not a new protocol.
- [ ] Spec first. Decide before building: what, if anything, goes public (a finished book, a review, a status line), and whether that fits the access model, which has no per-item privacy and shows things only to your circle. Anything federated is public and can't be recalled, so it would need to be opt-in per user and per post.
- [ ] The smallest useful version: each opted-in user gets an ActivityPub actor (WebFinger, an actor document, an outbox, HTTP signatures) that publishes reviews or "finished" posts to followers on Mastodon and the like. Read-only first; no inbox, replies or boosts.
- [ ] Open questions: needs a public hostname and HTTPS (prod has that), a background queue for delivery with retries, and moderation (blocking a domain or actor) once anything comes in. Check whether a bridge or an existing tool (a feed-to-fediverse bridge over an RSS feed of public reviews) gets most of the value with none of this.

---

## Parked

Not scheduled; pick up only when Phil asks.
- Outrun: angled card and button corners via `clip-path` (it also clips borders and focus outlines, so draw those inside the shape). Animations: none yet; any added must respect `prefers-reduced-motion`. Cyberpunk now does this (styles.css "Cyberpunk shapes": filled corners on an overlay for cards, `clip-path` plus a gradient edge for the rest); Outrun could reuse it.

## Not planned

- **The archive fork** ([FORK-SPEC.md](FORK-SPEC.md)): out of scope (Phil, 2026-11-08). It was Phase 11, parked; the spec stays for the record.
- **Docker** is reference-only, since prod runs gunicorn directly. If it's ever revived: move off `python:3.11-slim-bullseye` (Debian 11 is EOL), add a non-root `USER`, drop `gcc`, use `--log-level info`, and the consolidated schema from Phase 2.1.
