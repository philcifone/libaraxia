# Style pass spec (ROADMAP 16.0)

Approved by Phil 2026-11-12. Source brief: Phil's `style-tweaks.md` (2026-11-12, not committed). Built on branch `phase-16-style-pass`, one commit per step (section 10).

## 0. Context

Phil's brief (`style-tweaks.md`, 2026-11-12): the styles look right overall, but small inconsistencies crept in while tools were added (crop, bulk edit, Goodreads, Movies & TV). This pass is mostly an **audit**: find the inconsistencies, fix them in small tweaks, and refactor the CSS and markup so **one change to one element updates it everywhere** in a style (bookcase, shelf grid, placeholder covers, cover box). There are no overhauls and no new hover, glow or animation effects. It is ROADMAP 16.0 "Final layout pass", the step before the portfolio screenshots. Most notes are about the Shelf style; Phil is still checking the other styles.

**On the word "refactor":** that is the right term. What you describe is a refactor (restructuring without changing how anything looks or behaves), aimed at a *single source of truth*: shared **design tokens** (CSS variables) and shared **components** (one Jinja macro / one JS helper per element). The one thing to watch: a refactor step must show no visual change on its own. Visual changes come in their own steps afterwards, so each one is easy to review.

**Decisions so far (Phil, 2026-11-12):**
- The "rounded / themed cards" Appearance toggle is **dropped for now**. Settle the bookcase rule first; revisit only if the rule doesn't fix the "which card gets a case" problem.
- **Collections (Shelf style):** the whole page is one bookcase. Each collection is a shelf whose covers scroll sideways (the same treatment as Reviews).
- **Wishlist and a friend's wishlist (Shelf style):** the same as Collections. One bookcase, one sideways-scrolling shelf per section (Books, Movies & TV, Music), covers only (title and author for screen readers). The note, Move to shelf and Remove are on the item page, which already has all three (`book_detail.html` ~L148-200).
- **Do I Have This?:** its results get the bookcase wrap.
- **Still unchanged** (notes list): the profile's Collections and Wishlist rows. With the `cased` option they can be switched on later in one word each.

One commit per step on `phase-16-style-pass`. Phil reviews and merges; Claude does not push.

## 1. The bookcase rule (Phil asked for UI input)

Rule of thumb: **if you'd put it on a shelf, it's in a case; if you'd use it, it's paper.**

| Kind of card | Shelf treatment | Examples |
|---|---|---|
| Page heading | small bookcase (`.page-heading`, already) | every `page_heading`, plus new: Add page, item title |
| Covers on display, many items | covers stand on ledges in a case: a grid, or stacked sideways-scrolling shelves | library grids (already); stacked shelves: Reviews, Collections, Wishlist; Do I Have This? results |
| A card about one item or one person | small bookcase (`.case-card`) with its cover/avatar on the ledge | feed, notifications, item details and reviews (already), Friends cards (new) |
| Tools and text | plain paper card, never a case | forms, lookups, search, filters, tab bars, settings, stats, empty states, the profile header |

The only place the rule says "case" that this phase leaves alone is the profile's Collections and Wishlist rows (notes list).

## 2. Refactor: one source per element (no visual change)

- **Shelf lighting tokens.** The grid (`styles.css` ~L1348) and the small case (~L1752) each hard-code the lamp: wall shade .12, top-face shade .16, lit arris .2, front shade .2, inset case shade. These move to one set of tokens on `:root[data-style="shelf"]`, used by both, plus `.shelf-row`'s ledge (`--ledge-paint`). The rack keeps overriding them as it does now.
- **One cover component.** Today 11 templates hand-write `<span class="cover-box"><img …></span>`, as do `common.js` and `script.js`. New macro `cover(src, alt, class)` in `templates/_covers.html`, with `_no_cover.html` kept as its fallback, and a `coverBoxHtml()` twin in `common.js` beside `noCoverHtml()`. The macro also adds one empty `<span class="cover-sheen" aria-hidden="true">`. That free layer is what the glare (section 6) needs, because the box's `::before` and `::after` are already the side and top faces. Form previews and admin pages stay unwrapped, as now.
- **Heading text token** (moved to step 3 when built): a blanket `.font-display` colour would override headings that inherit `text-on-accent` (the "You own this" banner), so it's Shelf-only and targets `.font-display.text-content-primary` and `.no-cover` (`--heading-ink`).
- Raw Tailwind colours (`border-gray-700`, `bg-orange-600`, `text-white` …) are already re-pointed at tokens in `tailwind.config.js`, so they theme correctly. I only switch them to the semantic names (`border-rule`, `text-content-primary`) where a step already touches that markup. No sweep.

## 3. Shelf: colour and light

- Headings and placeholder titles (built): light mode walnut `92 62 38` (#5c3e26), since Shelf's ink was already a brown-black (#2b2118) and a smaller step wouldn't show; 9.1:1 on surface, 6.5:1 on the bookcase's back wall. Dark mode a warmer cream `245 232 206` (#f5e8ce; the ink was #f2e7d4), 10.9:1 or more.
- A subtle contact shadow on the shelf's top face under each box, falling slightly right to match the lamp (above-left). The existing cast shadow behind (`--box-cast`) stays. This is one token, `--box-contact`, so the grid, rows, cards and item page all change together. The grid's own value is tuned to its depth.

## 4. Shelf: page changes

- **Tabs (profile Overview / Stats / Reviews, and every `.tab` in Shelf for consistency).** Today an accent underline marks the active tab, and the open-bottomed tab beside it looks like the one joined to the panel below. Shelf's version: the active tab is raised paper with accent text and bold, no underline. Inactive tabs are recessed (`--fill` plus a soft inset shade along the bottom). Other styles are unchanged.
- **Add page:** the heading moves out of the lookup card into `page_heading('plus', heading)` above it (every style, so it matches every other page; the case comes from `.page-heading`). Crumbs stay above.
- **Item details:** the title, subtitle, "by" line and format icon move out of the details card into a heading card above it. The new macro `item_heading(...)` in `_icons.html` uses the `.page-heading` class, so Shelf wraps it in a case (every style gets the heading card, like every other page). The details card keeps the cover and everything below it.
- **Activity feed card:** the cover sits at the bottom of the card so it stands on the ledge. The details column has the activity line first, then the title. The like button moves into the layout: a footer row in the details column, clear of the ledge with real bottom padding, so it is no longer pinned in the corner. That also does 16.0's "give them a place in the layout" item. The dismiss X stays top right. `pb-16` goes once nothing needs it.
- **Reviews:** the section becomes one bookcase whose shelves are the existing rows (your reviews, friends', not yet reviewed). Each row's label, count and See all sit on the back wall, and its covers stand on a full-width ledge with the sideways scroll unchanged. This is a `cased` option on `_shelf_rows.html` (drops the row's `bg-primary` panel so the wall shows). It is the one "stacked shelves" component that the next three bullets reuse.
- **Collections:** `collections.html` passes `cased` to its rows, so the whole page is one bookcase, a shelf per collection, scrolling sideways. Custom collections keep their delete button beside the label. The Books / Movies / Music tabs and the Goodreads shelves card stay outside the case (tools, so paper).
- **Wishlist and a friend's wishlist** (Shelf only; other styles keep today's cards): one bookcase, a sideways-scrolling shelf per section (Books, Movies & TV, Music). The shelf's label shows the section and count, and the tabs still choose which shelves show. `_shelf_rows.html` needs one addition: an optional per-cover link (`cover.url`), since a wishlist cover opens its item, not the row's page. Today a row is a single link. `wishlist.js`'s filter hides the covers that don't match, and the counts update. The page feeds the rows through `utils/shelves.py` like Collections, not new markup. Simplest build: the page renders the cased rows in Shelf and the cards elsewhere (`data-style` is known server-side), with the filter working on both.
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
- **A findings table in the spec:** page × style, what's off, and the decision. **Fix now** covers blatant theme slips I don't need to ask about: a corner, font, border width or colour that ignores the style's tokens, misaligned or unbalanced padding, a missing `page_heading` or `crumbs`. **Notes for Phil** covers anything else, left unchanged. The table is filled in during step 1 and kept up to date.

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
| F9 | Notifications, empty | Shelf | the empty "No recent notifications" panel is a case with nothing on its shelf | fix now (step 10): the case goes on cards that hold an item, the empty state is paper, per the rule |
| F10 | Collection status page ("Read"), Reviews "See all" | all styles | plain `<h1>`, not `page_heading`, so no heading card (and no case in Shelf), unlike every other page | fix now (step 10) |
| F11 | Search results | all styles | the search bar sits above the crumbs, and the page has no heading; every other drill-down page starts with crumbs | fix now (step 10): crumbs first; heading as the other grids have it |
| F12 | Settings | all styles | heading card is 7xl wide, the tabs and panels under it 4xl, so the heading overhangs | fix now (step 10): one width for the page |
| F13 | Feed | all styles | timestamps raw (`2026-11-13 04:15:19`), unlike the dates elsewhere | note for Phil (wording/format, not style) |
| F14 | Profile, Notifications, Have, Friends | all styles | page widths differ (3xl / 4xl / 7xl), the "4xl / 7xl mix" 16.0 mentions | note for Phil: propose 4xl for single-column pages, 7xl for grids, in step 10 if he agrees |
| F15 | Profile | all styles | no page heading card; "Carol's Profile" is inside the header card | note for Phil (the header card with the avatar works as the heading; a case round it would break the rule's "tools are paper") |
| F16 | Reviews "See all" cards | Shelf | each card is about one item with a cover, so the rule says case-card | note for Phil (page not named in the brief) |

Notes for Phil (seen, not changed this phase):
- Profile: the Collections and Wishlist rows aren't cased yet (one word each with `cased`).
- F13 to F16 above.

## 10. Execution steps (one commit each)

0. Branch, write `docs/STYLE-TWEAKS-SPEC.md` (the spec above), and point ROADMAP 16.0 at it.
1. Screenshot harness plus the full audit pass: fill the findings table. No code changes.
2. Refactor: Shelf lighting tokens, `cover()` macro and `coverBoxHtml()`, heading-ink tokens. Screenshots must match step 1's, pixel for pixel or close to it.
3. Shelf colour and light (section 3).
4. Shelf tabs, Add page heading, item heading (section 4, first three).
5. Feed card layout (section 4).
6. Stacked shelves: `cased` rows with per-cover links, then Reviews and Collections.
7. Wishlist (yours and a friend's) on stacked shelves; Do I Have This? results in a case.
8. Friends page and profile changes, books in common (section 5).
9. Static cover glare.
10. The audit's "fix now" findings.
11. Wording pass.
12. (Gated on Phil) tilt glare.

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
