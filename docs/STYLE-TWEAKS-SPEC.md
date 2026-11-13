# Style pass spec (ROADMAP 16.0)

Approved by Phil 2026-11-12. Source brief: Phil's [STYLE-TWEAKS-BRIEF.md](STYLE-TWEAKS-BRIEF.md) (2026-11-12; `style-tweaks.md` at the repo root until 2026-11-13). Built on branch `phase-16-style-pass`, one commit per step (section 10).

## 0. Context

Phil's brief ([STYLE-TWEAKS-BRIEF.md](STYLE-TWEAKS-BRIEF.md), 2026-11-12): the styles look right overall, but small inconsistencies crept in while tools were added (crop, bulk edit, Goodreads, Movies & TV). This pass is mostly an **audit**: find the inconsistencies, fix them in small tweaks, and refactor the CSS and markup so **one change to one element updates it everywhere** in a style (bookcase, shelf grid, placeholder covers, cover box). There are no overhauls and no new hover, glow or animation effects. It is ROADMAP 16.0 "Final layout pass", the step before the portfolio screenshots. Most notes are about the Shelf style; Phil is still checking the other styles.

**On the word "refactor":** that is the right term. What you describe is a refactor (restructuring without changing how anything looks or behaves), aimed at a *single source of truth*: shared **design tokens** (CSS variables) and shared **components** (one Jinja macro / one JS helper per element). The one thing to watch: a refactor step must show no visual change on its own. Visual changes come in their own steps afterwards, so each one is easy to review.

**Decisions so far (Phil, 2026-11-12):**
- The "rounded / themed cards" Appearance toggle is **dropped for now**. Settle the bookcase rule first; revisit only if the rule doesn't fix the "which card gets a case" problem.
- **Collections (Shelf style):** the whole page is one bookcase. Each collection is a shelf whose covers scroll sideways (the same treatment as Reviews).
- **Wishlist and a friend's wishlist (Shelf style):** ~~the same as Collections~~. Changed 2026-11-13 (Phil): "laid out exactly like the main page shelves, not these taller shelves": each section is the library's bookcase grid, covers only (title and author for screen readers), with a round (+) on each cover's top-left corner that adds it to your shelf. The note and Remove are on the item page (`book_detail.html` ~L148-200).
- **Do I Have This?:** its results get the bookcase wrap.
- **Profile rows** (2026-11-13, after Phil saw Reviews): the profile's Collections and Wishlist rows are each one `.shelf-case`, like the Collections page.

One commit per step on `phase-16-style-pass`. Phil reviews and merges; Claude does not push.

## 1. The bookcase rule (Phil asked for UI input)

Rule of thumb: **if you'd put it on a shelf, it's in a case; if you'd use it, it's paper.**

| Kind of card | Shelf treatment | Examples |
|---|---|---|
| Page heading | small bookcase (`.page-heading`, already) | every `page_heading`, plus new: Add page, item title |
| Covers on display, many items | covers stand on ledges in a case: a grid, or stacked sideways-scrolling shelves | library grids (already); stacked shelves: Reviews, Collections, Wishlist; Do I Have This? results |
| A card about one item or one person | small bookcase (`.case-card`) with its cover/avatar on the ledge | feed, notifications, item details and reviews (already), Friends cards (new) |
| Tools and text | plain paper card, never a case | forms, lookups, search, filters, tab bars, settings, stats, empty states, the profile header |

Every place the rule says "case" gets one; the profile rows were the last (step 7).

## 2. Refactor: one source per element (no visual change)

- **Shelf lighting tokens.** The grid (`styles.css` ~L1348) and the small case (~L1752) each hard-code the lamp: wall shade .12, top-face shade .16, lit arris .2, front shade .2, inset case shade. These move to one set of tokens on `:root[data-style="shelf"]`, used by both, plus `.shelf-row`'s ledge (`--ledge-paint`). The rack keeps overriding them as it does now.
- **One cover component.** Today 11 templates hand-write `<span class="cover-box"><img …></span>`, as do `common.js` and `script.js`. New macro `cover(src, alt, class)` in `templates/_covers.html`, with `_no_cover.html` kept as its fallback, and a `coverBoxHtml()` twin in `common.js` beside `noCoverHtml()`. The macro also adds one empty `<span class="cover-sheen" aria-hidden="true">`. That free layer is what the glare (section 6) needs, because the box's `::before` and `::after` are already the side and top faces. Form previews and admin pages stay unwrapped, as now.
- **Heading text token** (moved to step 3 when built): a blanket `.font-display` colour would override headings that inherit `text-on-accent` (the "You own this" banner), so it's Shelf-only and targets `.font-display.text-content-primary` and `.no-cover` (`--heading-ink`).
- Raw Tailwind colours (`border-gray-700`, `bg-orange-600`, `text-white` …) are already re-pointed at tokens in `tailwind.config.js`, so they theme correctly. I only switch them to the semantic names (`border-rule`, `text-content-primary`) where a step already touches that markup. No sweep.

## 3. Shelf: colour and light

- Headings and placeholder titles (built): light mode walnut `92 62 38` (#5c3e26), since Shelf's ink was already a brown-black (#2b2118) and a smaller step wouldn't show; 9.1:1 on surface, 6.5:1 on the bookcase's back wall. Dark mode a warmer cream `245 232 206` (#f5e8ce; the ink was #f2e7d4), 10.9:1 or more.
- A subtle contact shadow on the shelf's top face under each box, falling slightly right to match the lamp (above-left). The existing cast shadow behind (`--box-cast`) stays. This is one token, `--box-contact`, so the grid, rows, cards and item page all change together. The grid's own value is tuned to its depth.

## 4. Shelf: page changes

- **Tabs (profile Overview / Stats / Reviews, and every `.tab` in Shelf for consistency).** Today an accent underline marks the active tab, and the open-bottomed tab beside it looks like the one joined to the panel below. Shelf's version: the active tab is raised paper with accent text and bold, no underline. Inactive tabs are recessed (`--fill` plus a soft inset shade along the bottom). Other styles are unchanged. Built: the recessed shade is a token per mode (`--tab-recess`; in dark mode `--fill` is the lighter one), and the Add page's lookup tabs (`.search-method-btn`) follow the same rule.
- **Add page:** the heading moves out of the lookup card into `page_heading('plus', heading)` above it (every style, so it matches every other page; the case comes from `.page-heading`). Crumbs stay above. Built: Edit Book and Edit Movie / Album moved the same way (they share the form, and would otherwise be the odd ones out). The icon is the section's (`section_icons` in `_icons.html`), the bookmark on the wishlist's Add.
- **Item details:** the title, subtitle, "by" line and format icon move out of the details card into a heading card above it. The new macro `item_heading(...)` in `_icons.html` uses the `.page-heading` class, so Shelf wraps it in a case (every style gets the heading card, like every other page). The details card keeps the cover and everything below it. Built with `heading_card()`, the card that `page_heading` now also uses, so every heading card has one source.
- **Activity feed card:** the cover sits at the bottom of the card so it stands on the ledge. The details column has the activity line first, then the title. The like button moves into the layout: a footer row in the details column, clear of the ledge with real bottom padding, so it is no longer pinned in the corner. That also does 16.0's "give them a place in the layout" item. The dismiss X stays top right. `pb-16` goes once nothing needs it. Built as a small grid (`.feed-row`, every style): desktop has the cover on the left and the activity and then the like row beside it; a phone has the activity full width, then the cover and the like row side by side (beside the cover the text had ~150px, a word a line). The four activity types share one structure now (they were four copies).
- **Reviews:** the section becomes one bookcase whose shelves are the existing rows (your reviews, friends', not yet reviewed). Each row's label, count and See all sit on the back wall, and its covers stand on a full-width ledge with the sideways scroll unchanged. This is a `cased` option on `_shelf_rows.html` (drops the row's `bg-primary` panel so the wall shows). It is the one "stacked shelves" component that the next three bullets reuse. Built: the page puts `shelf-case` on the element round `_shelf_rows.html` (no flag in the partial); the covers' one height (`h-28`) puts the ledge at a fixed depth (`--shelf-y`), painted with `background-attachment: local` so it runs the whole scroll width; an empty shelf is a bare ledge. Other styles: pixel-identical.
- **Collections** (built): one case holding the status shelves and then the custom collections (their headings on the back wall), a shelf per row in Shelf; "New collection" (the create form) is its own paper card below, in every style. The button says "Create collection" (it said "Create Shelf"; in the UI a shelf is what you own). The Goodreads shelves card stays paper.
- **Wishlist and a friend's wishlist** (built in step 7): ~~stacked rows~~; each section (Books, Movies & TV, Music) is the library grid's bookcase. One markup for every style, since the cycler switches styles without a reload: `_wishlist_card.html` is shared by both pages and carries the grid's hooks (`book-item`, `book-cover`, `book-link`, `book-info`) inside a `.wishlist-grid.shelf-grid` per section, so the grid's rules draw it as they are. Shelf drops the card's chrome and its button for a round (+) on the cover's corner (`.wishlist-quick-add`, the same POST as the button, with a confirm, named "Add <title> to your <shelf>" for screen readers). House, OG and Outrun keep the cards, unchanged pixel for pixel. A friend's wishlist now uses the same card (it had its own copy) with `page_heading`, sections per type and the item page's shop searches (`media.buy_links`) in place of the hard-coded ThriftBooks / Bookshop pair. The Music grid takes the album shelf height (`:is(#book-container, .wishlist-grid)`), and the Movies rack easter egg is scoped to `#book-container` so it stays on the library.
- **Stacked shelves, fixes (step 7):** no rubber-band at either end of a row (`overscroll-behavior-x: none`, plus the ledge drawn a second time fixed to the row for a browser that bounces anyway), ~~and a plank under each case heading~~ (dropped in 7d: Phil, "it doubled up"; the profile's headings stand above their bookcases (`.case-wrap` drops the paper card in Shelf), and Collections has no visible headings inside its case, screen-reader headings only). The stacked-shelf case has no framed bottom: its last ledge is the bottom, as on the grid (a frame just under it read as a second shelf); Collections' "no collections" note gets a bare ledge under it so the case still ends on a shelf. The case has the inside of its left panel (a strip down its side, as the small cases have), and every ledge, the heading planks included, runs back into it on the 1:2 slant; the row (the scroller) starts at the panel's inner face, so covers scroll behind the board in every browser, and the strip's slice of each ledge is `.shelf-row::after`, positioned outside the scroller (painting it over the covers failed in iPhone Safari). On the wishlist grid a coverless item gets an explicit width: iPhone Safari gave the nested placeholder none (only its spine showed).
- **Do I Have This?** (`have.html`): each match is a card about one item, so it becomes a `.case-card` with its cover standing on the ledge and the details beside it (audit F8). The "You own this" banner and the search card stay paper.
- **Friends page:** each friend card is a `.case-card`.

## 5. Friends and profile (behaviour changes the brief asks for, every style)

- **Friends page card:** the avatar and name open the friend's **profile**. The bottom link reads **"See their shelf"** and opens their shelves. The books / movies / music counts become plain text, with no links.
- **Sidebar:** Friends is the active nav item on a friend's profile too, since that is where its cards now lead (`on_friend` in `_sidebar.html`).
- **Profile header, actions:** the orange icon button (on a phone just "Remove") and the outline "Remove Friend" are replaced by plain outline buttons that say exactly what they do: **"Remove from your household"** (household owner), **"Leave household"**, **"Unfriend"**. Each confirm names the consequence (for example "Unfriend bob? You'll stop seeing each other's shelves, reviews and feed. Your books aren't touched."). They sit together in one row at the bottom of the header, with the danger colour only on hover. No icon-only or shortened labels.
- **Friend at a glance:** a line of facts under the name on a friend's profile:
  - "In your household" when that applies (`in_shared_library`).
  - "N books in common": books only, on both shelves (`book_utils.on_shelf()`), matched with `utils.book_matching.BookIndex` (ISBN, then title and author), never against all of `books`. A new helper in `utils/` with a test.
  - Their reading goal: `_reading_goal.html` already shows it to friends, so check it shows and keep it on this line.

## 6. Glare on covers (Shelf)

- **Static glare, step one:** the rental-case sheen (`--case-sheen`, ~L2184) on every cover via the new `.cover-sheen` layer, at a lower alpha for paper covers than for the plastic case. It doesn't move or animate.
- **Your accelerometer question:** yes, it's possible. `DeviceOrientationEvent` gives the phone's tilt. Android Chrome and Firefox send it on HTTPS with no prompt. iPhone Safari needs `DeviceOrientationEvent.requestPermission()` called from a tap, so iPhone users would need a one-time "Tilt glare" switch, in Appearance or on the Shelf page. The build would be one small self-hosted script (CSP-safe), loaded only in the Shelf style. It throttles to `requestAnimationFrame` and sets `--tilt-x` / `--tilt-y` on `<html>`, and the sheen's `background-position` reads them. It stays off under `prefers-reduced-motion`. It costs no noticeable battery and needs no server change. My recommendation: ship the static glare, look at it for a few days, and only then build the tilt as its own step. It is the only motion in the phase, so it waits for your go.

## 7. Wording (low priority, last)

Shorter, still warm help text and confirm messages, with the same information. As a list of before → after per page in the step's commit, for Phil to veto line by line.

## 8. The audit (the main goal)

- **Screenshots I can look at myself:** a throwaway Playwright harness in the scratchpad (not committed, not added to requirements), run against the dev server on a copy of the DB. It logs in as two seeded users who are friends and share a household. It visits every GET page (the same list as `test_every_page_loads`) in house / classic / outrun (dark only) / shelf × light / dark × 390px and 1280px widths, and saves contact sheets. Each step's before/after is compared on those sheets.
- **A findings table in the spec:** page × style, what's off, and the decision. Consistency findings are fixed without asking (Phil, 2026-11-13); only a merge that would change a look elsewhere goes to Phil. The table is filled in during step 1 and kept up to date.

---

## 9. Findings (filled in by step 1, kept current)

Audit of 2026-11-12: 32 pages × 7 style/mode pairs × phone and desktop, on a copy of the dev DB with real cover files mapped in (the dev DB's own covers aren't on disk). The harness and contact sheets are in the session scratchpad, not the repo.

| # | Page | Where | What's off | Decision |
|---|---|---|---|---|
| F1 | Add (every type) | all styles | "Add a Book" heading sits inside the form card, under the lookup card | brief: step 4 |
| F2 | Item page | all styles | title, subtitle and "by" are inside the details card | brief: step 4 |
| F3 | Friend's profile | all styles | orange filled "× Remove from Household" (phone: just "Remove") stacked over an outline "Remove Friend": two danger actions, different weights, unclear targets | brief: step 8 |
| F4 | Profile tabs, every `.tab` bar | Shelf | the active underline makes the open-bottomed neighbour read as the joined tab | brief: step 4 |
| F5 | Feed | Shelf, worst on phone | cover top-aligned, so it floats above the ledge; text column squeezed by the dismiss X's `pr-6`; large empty band above the ledge (`pb-16`) | brief: step 5 |
| F6 | Reviews, Collections, profile rows | Shelf | the ledge runs under the star and name captions, not under the covers, so the books don't stand on it | step 6: cased rows put the ledge right under the covers (one row height, `h-28`, makes that a fixed offset); captions hang below the ledge like the grid's badges |
| F7 | Wishlist | Shelf | full paper cards with boxed covers floating inside | brief: step 7 |
| F8 | Do I Have This? matches | Shelf | plain paper cards, cover top-aligned | step 7: each match is a `.case-card` with its cover standing on the ledge; the "You own this" banner stays paper (it's text) |
| F9 | Notifications, empty | Shelf | the empty "No recent notifications" panel is a case with nothing on its shelf (inconsistent with the rule, not broken) | Moot (2026-11-13): notifications are the rounded Reviews cards again, no case |
| F10 | Collection status page ("Read"), Reviews "See all" | all styles | plain `<h1>`, not `page_heading`, so no heading card (and no case in Shelf), unlike every other page | On hold: touches headings, which Phil may undo app-wide (2026-11-13) |
| F11 | Search results | all styles | the search bar sits above the crumbs, and the page has no heading; every other drill-down page starts with crumbs | Done (2026-11-13): crumbs first, then the search bar |
| F12 | Settings | all styles | heading card is 7xl wide, the tabs and panels under it 4xl, so the heading overhangs | On hold: touches headings (see F10) |
| F13 | Feed | all styles | timestamps raw (`2026-11-13 04:15:19`), unlike the dates elsewhere | Done (2026-11-13): the date only (`YYYY-MM-DD`), as on the Reviews cards |
| F14 | Profile, Notifications, Have, Friends | all styles | page widths differ (3xl / 4xl / 7xl), the "4xl / 7xl mix" 16.0 mentions | Wide pages done in step 7d: one `.page-frame` (7xl, 16px / 24px / 32px gutter) for every wide page; the library grid had Tailwind's `container` (other widths per breakpoint) and six pages (Shelves, Household, a friend's, Movies/Music grids, Friends, Feed) had `p-6` on `<body>`, 24px further in than the rest; Shelf cases keep their right face inside the frame, as the grid does (Phil, 2026-11-13: the wishlist grid on an iPhone is the reference). Rest done in step 10 (2026-11-13, Phil: "do the page widths"): two frames, one per page, the same gutters: `.page-frame` (7xl) for grids and two-column pages (Rate & Review moved up from 6xl to match the item page), `.page-frame-narrow` (4xl) for one column (profile, notifications, add / edit / Goodreads forms, Do I Have This? and Find from 3xl, admin pages from 5xl); every page checked in `test_every_page_loads`. A heading inside its page's frame follows it. Settings' 7xl heading over 4xl panes stays until the heading decision (F12) |
| F15 | Profile | all styles | no page heading card; "Carol's Profile" is inside the header card | On hold: touches headings (see F10) |
| F16 | Reviews "See all" cards | Shelf | each card is about one item with a cover, so the rule says case-card | Dropped (2026-11-13): Phil is using the bookcase on fewer cards, and the feed now copies these |
| F17 | Sidebar | all styles, phone height | avatar 2px under the top bar and the column ending up to 170px short of the drawer's bottom: the short-screen rules (11.5, `max-height: 760px`) were sized when the nav had more entries | Done (2026-11-13, Phil: "more padding between avatar and top bar"): the avatar clears the bar by 20px; the link rows are fluid with the height (`--side-row`), so the column ends about 20px above the bottom; breakpoint 800px, since the tall layout needs 770 |
| F18 | Notifications | all styles | the card under the page heading had its own "Recent Activity" heading and bell, repeating the page's | Done (2026-11-13, Phil): no heading in the card (`aria-label` for screen readers); Mark all as read sits at its top right |

Decided 2026-11-13 (Phil): consistency calls across pages and styles are Claude's to make, so every finding above is scheduled, none is waiting on Phil. Ask only when unifying two similar things would change how something already looks elsewhere.

The feed card's phone layout: done (Phil, 2026-11-13: "we fixed but didn't tick"); the card is the Reviews list's card on every width.

The profile's Collections and Wishlist rows: done in step 7, each one `.shelf-case`.

## 10. Execution steps (one commit each)

0. Branch, write `docs/STYLE-TWEAKS-SPEC.md` (the spec above), and point ROADMAP 16.0 at it.
1. Screenshot harness plus the full audit pass: fill the findings table. No code changes.
2. Refactor: Shelf lighting tokens, `cover()` macro and `coverBoxHtml()`, heading-ink tokens. Screenshots must match step 1's, pixel for pixel or close to it.
3. Shelf colour and light (section 3).
4. Shelf tabs, Add page heading, item heading (section 4, first three).
5. Feed card layout (section 4).
6. Stacked shelves: `cased` rows with per-cover links, then Reviews and Collections.
7. Wishlist (yours and a friend's) as the library's bookcase grid with the (+) quick add; the profile's rows cased; Do I Have This? results in a case. Done (7a-7f): each match is a `.case-card` with its cover on the ledge, through `.case-cover`, the hook the feed's cover now shares; a case that is a link doesn't move on hover in Shelf.
Taste pass (Phil, 2026-11-13): the bookcases are being used more sparingly. The feed and notification cards went back from `.case-card` to the rounded card the Reviews lists use (`bg-secondary rounded-lg card`). **Open question for Phil, don't act yet:** the heading cards (`heading_card` / `page_heading`, steps 3-4) may be undone; he is sleeping on it. Leave every heading as it is until he decides. Same pass: the item page's body cards and the Friends cards are plain cards again (headings keep their case); the feed's card is now the Reviews list's card itself (cover left, title, creator, one line of rating / who / when, the review with Read more, then the like), two columns on desktop like Reviews; Do I Have This? keeps its cases with gap-6 between cover and text.

The item page's details card is an ID badge at every width (Phil, same day): the cover with the facts beside it, two columns of facts on a phone (codes such as the ISBN span both), the description and the rest under the badge on a phone and beside the cover from md. Desktop is unchanged.

The item page's reading info, condensed (Phil, same day: "I dislike how much I have to scroll"; status and collections could be condensed, tabs like the profile's). On a phone the cover and the facts share one midline. The reading info is one card as wide as the details card, two columns on desktop: on the left the status and the collections as chips (`.chip`, `aria-pressed`) that save on a tap and come back to the card (`anchor=your-info`, `collections._back`, a fixed list), and "+ New collection", which creates one with the item already in it. On the right, tabs for Review, History and Tags (`initTabs`; a session saved or deleted comes back to `#item-history`). Household reviews follow, also full width, two columns of cards on desktop. The page is about a third shorter (2842 to 1918px on a 440px phone, 2362 to 1495px on desktop).

8. Friends page and profile changes, books in common (section 5). Done: Friends cards are `.case-card`s, avatar and name to the profile, "See their shelf", counts as text; Friends lit in the sidebar on anyone else's profile; the profile's actions in one row with full labels (Remove from your household, Leave household, Unfriend, Invite to your household, Join their household, Cancel invite, Accept friend request, Add friend) and consequence confirms; "friend at a glance" under the name (In your household, N books in common via `book_matching.books_in_common`), the reading goal staying under the bio. Also: Do I Have This? album covers are square (a book's 5rem width cap squeezed them, every style).
9. Static cover glare. Done (2026-11-13): `.cover-sheen` in Shelf, a fixed diagonal band (alpha .10 on paper, .16 on cases and sleeves, off on the rental rack, which has its own); its position reads `--sheen-shift`, the hook for step 12.
10. The audit's "fix now" findings.
11. Wording pass.
12. Tilt glare. Done (2026-11-13, Phil's go): `static/tilt.js`; a Tilt Off / On switch in Appearance, Shelf only, saved per device. The band slides up to 30% either way against the pose you hold the phone in (which drifts slowly after you); an iPhone asks permission when you turn it on.

Steps 3 to 11 each end with a fresh screenshot set reviewed against the previous one, `npm run build:css` when classes change, and `pytest`.

## 11. Critical files

- `static/styles.css`: the Shelf blocks (~L224-280 palette, ~L1338-1715 grid, ~L1716-2015 rest of app and boxes, ~L2178 sheen), `.tab` (~L1021).
- `templates/_icons.html` (`page_heading`, new `item_heading`), new `templates/_covers.html`, `_no_cover.html`, `_shelf_rows.html`, `_wishlist_card.html`, `_sidebar.html`.
- Pages: `friends.html`, `user.html`, `activity_feed.html`, `reviews.html`, `collections.html`, `wishlist.html`, `user_wishlist.html`, `have.html`, `add_item.html`, `book_detail.html`, `utils/shelves.py` (wishlist rows), plus every template that now hand-writes `cover-box` (have, rate_review, reviews_list, reviews_find, `_book_grid`, `_shelf_rows`, user, activity_feed).
- `static/common.js` (`coverBoxHtml` beside `noCoverHtml`), `static/script.js`, `static/wishlist.js`.
- `blueprints/friends.py` / `blueprints/user.py` (profile context: books in common), a new helper in `utils/` reusing `utils/book_matching.BookIndex` and `book_utils.on_shelf()`.
- `docs/ARCHITECTURE.md` (covers and placeholders, themes, Shelf bookcases), ROADMAP 16.0.

## 12. Tests and verification

- `pytest` after every step. New tests:
  - the `cover()` macro renders the box and the sheen layer; the placeholder fallback when there's no file;
  - the Friends card links: avatar and name go to the profile, "See their shelf" goes to the shelf, the counts aren't links (assert on hrefs and `data-*` markers, not words);
  - the profile action buttons and confirms per household and friendship case;
  - books in common counts only books on both shelves (alice / carol fixtures), ignores removed and not-owned rows and other media types, and isn't visible to non-friends;
  - the item page and Add page each render one `.page-heading`;
  - in Shelf, Collections, Reviews and Wishlist render the cased rows; wishlist covers link to their items; other styles keep today's wishlist cards;
  - `test_csp.py`, `test_pages.py` and `test_every_rule_in_styles_css_ships_in_output_css` keep passing (no inline JS, every page extends base, every rule ships).
- `npm run build:css` after new classes; `output.css` committed with the step.
- Visual: the harness's before/after sheets per step, every style and mode at both widths. Phil checks over the LAN on the dev server (check for a running one first; otherwise `python3 app.py` bound to 0.0.0.0 with `DATABASE_PATH` on a copy of the DB, and I'll give the port and LAN URL).
- Phil's own measure of done: he stops finding things to tweak. Anything he finds goes into the findings table, not ad hoc.
