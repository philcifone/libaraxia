# Roadmap

The single list of **open** work for Libaraxia, in the order to do it. Tick items (`[x]`) as they land; when a phase is finished, move it to [docs/ROADMAP-ARCHIVE.md](docs/ROADMAP-ARCHIVE.md) with its date and keep only its line in the table below.

Finished phases (0–8F and 10) are in the archive, verbatim and with their original numbers, because code comments cite them ("ROADMAP 7.2b", "8B.3", "10.1"). Grep the archive for those.

Priority key: 🔴 do soon · 🟠 important · 🟢 nice to have

## Phases at a glance

| # | Phase | Status |
|---|---|---|
| 0–8F | Design refresh, prod upkeep, data foundations and correctness, access, Goodreads import, page structure, design polish, physical media (movies, music), ownership and formats, collections, Do I have this?, cover quality | Done 2026-11-02 to 2026-11-08, [archive](docs/ROADMAP-ARCHIVE.md) |
| 10 | More styles: Shelf (with the movie rack), Outrun, font choice | Done 2026-11-08, [archive](docs/ROADMAP-ARCHIVE.md#phase-10-more-styles) |
| 11 | [Shelves: one home for every section](#phase-11-shelves-one-home-for-every-section) | Next |
| 12 | [Profile and stats](#phase-12-profile-and-stats) | After 11: stats use its section switch |
| 13 | [Reviews section](#phase-13-reviews-section) | Done 2026-11-09 |
| 13b | [Do I have this? across all three types](#phase-13b-do-i-have-this-across-all-three-types) | Next: after 13 |
| 14 | [Bulk edit and granular import](#phase-14-bulk-edit-and-granular-import) | After 11: select mode lives on the new grids. Was Phase 9 |
| 15 | [Portfolio: README, showcase site, demo](#phase-15-portfolio-readme-showcase-site-demo) | Last: screenshots of the finished app |

**Numbering (2026-11-08):** the old Phase 9 is now 14, so the open phases run in order after the finished 10. 11 was once the archive fork (dropped, see Not planned); the number is reused.

**Why this order:** 11 changes the navigation and the grid pages' shape, and adds the Books | Movies | Music switch; 12, 13 and 14 all build on those (the switch, the grids), so doing them first would mean redoing them. 12 is small and self-contained, so it goes before the two bigger features. 15 photographs the result, so it goes last (the README was already deferred to after bulk edit).

---

## Loose ends

Housekeeping that doesn't belong to a phase. Tick and remove as done.

- [ ] **Prod, Phil, from about 2026-11-09:** in `/home/phil/library-catalog`, delete `library-prod.db`, `libaraxia.db`, `library.db.backup-20251104` and the `library.db.backup-20261102-*` files from the Phase 2 deploy.
- [ ] **Prod, Phil:** Admin → placeholder covers → clear them, then fetch missing covers (the October blank strips, 8F).
- [ ] **Dev DB provenance:** `library.db` in the repo may be an old Goodreads import test rather than a prod copy (Phil, 2026-11-08). Before using it as evidence about prod, or for the 15.1 screenshots, take a fresh anonymised copy of prod's DB.
- [ ] **Trim CLAUDE.md** after Phase 11 (it's loaded into every session, ~8k tokens): Phase 11 rewrites the navigation and blueprint notes anyway, so do one pass then. Keep the gotchas and conventions; drop history ("was Vinyls until ...", settled product-direction notes) and anything the code says plainly.

---

## Phase 11: Shelves, one home for every section

From Phil, 2026-11-08: the sidebar is getting full, and Library, Movies and Music are practically the same page.

### 11.0 "Unread" instead of "Untracked", and honest filter pills 🟢
Done 2026-11-08.
- [x] No status reads as what it means for something you own: **Unread** / **Unwatched** / **Not listened to** (`media.NO_STATUS_LABEL`, `media_labels()['no_status']`) instead of *Untracked*, in the item page's status menu and the export. Wording only: no status is still no row (the menu's value stays `untracked`, which clears it).
- [x] **"Did Not Finish" filter showed unread books** (Phil, on prod). Nothing sets DNF in bulk (the old importer only set read / currently reading / want to read, the current one only from DNF-named shelves), and the filter is an exact match. The cause: the panel only filters on **Apply**, but picking a status already added its pill to "Active filters" and bumped the funnel's count, so the page looked filtered while the grid still showed everything. Now the pills and count show the filters the page was loaded with (`appliedFilters`, `renderAppliedFilters` in `script.js`), and a pending change shows on the button instead ("Apply 1 change", `filtersChanged`, `countFilterChanges`). Checked in a browser: pick DNF, no pill, "Apply 1 change"; apply, one book and its pill.
- [x] On the way: the Library's status filter listed raw values ("did not finish"); it uses the labels now (`STATUS_LABELS` template global).
- If prod ever shows DNF rows Phil didn't set, check where they came from first: `sqlite3 library.db "select date(created_at), count(*) from collections where status = 'did not finish' group by 1"`.

### 11.1 Shelves page 🟠
Done 2026-11-08.
- [x] One sidebar entry **Shelves** in place of Library, Movies and Music (`base.shelves`, `/base/shelves`).
- [x] Every grid page starts with `shelf_header()` (`templates/_shelves.html`): scope tabs **Mine | Household | Friends'**, the heading (**Shelves**, Household Shelves, Friends' Shelves, *name*'s Shelves), then the **Books | Movies | Music** switch, then search and the grid. The switch keeps the scope: Household → Movies is the household's movies, a friend's books link to that friend's movies and music (`section_switch()` on `friend_library.html`, under the friend's card).
- [x] Routes are unchanged (`/base/index`, `/videos/`, `/records/` and their shared and friends' pages); `shelf_url(type, scope, username)` (app.py) builds the links from `media.SHELF_ENDPOINTS`. `/base/shelves` redirects to the section you used last: every Shelves page sets an HttpOnly `shelf_section` cookie (`remember_shelf_section` in app.py); books the first time or for a bad value. `_media_tabs.html` and the per-section headings are gone.
- [x] The floating `+` on each grid still adds to that section.
- [x] Tests: `test_shelves_one_entry_and_section_switch`.

### 11.2 "Shelves" means where things stand; collections are collections 🟠
Done 2026-11-08.
- [x] **Shelf** = what you own and where it stands: the Shelves pages, "on your shelf" (owned, not removed), the Shelf style.
- [x] **Collection** everywhere else in the UI: the Collections page ("Custom Collections", "New book collection", "No book collections yet"), the delete confirmation, the profile's rows ("Collections"), flashes ("You already have a collection called ..."), account removal's summary, and the data export (`collections.csv`, column `Collection`; was `shelves.csv`). Code keeps `user_collections` and `_shelf_rows.html`. Goodreads' own "shelves" keep their name on the import page (they're Goodreads').

### 11.3 Friends: a page of people, not a shelf tab 🟠
Done 2026-11-08 (Phil: put Notifications with its count under "Welcome").
- [x] **Sidebar: Friends** (`friends.index`, `/friends/`, `templates/friends.html`): a card per friend (avatar, name, "4 books · 0 movies · 0 albums", each count opening that section of their shelves; the name opens their books) and a link to their profile. A line links to Notifications when friend requests wait. **Find friends** moved here from the profile (`static/friends.js`, out of `user.js`); the profile's Friends block keeps its avatars and links here.
- [x] **Shelves scope tabs are Mine | Household.** `base.friends_libraries`, `videos.friends` and `records.friends` redirect to `/friends/`; their templates are gone; `media.SHELF_ENDPOINTS` has no `friends`.
- [x] **A friend's shelves:** crumbs Friends / *name*, "*name*'s Shelves", the section switch (`shelf_header(type, 'friend', username)`), then the grid. The sidebar marks Friends there, not Shelves.
- [x] **Notifications** left the nav list: a link under "Welcome, *name*!" with the number waiting (friend requests, household invites, unread; `utils/notifications.unread_counts`, also behind `friends.notification_count`).
- [x] 2026-11-08: the friend's **book** page is the regular grid now (`base.library_page`, shared with your Library and the household's): search, filters, sort, list view. Phil: filters and sorts apply to the entries in view, so on a friend's shelf (books, movies, music) status, rating and tag filters, the date read and rating sorts, and list view's columns are **the friend's**; your own and the household's stay yours. The page names them ("Search carol's 136 books", "carol's rating") and links their profile and wishlist.
- Access unchanged: friends only (`is_friends_with`).

### 11.4 More sort options 🟢
Done 2026-11-08 (Phil asked for sort by date read, and others).
- [x] One helper, `utils/sorting.py` (`choice`, `order_by`), for every grid: Library, Household, search, Movies, Music, friends' movies and music, and the collection pages (which showed the menu but ignored it; their default stays "Date added here", newest first). The menu (`_view_bar.html`) is built from `sorting.BY_TYPE` (template global `SORT_OPTIONS`), so it can't offer what the route refuses.
- [x] New: **Date read / watched / listened to** (your latest finished session), **Your rating**, **Pages** (books; audiobooks and unknown counts last), alongside Title, Author/Director/Artist, Year, Date added and Length. Always in the menu, not only with the Read filter on.
- [x] Every order puts empty values last either way (`NULLS LAST`), then ties by title and id, so infinite scroll never repeats or skips. Title and author sort case-insensitively everywhere now (the book pages didn't).
- [x] Date read and rating are the viewer's own, also on household and friends' pages. Tests: `tests/test_sorting.py`.

### 11.5 Sidebar after 11 and 13 🟢
- [x] 2026-11-08: on a short screen (`max-height: 760px`, styles.css "Sidebar on a short screen") the avatar shrinks and link rows tighten, so the 8 entries, Mode and Log out fit a 375x667 phone, and "Do I Have This?" stays on one line.
- [x] 2026-11-09, with Reviews (Phase 13): measured at 375x667, Reviews made an admin's Log out end 33px below the fold. Phil's fix: icons instead of entries: Notifications (bell, with the waiting count) at the end of the welcome line, then under it Admin Settings (gear, admins only) and a Light/Dark toggle (sun/moon; `data-mode-toggle` in `sidebar.js`, the icon follows the mode in effect in `styles.css` "Sidebar icon row", hidden in Outrun). Notifications, Admin and the Mode buttons left the nav. Nav is now Feed, Shelves, Reviews, Friends, Do I Have This?, Wishlist, Collections, Profile, then Log out, which ends at 595px for everyone. "Follow system" stays at Profile → Appearance.

**Done when:** one Shelves entry reaches all three sections for you and your household; friends are people on their own page, each opening their shelves; no page says "shelf" for a collection.

---

## Phase 12: Profile and stats

From Phil, 2026-11-08. The profile page (`templates/user.html`, `blueprints/user.py`) has grown section by section; make it hang together.

### 12.1 Stats: the same tabs for every type 🟠
Done 2026-11-08.
- [x] Two levels: **Overview | Insights** on top, then **Books | Movies | Music** (only the types the user has; books always). `templates/_profile_stats.html`; all panels are in the page and `showStats()` in `user.js` shows one (`hidden`, so screen readers agree). The Library tab is gone; its numbers are in Overview.
- [x] One function for every type, `utils/stats.py` `type_stats(conn, user, kind)` (replaces `calculate_user_stats`, `calculate_library_stats`, `calculate_media_stats`). Overview: owned, finished, finished this year, want to, pages or hours finished and on the shelf, share of the shelf finished, average rating, reviews, creators on the shelf, not owned (when any), longest on the shelf, most common genre, the per-month chart (`stats.by_month`, any type now) and formats. Insights: top genres and creators (of what you finished), your ratings 5 to 1 as bars, collections, the shelf by decade.
- [x] **"See the books"** like the other two, on both levels; on a friend's profile it opens their shelves.
- [ ] **All media** (a fourth choice, or the top of Overview): with 12.2.

### 12.2 More stats across all media 🟢
Done 2026-11-08 (Phil: compact, UI forward).
- [x] An **All** tab, first in the type switch when there's more than one type (`stats.all_stats`). Overview: owned, finished, finished this year, average rating (each with its split by type), time spent (pages read, hours watched, hours listened to), and **Year by year**.
- [x] **Year by year** (`stats.year_by_year`): a row per year, newest first, the counts by type as text and a bar split by type on one scale, the reading goal as a tick ("goal 30, met"). Past years' goals live here now. A run of empty years is one row. With books only it sits on the Books tab.
- [x] Insights: creators you return to (with their types), top genres, ratings 5 to 1, firsts (logging since, oldest on the shelf, added this year).
- Not done, if wanted later: month-by-month across types, collection growth per month.

### 12.3 Reading goal under the bio 🟢
Done 2026-11-08.
- [x] **Goals per year** (migration 029, `reading_goals (user_id, year, goal)`): the old `users.reading_goal` became this year's row (the column stays, unused). Setting the goal sets this year's row; 0 clears it; past years are never touched (`user.update_reading_goal`).
- [x] **Under the bio** (`templates/_reading_goal.html`): "2026 goal: 12 of 30 books", a thin bar, "Change goal" (a `<details>` with the number field, no script). No goal: "Set a reading goal for 2026" on your own profile; friends see the goal and past years, or nothing.
- [x] **Past years** moved to the stats card's Year by year (12.2, Phil); under the bio is this year's goal only.
- [x] **What counts:** books with a session finished in that year, each once per year (a re-read counts in each year). A book marked Read with no date counts nowhere, so **marking Read / Watched / Listened now opens the review page with the session form open and today as the finished date** (`?finished=1`; an open session is finished instead of adding one; nothing is offered if one already finished today). Save keeps it; clear the date for an old read.
- [x] Export: `reading_goals.csv` (year, goal); `profile.csv` lost its Reading Goal column.
- Books only, as before; goals for movies and music can come later.

### 12.4 Appearance: its own card, and no System button 🟢
Done 2026-11-08.
- [x] Appearance (Style, Mode, Font, Accent) left Settings for its own card under the profile header: a `<details class="appearance-card">`, closed by default.
- [x] **Mode: Light | Dark.** `system` stays the stored default; while following it, the button for the mode in effect shows pressed and changes with the device (`syncModeButtons` in `sidebar.js`). Choosing one stores it, and a **Follow system** link (`_follow_system.html`) appears to go back; CSS hides it while following. The link is on Profile → Appearance only (Phil); the sidebar has just Light | Dark. No migration.

**Done when:** every type's stats look alike and link to their grid, the goal and appearance no longer take a card each in the middle of the page, and Mode is two buttons.

---

## Phase 13: Reviews section

From Phil, 2026-11-08: reviews and not-owned items already exist (`read_data`, 8B.3), so give reviews their own visible entry. Done 2026-11-09.
- [x] **Sidebar: Reviews** (`/reviews/`, `blueprints/reviews.py`, queries in `utils/reviews.py`), after Shelves. Heading, then the Books | Movies | Music switch (`section_switch(..., urls=)` in `_shelves.html`, the Reviews variant of `shelf_url`). Each tab has three rows (`_shelf_rows.html`, which gained stars and a name under each cover, "See all" and an empty line):
  - **Your reviews**, newest first, stars under each cover. read_data has no timestamp, so "newest" is the latest finished date of your sessions on it, then the order reviews were first written (rowid). Marking something finished already dates it today (12.3).
  - **Friends' reviews** (`models.friend_ids`, new: friends only, never household-only members), stars and the friend's name.
  - **Finished, not reviewed yet** (done status, no `read_data` row).
  - **"See all"** (`/reviews/all/<mine|friends|unreviewed>?type=`): review cards with the review text (Read more), "Edit review" or "Write a review". `?by=<friend>` narrows Friends' to one friend (404 unless friends).
- [x] **Floating [+ Review]**: Book | Movie | Album → `/reviews/find?type=&q=`, a plain GET search over the section's view (your shelf, your not-owned and removed items, your household's; never wishlist entries, friends' or strangers' rows), yours first. A result opens `read.rate_review`. Nothing found (or "Not the one?"): **Add it as not owned** opens that type's add page with `?not_owned=1&then=review&title=<search>` (`reviews.then_review_values`): "I don't own this" ticked, the title filled in, and saving lands on the review page.
- [x] Reuse: the review form stays `read.rate_review`; opened from Reviews (`?from=reviews`) its crumb is Reviews and saving returns there. The profile's recent reviews use the same query (which also fixed a re-read book being listed once per session) and have **View all →** to Reviews.
- [x] Tests: `tests/test_reviews.py` (access: stranger and household-only member; each type's rows; newest first; See all and `?by=`; the find scope; the not-owned path for all three types; the profile list). `/reviews/all/<which>` is in `test_every_page_loads`. Media add pages now keep "I don't own this" across a refused submit too.

**Done when:** every review you or a friend wrote is two taps from the sidebar, and reviewing something you don't own is one flow.

---

## Phase 13b: Do I have this? across all three types

From Phil, 2026-11-09: "I searched Orville Peck Pony and it thought I was talking about a book", and the item you scanned or searched for should fill in the add form when you press "Add to wishlist", for whichever media type it is.

**What happens today (reviewed 2026-11-09):** the local check (`utils/have.py`) already searches books, movies and music. The problem is the "Not here" step: for a typed title, `have.add_links` always offers *book* links (Add to wishlist / Add to library), and carries neither the title nor a type. For a non-ISBN barcode it offers four buttons (movie or album, wishlist or shelf) and you pick, though the code is carried. Nothing is looked up online until you reach the add page.

- [ ] 🟠 **Online lookup on "Not here", across all three sources.** Ask Google Books / Open Library, TMDb and Discogs (MusicBrainz as backup) in parallel, through the existing lookup modules and SSRF guard. Load it with a fetch after the page renders (`have.js`), so the local answer stays instant and a slow source can't hold it up. Only on "Not here", never on a hit.
- [ ] 🟠 **"Most likely" ranking.** Score each candidate on how well its title and creator cover the words searched (folded with `search.fold`). "orville peck pony" fits artist + title on a Discogs release far better than any book title. Show the best candidate as the headline with its type badge, then the rest grouped by type, so a wrong guess is one tap from right. Start with a plain, explainable heuristic (word coverage, exact-title bonus, creator match), not a model.
- [ ] 🟠 **Barcodes:** a non-ISBN code asks TMDb/UPCitemdb and Discogs at once and picks whichever recognises it, instead of the four-button choice. Keep the choice as the fallback when neither or both answer.
- [ ] 🟠 **"Add to wishlist" fills the form.** Each candidate links to its type's wishlist add page with the source id (`?isbn=`, TMDb id, `?discogs=` / `?mbid=`, or the barcode). The add page looks that up on load (`add_item.js` already auto-looks-up a carried code: extend it to the other ids), so the form arrives filled in. A text search with no candidates still carries `?title=`.
- [ ] Tests: ranking on fixed fixtures (the Orville Peck case), each type's add link carrying its id, no network on a local hit, and the add page pre-fill per id.

**Worth knowing before starting:**
- Cost: up to three outside calls per "Not here". MusicBrainz is 1 request/s per process and Discogs about 60/min; the lookup modules already throttle and cache (6 h). Fine for one person in a shop, and the "only on Not here" rule keeps it that way.
- Calculated risk: the ranking will sometimes guess wrong (a book and an album with the same name). Showing all three groups, only ordered, is what makes that acceptable.
- Not in scope: auto-adding anything. A lookup only pre-fills; you still press Add.

**Done when:** a search or scan that isn't in the house shows the most likely match first, of the right type, and "Add to wishlist" opens that type's form already filled in.

---

## Phase 14: Bulk edit and granular import

From Phil, 2026-11-08 (was Phase 9, then 13). Its own phase: a whole selection-and-actions UI, not a tweak.
- [ ] **Select mode on the grids** (Shelves in every section, search results, a collection): an Edit / Select toggle; tap covers to select, shift-click for a range, select all (on this filtered view), with a count and a sticky action bar. Works with the keyboard and at phone width.
- [ ] **Bulk actions** on the selection, each one POST with CSRF, ownership checked per item in SQL (owner or admin, as Edit), and a summary ("47 changed, 3 skipped: not yours"):
  - add to / remove from a custom collection (the selection's section);
  - set a status (only statuses valid for each item's type);
  - set genre (the cookbooks case), format, owned / not owned;
  - add or remove a tag;
  - remove from library (deaccession) with one note.
- [ ] Undo, or at least a clear confirmation before anything that isn't easy to reverse.
- [ ] **Granular Goodreads import** (CLAUDE.md, product direction): after parsing, a sortable, filterable grid of the rows with checkboxes and a destination per row (library / wishlist / not owned / skip) and collection mapping, then import only the chosen ones. Reuses the select-mode pieces above. Covers can't come from the export (no URLs); the background cover job (`cover_jobs`) fills them after.
  - **Wishlist rows that Goodreads says you've read** (Phil, 2026-11-08): today the import silently takes the book off your wishlist and marks it Read in your library (`utils/goodreads.py`, `row()`, "moved from your wishlist to your library"). It's the one case where the import changes existing data rather than only filling gaps. In the granular import, show it as its own outcome in the grid and let the row's destination decide (move to library, mark read but keep it wished for, or skip), defaulting to asking.
  - Conflicts in general: the import never overwrites (an existing status, rating or review wins and the row is skipped as "already"). Worth showing those rows in the grid too, so you can see what was skipped and why.

---

## Phase 15: Portfolio: README, showcase site, demo

From Phil, 2026-11-08: for a portfolio, not commercial or public use.

### 15.1 README and screenshots 🟠
- [ ] Retake the README screenshots in every style (Negative Earth, OG, Shelf, Outrun) and both modes, from an **anonymised copy** of the DB (rename other users, clear their emails, bios, avatars and review text), never the live one. Bring the README up to date (sections, Do I Have This?, reviews, styles).

### 15.2 Showcase site spec 🟠 (medium)
- [ ] Write `docs/SHOWCASE-SPEC.md` first; build after it's agreed. A static site (Hugo or Astro, which Phil already uses) showing the project's progress as a **timeline**: a fancy changelog.
  - Sources: the git history, the archived phases and their dates (`docs/ROADMAP-ARCHIVE.md`), `docs/DEVLOG.md`, and before/after screenshots per phase (the 2026-11-02 set, the Phase 0 refresh, styles, sections).
  - A feature tour and a short "how it's built" page (raw SQLite with tracked migrations, CSP with no inline JS, the SSRF guard, the access model, auto-deploy on green CI).
  - Same privacy rule as 15.1: anonymised data only. No tracking scripts, self-hosted fonts, Phil's house style.
  - Where it lives: a subpath or subdomain of philcifone.com; decide in the spec.

### 15.3 Open demo server 🟢 (low)
- [ ] Only if the showcase wants a live link. Best practice for a public demo:
  - a separate instance, user and systemd unit, its own `SECRET_KEY` and DB, no prod secrets (no API keys, or separate rate-limited ones);
  - seeded fake data, reset on a timer (copy a seed DB nightly or hourly);
  - a shared demo login, or per-visitor throwaway accounts that expire; registration, email and password change off;
  - uploads off or tightly capped, outbound lookups off or stubbed, rate limits on;
  - behind the existing reverse proxy, `noindex`, a banner saying data resets.

---

## Parked

Not scheduled; pick up only when Phil asks.
- Outrun: angled card and button corners via `clip-path` (it also clips borders and focus outlines, so draw those inside the shape). Animations: none yet; any added must respect `prefers-reduced-motion`.
- Audiobookshelf integration for audiobooks (CLAUDE.md, product direction).

## Not planned

- **The archive fork** ([FORK-SPEC.md](FORK-SPEC.md)): out of scope (Phil, 2026-11-08). It was Phase 11, parked; the spec stays for the record.
- **Docker** is reference-only, since prod runs gunicorn directly. If it's ever revived: move off `python:3.11-slim-bullseye` (Debian 11 is EOL), add a non-root `USER`, drop `gcc`, use `--log-level info`, and the consolidated schema from Phase 2.1.
