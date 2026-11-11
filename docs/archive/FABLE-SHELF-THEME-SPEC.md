# Fable Shelf Theme Spec

Status: DRAFT for tightening. Not on the ROADMAP yet; if it goes ahead it becomes a
numbered phase there.

## Goal

Give the Shelf style (`<html data-style="shelf">`, the iBooks-style skeuomorphic
theme, Profile -> Appearance -> Style) one careful pass of polish. It already
works and Phil likes the direction. The job is to find the rough edges and make
the physical metaphor feel more consistent and better lit, not to make it louder.

Reference for the look: `docs/skeuomorphic-inspo.jpg` (the iBooks bookcase). Take
the spirit, not a copy. See the constraints below for what Phil has already
ruled out.

## Constraints (decided by Phil, do not re-litigate)

- **Restraint.** Nothing over the top. A polish pass should be mostly subtle:
  shading, spacing, edge treatment, consistency. If a change would be the first
  thing someone notices on the page, it is probably too much.
- **No wood-grain texture** (dropped 2026-11-08). The flat two-tone ledge line
  is the look; the `--shelf-*` colours are the wood. No images or SVG textures.
- **No hover lift or hover animation on covers** (dropped 2026-11-08). Keyboard
  focus gets a ring round the cover.
- **No title label under covers on the bookcase.** `.book-info` stays visually
  hidden (screen readers still get it). A coverless item has its title printed
  on it.
- **The movie rack stays an easter egg**: off by default, only
  `[data-rack="store"]` rules touch it. Music keeps the wooden bookcase. The
  rack gets its own polish pass, aimed at 90s video-rental nostalgia; see "The
  movie rack" below. It stays unbranded: no store's name, logo, wordmark or
  tagline anywhere. (The 2026-11-08 rule was "generic"; Phil relaxed it on
  2026-11-10 to "evokes the era, names nobody". The app is going on public
  display in ROADMAP 16, so the line stays at the brand itself.)
- **Shelf only.** Do not change House (Negative Earth), OG/Classic or Outrun,
  their palettes, or the shared component classes in a way that shifts them.
  Every new rule is scoped `:root[data-style="shelf"] ...`. After the change,
  compare the other three styles before and after: they must be pixel-identical.
- **Both modes.** Light (parchment and maple) and dark (walnut) both, plus
  "Follow system" (the `prefers-color-scheme` block duplicates the dark tokens).
- **Accents still work.** Shelf keeps House's accents and status colours; the
  accent picker (`data-accent`) and font picker (`data-font`) must still apply.
- **Accessibility.** Text keeps at least 4.5:1 contrast (the top bar is 4.9:1
  cream on `--shelf-bar`; do not lose that). Respect `prefers-reduced-motion`.
- **Phone first-class.** Three shorter books per shelf on phones; check 375 px
  wide as well as desktop. No horizontal page scroll.
- Plain CSS in `static/styles.css`, using the existing tokens (`--shelf-*`,
  `--ledge`, `--ledge-top`, `--sink`, `--box-depth`, `--cover-h`, ...). Add a
  token before adding a magic number. No new dependencies, no CDN, no inline JS
  or inline `<script>` (the CSP blocks it; `tests/test_csp.py` enforces it).
- Project rules in `CLAUDE.md` apply (no emojis in markdown, comments explain
  the why, state-changing routes stay POST, and so on). This task should not
  need any Python or schema change.

## Where to look for rough edges

Candidates, not a checklist. Look at the pages first, keep only what is a real
improvement, and say what was left alone and why.

1. **Light and shade on the bookcase.** Direction and softness of the shadow
   under each cover box, the shadow the ledge casts on the back wall, the
   shelf's front edge highlight, the frame's inner edge. Does the light seem to
   come from one place (above, slightly left)?
2. **The cover box.** Top and right faces: do the shaded faces read well on
   both very light and very dark covers? Seam artefacts where the skewed
   pseudo-elements meet the front face, at odd cover aspect ratios, at 1x and
   2x pixel density.
3. **Coverless items** (`.no-cover` as the box): printing, spacing and contrast
   of title and author, long titles, the record variant.
4. **Records and the rack.** The thinner record box (`--box-depth`), the record
   shelf's column and height maths. (The movie rack has its own section below.)
5. **Chrome.** The wooden top bar, the sidebar drawer's edge, page titles on
   their ledge, the raised buttons and FAB, sunken form fields, the segmented
   Books | Movies | Music switch and the grid/list buttons in the view bar.
6. **Rows and cards.** `.shelf-row` (Collections, profile shelves, wishlist
   rows), `.cover-stand` on the item page, wishlist cards, the feed's covers.
7. **Dialogs and the crop tool.** The Shelf block at the end of the file
   (wooden bar, framed recessed case, round magnifier). Confirm dialog and
   flash messages in Shelf, if they have no Shelf treatment and look out of
   place.
8. **Seams between sections.** Anywhere the metaphor stops: a page with a
   wooden bar but flat House-style cards, mismatched borders, a stray
   Negative Earth hard shadow, inconsistent corner radii.
9. **Small stale item.** The comment in `templates/base.html` (around line 26)
   still mentions tap-once-for-title; that was dropped and `static/shelf.js`
   now only does the rack. Fix the comment while there.

## The movie rack (Phil, 2026-11-10)

The video-store rack (`<html data-rack="store">`, the egg button on the Movies
grid) gets its own polish, with one aim: it should make someone of a certain age
think of a Friday night at a 90s video rental store, without ever naming one.
Same restraint as the rest: a few well-chosen cues beat a theme park.

What exists today (see the "movie rack" block, about lines 1691-1830, and the
archive's 10.1 entry): an all-white wall, white cases with a thin black outline,
a blue and a yellow stripe down the spine, the poster inset, a title printed on
a coverless case.

Ideas to evaluate (pick the few that work, drop the rest):

- **Blue and yellow as the room's colours, not just the spine.** A blue shelf
  edge or header strip under each row, a yellow accent line, instead of
  everything staying white. Keep the colours muted enough that posters still
  lead; check both modes (dark must not glare or turn the blue neon).
- **Shelf-edge label strips.** The thin printed strip along the front of a
  rental shelf, in plain type, as a flat band on the ledge. Decorative only:
  no new data, no real genre labels unless they already exist in the markup.
  If text is used, take it from the existing section name or leave it blank.
- **Case details.** The slight plastic sheen on a clamshell, a faint edge
  highlight, a spine that reads as a spine. Aim for "chunky rental case", not
  "glossy 3D render".
- **Era-appropriate type** for printed titles on coverless cases: a plain
  condensed sans (self-hosted, OFL, in `static/fonts/`; none from a CDN) if one
  already in the repo fits, otherwise leave it.
- **Lighting.** Flat fluorescent store light: even, slightly cool, little
  shadow, in contrast to the warm directional light of the wooden bookcase.
- **Row rhythm.** Real racks have uniform case height and tight spacing; check
  that gaps, case size and the ledge feel like one wall.

Hard limits:

- No store name, logo, wordmark, tagline or recognisable ticket or membership
  card artwork. Colours and general layout cues only. (No "be kind, rewind" or
  other slogans either.)
- Nothing animated. Still off by default; still only `[data-rack="store"]`
  rules; Music and Books grids are untouched.
- Still no external assets: fonts and any image stay in the repo, any SVG or
  texture stays inline in the CSS or tiny and self-hosted, and `tests/test_csp.py`
  must pass.
- Rack text and the focus ring keep the contrast rules above.

## Files in scope

Read these and nothing else unless a task needs it. Line numbers are as of
commit 3d8e51c and will drift; grep for the comment headers.

### Edit

`static/styles.css` (2207 lines; the output is built from this). Read only these
parts:

| Lines | Content |
|---|---|
| 137-275 | Themes: shape tokens per style, including the Shelf shape block (224-272) and the `--shelf-*` tokens |
| 549-600 | Shelf palette (parchment/maple, walnut): neutrals only |
| 635 | One selector in the shared components excluding Shelf; check it when touching shared parts |
| 679-760 | Cards and buttons (shared; the base the Shelf buttons build on) |
| 770-790 | `.shelf-row` base |
| 868-945 | No-cover box, cover skeleton, the rack-toggle button (942) |
| 1182-1260 | Flash messages, dialogs, star rating (for the seams check) |
| 1260-1315 | List view (the bookcase is grid view only; list view in Shelf should still look right) |
| 1315-1580 | **Shelf: the library grid as a bookcase** (ledges, boxes, coverless, focus ring) |
| 1581-1690 | **Shelf: the rest of the app** (top bar, drawer, headings, buttons, fields, rows, cover-stand) |
| 1691-1830 | **Shelf: the movie rack** |
| 1846-1905 | Sidebar icon row and Mode toggle (check in Shelf) |
| 2109-2207 | **Cover crop tool: the Shelf style** |

`templates/` only if markup is genuinely needed (prefer CSS only):
`_book_grid.html` (the `.cover-box` wrapper, `data-media`), `_no_cover.html`,
`_view_bar.html` (grid/list buttons, rack egg), `_sidebar.html` (top bar and
drawer), `_icons.html` (`page_heading`, `section_heading`), `_shelf_rows.html`,
`_wishlist_card.html`, `book_detail.html` (`.cover-stand`, around line 37),
`_cover_crop.html`, `base.html` (the stale comment).

`static/shelf.js` (26 lines, the rack toggle) only if the rack changes.

### Read only, do not change

- `tailwind.config.js` (how Tailwind names map to the CSS variables).
- `static/script.js` around line 483 and `static/common.js` `noCoverHtml()`:
  JS-built cards must keep producing the same markup as the templates
  (`.cover-box`, `.no-cover`). If markup changes, change both.
- `docs/ROADMAP-ARCHIVE.md`, section "10.1 Shelf" (about line 784): what was
  built and every decision above, with dates. Grep for it, do not read the file.
- `docs/skeuomorphic-inspo.jpg`.

### Tests that touch Shelf

- `tests/test_layout.py::test_shelf_style_bookcase` (about line 569) asserts
  exact strings in the bookcase block: `row-gap: var(--shelf-gap)`,
  `--shelf-pitch: calc(var(--cover-h) + var(--ledge) + var(--shelf-gap))`,
  `padding-bottom: var(--ledge)`, `height: var(--cover-h)`, and that
  `--shelf-front: 80 54 34;` appears exactly twice (the dark tokens). Keep the
  ledge gradient and the row heights in whole pixels so the ledges do not drift
  from the rows. If a value has to change, change the test with it and say why.
- `tests/test_csp.py` and `tests/test_pages.py` (no inline JS, pages extend
  `base.html`). Run the whole suite; it takes about a second.

### Out of scope

Everything else: other styles, Python, migrations, other JS, README and
screenshots (a separate ROADMAP item, 16.1).

## How to work

1. **Look first.** Run the app against a copy of the DB, never the live one:
   `cp library.db /tmp/shelf.db && DATABASE_PATH=/tmp/shelf.db python3 app.py`
   (check for a server already running; bind `0.0.0.0` and give Phil the port
   and LAN URL). Set the style to Shelf at Profile -> Appearance. Use a library
   with a good mix: many covers, coverless items, a record (square) shelf, the
   Movies grid with the rack on and off, a short and a long title.
2. **Baseline screenshots** before touching anything: Shelf light and dark,
   desktop (about 1280 px) and phone (375 px), for: Books grid, Music grid,
   Movies grid (rack off and on), an item page, Collections, Wishlist, Profile,
   a form page (edit book), the crop dialog, the sidebar drawer open, and a
   confirm dialog. Keep them outside the repo (scratchpad), anonymised if they
   might be shared.
3. **List findings** short: what looks off, why, the proposed fix, and whether
   it is subtle or noticeable. Drop anything noticeable that is not clearly a
   fix. Then implement.
4. **Rebuild the CSS**: `npm run build:css`. `static/css/output.css` is
   committed and built from `static/styles.css`, so any CSS edit needs it.
5. **Compare** against the baseline in both modes and at both widths, and
   against the other three styles (unchanged).
6. **Run `pytest`.**

## Deliverable

- Changes in `static/styles.css`, the rebuilt `static/css/output.css`, and
  small template edits only where unavoidable.
- A short summary: what changed and why (a sentence each), what was looked at
  and deliberately left alone, and anything that needs a decision from Phil.
- Before/after screenshots of the changed areas.
- Do not commit or push; Phil commits himself. No attribution trailers.

## Acceptance

- Reads as the same theme, only more refined; side by side, nothing jumps out.
- No regressions in House, OG or Outrun; no contrast regressions; no layout
  shift on phone; `pytest` passes.
- Every new colour or size is a token or reuses one, and each non-obvious rule
  has a comment saying why.
