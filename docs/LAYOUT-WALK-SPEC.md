# Layout walk spec (ROADMAP 16.0)

Drafted 2026-11-19 from Phil's list of things he found walking the pages; open questions answered by Phil the same day (section 10). This is the first part of ROADMAP 16.0's walk ("walk every page at phone and desktop width in each style; list what's off; fix in one pass"). Build on a new branch `phase-16-layout-walk` off `main` once `phase-16d-lending-abs` is merged, one commit per step (section 9).

## 0. Context

Phil's list (2026-11-19), in his words, then what the code says today:

1. **Shelf: the catalog cabinet on every tab row.** "Use the book catalog tab design (drawers, knobs, etc) on all tabs across application": Reviews and its child pages, Profile, Wishlist, Collections.
2. **Activity feed covers** "still use the boxes and not our updated style we're using in the book grid". "Make test that checks whole app for these?"
3. **Your reviews / Friends' reviews** need a heading and catalog-style tabs.
4. **Reviews and its child pages** need the fixed boxes too; the rate & review page needs a better layout, at least on a phone.
5. **A Cancel button** on add item, edit item, edit review and the like.
6. **Do I Have This?** results: from the Shelf bookcases back to the card the feed and the review lists use.

Screenshots for this draft were taken as `claude` in Shelf at 390 px and 1280 px (the style was set back afterwards). `claude` has little data of its own (one book, no reviews), so the walk in step 7 seeds some first (section 8).

## 1. What changes in the bookcase rule

[STYLE-TWEAKS-SPEC.md](STYLE-TWEAKS-SPEC.md) section 1 set the Shelf rule ("if you'd put it on a shelf, it's in a case; if you'd use it, it's paper"). Two rows of its table change:

| Kind | Was | Now |
|---|---|---|
| Tab bars | plain paper card | the catalog cabinet's drawers (Phil, item 1), on every page-level tab row |
| Do I Have This? results | a small bookcase per match (`.case-card`) | the feed's card (`.feed-card`), as the feed and the review lists are now (Phil, item 6) |

ARCHITECTURE.md and the style-tweaks spec's table get the same change.

## 2. One cover box everywhere (items 2 and 4)

**What's wrong.** In Shelf every cover is a 3D box (`.cover-box`, `_covers.html cover_img`). The grid and the item page draw it per item: a book's top and fore-edge show lined pages, a vinyl sleeve is 1 px card in its cover's edge colour, a DVD is thinner than a VHS, movie and music cases are grey plastic, and an item's top and side photos or placeholders go on the faces. All of that keys on two wrappers only: `.shelf-grid.grid .book-item` and `.cover-stand`, which carry `data-media`, `data-format` and the `--face-top` / `--face-side` style. Every other list calls `cover_img` bare, so it gets the generic grey box with no pages: the feed, the three Reviews lists and their rows, Find something to review, the rate & review page, Do I Have This?, the profile's reviews, Borrowed, and the Collections and Reviews rows (`_shelf_rows.html`).

**The fix.**
- Since 2026-11-19 every display page's `cover_img` already passes `ring=abs_ring(id)` (the Audiobookshelf progress ring), and the Reviews and Collections rows' covers carry their book `id`. `item=` can take over: the ring comes from the item's id, so the calls get one argument instead of two.
- `cover_img` gains an `item=` argument: the row (anything with `media_type`, `format` and `id`). With it, the box itself carries `data-media`, `data-format` and the faces style, so the Shelf rules no longer depend on the wrapper.
- The per-type rules in `styles.css` ("Box faces", the vinyl edge, "book pages", the DVD depth, the plastic colours) move from `:is(.shelf-grid.grid .book-item, .cover-stand)` to the box: `.cover-box[data-media="book"]` and so on. The grid and the item page pass `item=` too, so there's one set of rules, not three. The video-store rack's rental cases keep their own look, as now.
- Faces: the lists' queries return the item id already; the page builds the faces map with `utils/photos.box_faces` for the ids on it, as the grid does. One query per page, not per row.
- `_no_cover.html` (a coverless item) takes the same three attributes, so a placeholder box has pages too.
- `coverBoxHtml()` in `common.js` (the JS twin) gets the same argument, for the grids `script.js` builds.
- The vinyl edge colour (`paintVinylEdge`) is found by `VINYL_COVER` in `common.js`; that selector moves to the box as well.

**The test Phil asked for** (`tests/test_layout.py`):
- Every `cover_img(` call and every `_no_cover.html` include in `templates/` passes `item=`, except an allow-list of the pages that stay flat on purpose (form previews, admin pages). A new list that forgets it fails CI.
- No per-type box rule in `styles.css` keys on `.shelf-grid` or `.cover-stand` any more (a regex over the rules' selectors), so the rules can't drift back to one wrapper.

## 3. The catalog cabinet on every tab row (items 1 and 3)

**Today.** The drawers (brass label holder, cup pull, the open drawer pulled out with a blank card standing in it) are `.cabinet-top .tab` rules, and only `shelf_header` sets `cabinet=True` on `section_switch`. Reviews uses `section_switch` without it; Collections and Wishlist hand-write the same `<nav>` of `.tab` links; Profile, Settings and Admin hand-write `role="tab"` buttons that `initTabs` (common.js) marks with `aria-selected`, not `.tab-active`.

**The fix.**
- One macro for a tab row, `tab_row(tabs, label, cabinet=True)` in `_shelves.html`: links (`href`) or in-page buttons (`controls`), an optional count per tab. `section_switch` becomes a caller of it. Collections, Wishlist, Reviews and its children, Profile, Settings and Admin use it (Settings and Admin too: Phil, 2026-11-19), so a tab row is written once.
- A cabinet that is only a tab row has both ends: the top rail and the plinth on one band (`.cabinet-top.cabinet-end`). Wishlist's filter box under its tabs becomes the cabinet's search band, as on the shelf pages.
- The open-drawer rules match `[aria-selected="true"]` as well as `.tab-active`, so the in-page tabs pull out too.
- Width as on the shelf pages (Phil, 2026-11-19): on a desktop the cabinet is the small piece of furniture, centred (`--cab-w`), because stretched across the page it loses the catalog look; on a phone it's full width, matching the cards under it.
- Other styles: no change; the same markup draws today's tabs.

**Headings (item 3).** Your reviews, Friends' reviews and Finished, not reviewed yet print a plain `<h1>`. They get `page_heading('star', heading)` (the framed heading in Shelf), the crumbs above, then the cabinet. Find something to review gets the same.

**The test.** `tests/test_layout.py`: no template outside `_shelves.html` has a `class="tab` element, so a new hand-built tab row fails (the item page's tabs are allow-listed: they stay as they are, section 10).

## 4. Reviews pages and rate & review (item 4)

Found on the walk, besides the boxes:
- **The Reviews page scrolls sideways on a phone, in every style** (Shelf and Negative Earth at 390 px: the page is 957 px wide). The Friends' reviews row's covers overflow the case (`.shelf-figure` at x = 446 in a 390 px window): the row isn't clipped to scroll inside its shelf as Collections' rows are. Fix it in `_shelf_rows.html` (`min-w-0` on the grid cell, the row's own `overflow-x: auto`), with a test that the row's container has both.
- "Nothing reviewed yet. The + button finds something to review." runs over the case's left side in Shelf: the empty line needs the row's padding.
- Friends' reviews' captions (stars, Phil) sit under the ledge, apart from their covers. They go on the ledge's front, as Collections' captions do (`.shelf-figure figcaption`).

**Rate & review on a phone.** Today the cover fills the whole first screen (300 px wide, full height), then "Rate & Review" repeats the title, then the form. On a phone:
- The cover is small beside the title and author (the review list card's layout: about 6 rem wide, left), so the stars are on the first screen.
- The stars are 44 px tap targets.
- The reading history and the review keep their order; Submit Review and Cancel sit together at the bottom (section 5).
- In Shelf the form is a paper card like the item page's ("Paper cards"), the cover a box with `item=` (section 2).
- Desktop keeps the two columns.

## 5. Cancel (item 5)

Every full-page form gets a Cancel beside its main button: Add (book, movie, album, wishlist entry; `add_item.html`), Edit book (`edit_book.html`), Edit movie / album (`media_form.html`), Rate & review (`rate_review.html`). Step 5 greps for any other full-page form and adds it to this list.
- A plain link (`<a>` styled as the outline button, `btn btn-outline`), not `history.back()`: it works without JS and always lands somewhere predictable.
- Where it goes: the item page for Edit and Review; the crumbs' parent for Add (the shelf or the wishlist it came from; the Reviews page when you came from Reviews).
- No "discard changes?" prompt: nothing is saved until the main button, so leaving loses only what's typed. One exception to say plainly: on Edit, photos and crops save as soon as you make them, so Cancel doesn't undo those. Its `title` says so ("Photos you changed are already saved").
- Order: the main button first, Cancel after it, both centred, as the session form's Save / Cancel already are.
- A test per form that the Cancel link is there and points at the right page (`data-cancel` marker).

## 6. Do I Have This? results (item 6)

Each match becomes the feed's card (`feed-card`, as in `activity_feed.html`): the cover left, the title, the creator, the verdict line in the accent for yours and the household's, "You: read, rated 4/5" under it. The whole card stays one link. The "You own this" banner above stays as it is. `case-card` and `case-cover` go from `have.html`; their CSS stays while the feed's own rules still use them (step 6 checks, and removes what nothing uses).

## 7. Out of scope here

The rest of the 16.0 walk (Notifications, Friends, Settings and Admin spacing, the other styles' details) comes after these steps, as its own findings list in section 8. No new features, no colour changes outside Shelf.

## 8. Findings (filled in by step 7, kept current)

To be filled in by the walk: every page at 390 px and 1280 px, in all five styles and both modes. `claude` is seeded first (a few reviews, an item of each type, a wishlist entry, a friend's review), through the app, not SQL. The walk script (Playwright, scratchpad) also reports any page wider than its window, which found section 4's first item.

## 9. Steps (one commit each)

1. Cover boxes: `cover_img(item=)`, `_no_cover` and `coverBoxHtml`, the CSS moved to the box, every call site, the faces map on the list pages; the test. Done 2026-11-19: `app.py cover_box` (the book id is `book_id` when a row has one; faces read once per page by `box_faces` and kept on `g`, else per cover), the lists' queries gained `format` and `owned`, a page sets `--box-depth` and `--box-thin` and the box takes its own. Kept on the grid's `.book-item`: `data-format`, for the record sizes (layout, not the box).
2. Tab rows: the `tab_row` macro, every page moved to it, the one-band cabinet, `aria-selected`; the test. Done 2026-11-19: also Admin -> Placeholders; tabs are `(key, label[, count])`, links when `urls` is given; `initTabs` finds the tablist inside `[data-tab-row]` and shows the row; the wishlist's filter is a `.cabinet-band`; on a phone drawers shrink, a count goes under its name and a long name wraps (the four-drawer wishlist); `sidebar.js` reloads on a Shelf switch only where the view bar is a cabinet part, not on every tab row. Open: the wishlist filter's placeholder is cut at 390 px. Later the same day, Stats (section 10): `tab_row` gained `action` / `data` (toggle buttons for user.js, `aria-pressed`) and `lower` (a second row of drawers as a band); the drawer rules key on `.cabinet-drawers`, on every tab_row, instead of `.cabinet-top`.
3. Reviews pages: headings, the sideways scroll, the empty line, the captions. Done 2026-11-19: the sideways scroll wasn't the grid cell. The stars' screen-reader text ("Rated 4 of 5", `sr-only`, absolutely placed) had no positioned ancestor inside the row, so it was placed outside the scroller and not clipped by it; the caption's `<figure>` is now `relative`. The empty line takes `.shelf-case-note`. Captions are printed in cream on the ledge's front, which deepens to one or two lines on a captioned row (it redeclares `--ledge-h`, worked out where it's declared; a test checks). The list pages and Review a ... get `page_heading('star', ...)` between the crumbs and the drawers.
4. Rate & review: the phone layout. Done 2026-11-19: one grid with named areas (`styles.css .review-layout`): a 6rem cover beside the title on a phone, the form under both; from md the title across the top, then the cover and the form, as before. Stars are 44 px targets. Also found: a reading session's row made the page 442 px wide at 390; it wraps now, the Started: / Completed: words for screen readers on a phone. Submit and Cancel together: step 5.
5. Cancel buttons and their tests.
6. Do I Have This? cards; unused CSS removed.
7. Walk every page (section 8), list what's off, fix; ARCHITECTURE.md and the style-tweaks spec's rule table; screenshots for Phil.

## 10. Decided (Phil, 2026-11-19)

1. **Which tab rows get drawers:** Reviews and its children, Profile, Wishlist, Collections, and Settings and Admin too. The item page's tabs stay as they are. Stats too (changed later the same day): both its switches, lifted out of the numbers' card into one cabinet, the type's drawers on top and Overview | Insights under them.
2. **The cabinet's width:** centred and narrower on a desktop, like the Shelves page; full width on a phone, matching the other cards.
3. **Cancel on Add:** back where you came from (the shelf, the wishlist, Reviews), since an add doesn't always start from a shelf.
