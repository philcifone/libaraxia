# Photos, condition and value spec (ROADMAP 16.0a)

Status: **built** on branch `phase-16a-photos-value` (2026-11-15), steps 1 to 11, waiting for Phil's test on the dev server. The open questions (section 12) were built with the draft's answers; each is a small change if Phil decides otherwise.

## 0. Context

From Phil, 2026-11-14, notes made while using the app:

- Records especially have more worth photographing than the cover: the back, the art and liner notes, and their condition. Add a back image and a small gallery per item.
- Record each item's condition (grading) and price.
- A "fetch price" from eBay or similar, for a rough value of the collection, with a bulk tool like the cover fetch.

Answered by Phil the same day:

- **Grading:** the standard terms for each type (section 4).
- **Price:** two optional fields, what you paid and what it's worth now.
- **Value sources:** Phil will set up an eBay developer account and Discogs seller settings. The manual steps go in this spec (section 7) and in the README at its pass (16.1).

The app should be feature-complete before the code review (16.0b) and the screenshots (16.1), so this lands between them.

## 1. What changes, in one paragraph

Every item can have a **back** photo and a **gallery** of more photos (a book a **spine** photo too), added and deleted on its edit page and shown on its page through a "More photos" link under the cover. Every item gets a **condition** in its type's standard grades (a record gets two: the record and its sleeve), a **price paid** and a **value**. The value can be typed in, or **fetched**: Discogs' suggested price for a record in its condition, or the median asking price on eBay for a book or a movie with an ISBN or barcode. A bulk **Fetch values** tool does a whole shelf in the background, like Fetch covers, and Stats shows the **collection's value**.

## 2. Data model (migrations 036 to 038)

All on the owner's copy, the `books` row (each user's copy is its own row), except the photos, which get a table.

**036_item_photos.sql**

```sql
CREATE TABLE item_photos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('back', 'spine', 'gallery')),
    path TEXT NOT NULL,              -- 'uploads/photos/...', relative to static/
    caption TEXT,                    -- optional, e.g. "Inner sleeve", "Scuff on side B"
    position INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_item_photos_book ON item_photos(book_id, kind, position);
CREATE UNIQUE INDEX idx_item_photos_one_back ON item_photos(book_id) WHERE kind = 'back';
CREATE UNIQUE INDEX idx_item_photos_one_spine ON item_photos(book_id) WHERE kind = 'spine';
```

**Spine** (Phil, 2026-11-15): books only, one per item, beside the back. Stored now for a later 3D book (cover, spine and back wrapped on a box, the Shelf style's next step); until then it is just another photo in the item page's gallery. A spine is a tall, narrow strip, so `save_photo` keeps its aspect (no crop), and the edit page's thumbnail shows it at full height.

The cover stays where it is (`books.cover_image_url`, crop and all); a photo row is never the cover.

**037_condition_grades.sql**: a lookup table, like `statuses` (CLAUDE.md: lookup tables, not CHECKs), and the condition columns.

```sql
CREATE TABLE condition_grades (
    media_type TEXT NOT NULL REFERENCES media_types(name),
    code TEXT NOT NULL,              -- stored on the item: 'NM', 'VG+', 'fine'
    label TEXT NOT NULL,             -- shown: 'Near Mint (NM or M-)'
    rank INTEGER NOT NULL,           -- best first, for sorting and comparing
    PRIMARY KEY (media_type, code)
);
-- rows: section 4
ALTER TABLE books ADD COLUMN condition TEXT;          -- the item (a record: the vinyl, tape or disc)
ALTER TABLE books ADD COLUMN sleeve_condition TEXT;   -- records only: the sleeve
```

The two columns can't be FKs into a two-column key from `ALTER TABLE ADD COLUMN` with `media_type` alongside, so `utils/condition.py` validates the code against the item's type on save (as `media.py` does for formats), and a test checks the table and `utils/condition.py` agree.

**038_item_value.sql**

```sql
ALTER TABLE books ADD COLUMN price_paid_cents INTEGER;      -- optional
ALTER TABLE books ADD COLUMN value_cents INTEGER;           -- optional
ALTER TABLE books ADD COLUMN value_source TEXT;             -- 'manual', 'discogs', 'ebay'
ALTER TABLE books ADD COLUMN value_note TEXT;               -- e.g. 'median of 23 listings'
ALTER TABLE books ADD COLUMN value_checked_at TIMESTAMP;
ALTER TABLE books ADD COLUMN discogs_release_id INTEGER;    -- records: for price suggestions
```

Money is whole cents in an integer (no float rounding). One currency for the site: `VALUE_CURRENCY` in `.env` (default `USD`); the forms and pages show it, and a fetch in another currency is refused rather than converted (section 6).

`books` keeps its column order: the new columns go on the end (templates read rows positionally, CLAUDE.md). No table rebuild, so the views don't need recreating; check `library_books` etc. still select what the grids need (`SELECT b.*` picks up the new columns, which is fine).

## 3. Photos

**Storage.** `static/uploads/photos/<book_id>/<random>.jpg`. One folder per item keeps cleanup and backups simple. Processing in `utils/image_utils.py`, a new `save_photo(file, book_id)`:

- Pillow: `ImageOps.exif_transpose` (phone photos come in sideways otherwise), then **strip all metadata** (EXIF carries GPS: a photo taken at home would publish where home is), resize to 2000px on the long side (covers stop at 500x1000, too small to read liner notes or see a scuff), save as JPEG quality 85.
- Refuse anything Pillow can't open as an image; the existing upload size limit applies; at most 30 photos per item (enough for a box set; stops a runaway upload).

**The orphan cleanup must know about them.** `find_orphaned_images` lists files under `uploads/` that nothing in the DB points to, and the admin's cleanup deletes them. It has to collect `item_photos.path` alongside covers and avatars, or the first cleanup after this ships deletes everyone's photos. A test covers it (section 11). The cover tools (Fetch covers, placeholder detection) work from `books.cover_image_url` and never see `photos/`.

**Deleting.** A photo row and its file go together, through `delete_image_file` (CLAUDE.md: never `os.remove` a DB path otherwise). Deleting an item: its rows cascade, and the route removes its `photos/<id>/` folder. Merging two items (anywhere `book_matching` merges) moves the photos to the survivor, as it keeps `goodreads_rows`.

**Routes** (`blueprints/photos.py`, `/photos`, `@login_required`, POST-only with CSRF, owner or admin, checked in the SQL):

| Route | Does |
|---|---|
| `POST /photos/<book_id>/back` | add or replace the back (replacing deletes the old file) |
| `POST /photos/<book_id>/spine` | books only: add or replace the spine, as the back |
| `POST /photos/<book_id>/gallery` | add one or more to the gallery (multiple files in one form) |
| `POST /photos/<photo_id>/delete` | delete one, after the page's confirm |
| `POST /photos/<photo_id>/caption` | set or clear a caption |
| `POST /photos/<book_id>/order` | the gallery's order (later, if wanted: section 9) |

JSON answers in the house shape (`{"success": ..., "error": ...}`), and each works as a plain form post too (redirect back to the edit page's `#photos`) so it doesn't need JS.

**Edit page.** A **Photos** section under the cover fields, on the edit page of every type:

- **Cover**: as today (upload, find a better cover, crop).
- **Back**: its thumbnail, or an **Add back** button; with one, **Replace** and **Delete**.
- **Spine** (books only): the same as the back.
- **Gallery**: thumbnails in a row that wraps, each with a delete button and its caption; **Add photos** opens the file picker (several at once; on a phone, the camera or the library). Uploads go one by one with a progress line, so a phone on a slow connection isn't one long wait.
- Every delete asks first (`data-confirm`, the styled dialog): "Delete this photo? It can't be undone." No placeholders where there's no photo, as Phil asked: just the Add buttons.

The Add page doesn't get this: photos come after the item exists (the form already has a cover; the back, spine and gallery wait for the edit page). "Saved. Add photos?" in the flash after adding an item links straight there.

**Item page.** Under the cover, only when the item has a back, a spine or gallery photos: **More photos (n)**. It opens the cover-zoom dialog (16.0) as a small gallery: the cover first, then the back, then the spine, then the gallery, one at a time, the same size as the zoomed cover, with:

- previous / next buttons either side, and the arrow keys; a swipe on a phone;
- a caption line under the photo when it has one, and "3 of 9";
- tap the photo, Esc, or the close button to go back, as with the cover.

Anyone who can see the item (`can_view_book`) sees its photos: they show the copy, like the cover.

## 4. Condition

The standard terms by type, best first. Stored as the code, shown as the label.

**Records** (the Goldmine scale, as Discogs uses it). Two fields: **Record** (the vinyl, tape or disc) and **Sleeve**.

| Code | Label |
|---|---|
| M | Mint (M) |
| NM | Near Mint (NM or M-) |
| VG+ | Very Good Plus (VG+) |
| VG | Very Good (VG) |
| G+ | Good Plus (G+) |
| G | Good (G) |
| F | Fair (F) |
| P | Poor (P) |

The sleeve also takes Discogs' three extras: **Generic** (a plain sleeve), **No Cover**, **Not Graded**. Using Discogs' exact grades means the item's grade can ask Discogs for the price at that grade (section 6) with no mapping.

**Books** (the booksellers' scale, ABAA / ILAB): As New, Fine, Near Fine, Very Good, Good, Fair, Poor. One field. (Collectors grade a dust jacket separately; left out for now, section 9.)

**Movies & TV** (used-media terms, as eBay and Amazon use them, since there's no collectors' standard for discs and tapes): New (sealed), Like New, Very Good, Good, Acceptable. One field. *Open question for Phil:* or the Goldmine scale here too, as Discogs grades its video releases.

**Where it shows.** The edit page: a select per field, empty by default ("Not graded"). The item page: a **Condition** line in the facts beside the cover ("NM / VG+" for a record: record, then sleeve, with the full labels on hover), only when set. Optional free-text detail goes in the existing Notes field; no new one.

## 5. Price paid and value

**Fields** on the edit page (and the Add page, since you often know what you paid when you add it): **Price paid** and **Value**, each an optional amount in `VALUE_CURRENCY`, entered as "12.50". Under Value: where it came from and when ("Discogs suggestion for NM, 2026-11-14", "eBay: median of 23 listings, 2026-11-14", "Entered by you"), and a **Fetch value** button where a source can answer (section 6). Typing a value yourself sets the source to manual; a fetch never overwrites a manual value unless you press Fetch on that item yourself.

**Who sees money.** Price paid and value are private to the owner (and admins): not friends, not household members, not exports someone else can see. Condition is public to anyone who can see the item. *Open question for Phil:* should household members see each other's values (a shared collection's total)?

**Stats.** The owner's Stats gets a **Collection value** card: the total value per section and overall, what you paid for the items that have a price, how many items have a value ("812 of 1,240 valued"), and the date of the oldest fetched value. Owned items on the shelf only (`on_shelf()`: not removed, not unshelved, not wishlist). A friend's Stats never shows it.

**Exports and backups.** The personal export and backup carry condition, price paid, value and its source, and the photos (the backup already copies uploads; the export gets a `photos/` folder). Goodreads import leaves these alone.

## 6. Fetching a value

`utils/valuation.py`, one function per source, each returning `{cents, currency, source, note}` or None, never raising to the caller (a Busy result for rate limits, as `discogs_lookup` does).

**Records: Discogs price suggestions.** `GET /marketplace/price_suggestions/{release_id}` returns a suggested price for each grade, in the currency of the token owner's seller settings. The item's **record** grade picks the price (no grade: Very Good Plus, the most common, and the note says so). Needs:

- `discogs_release_id` on the item. The Add page's lookup knows it when you pick a Discogs result; it's saved from now on (a hidden field). Existing records without one: look it up once by barcode, then by catalogue number and title, and keep it only on a single clear match; otherwise the fetch says "Not matched on Discogs: add the release from Edit" and Edit gets a "Discogs release" field (the number or the URL).
- The token owner's **seller settings filled in** (section 7); without them Discogs answers with an error, which the fetch reports in words.
- Throttled and cached through `discogs_lookup`'s existing `_get` (60 requests a minute for a token).

As a fallback when there's no suggestion, `GET /marketplace/stats/{release_id}` gives the lowest current price and how many are for sale: shown as the note, never stored as the value.

**Books and movies: eBay Browse API.** `GET /buy/browse/v1/item_summary/search?gtin=<ISBN or UPC>` with `filter=buyingOptions:{FIXED_PRICE},conditionIds:{...}` near the item's condition, on `EBAY_MARKETPLACE` (default `EBAY_US`). The value is the **median asking price** of up to 50 fixed-price listings, item price only (not shipping); fewer than 3 listings and it isn't stored, only reported. The note always says what it is: "eBay: median asking price of 23 listings". These are **asking prices**, not what things sold for: eBay's sold-price API (Marketplace Insights) is restricted to approved partners. Labelled as a rough estimate everywhere it shows.

- Auth: an application token by client credentials (`POST /identity/v1/oauth2/token`, the `https://api.ebay.com/oauth/api_scope` scope), cached in memory until a minute before it expires (about two hours). The client secret only ever goes in that request's Authorization header, never a URL or a log line (the TMDb key leak, ROADMAP loose ends, is the lesson).
- No ISBN or barcode: no fetch; the button is hidden and the bulk tool skips it ("needs an ISBN or barcode").
- Requests go through `book_utils._get_public()`-style safety where it applies (fixed hosts here, so a host allow-list is enough).

**Per item.** **Fetch value** on the edit page: fetches now, fills the Value field and its note, and saves only when you save the form (so you can look at it first).

**In bulk.** A **Fetch values** tool beside **Fetch covers** in Settings, for your own shelf (admins: any user's, as with covers). It runs in the background with the same floating progress panel. Rather than a second job system, `cover_jobs` grows a `kind` column (`'cover'` or `'value'`, migration 039) and the worker branches on it; the panel says which. Options: which sections, and **skip items valued in the last 30 days** (on by default), **never overwrite values you typed** (always). One request every couple of seconds to stay inside both services' limits (eBay's default is 5,000 calls a day; a 1,000-item shelf is a fraction of that).

**Currency.** Discogs answers in the seller-settings currency, eBay in the marketplace's. Anything not in `VALUE_CURRENCY` is refused with a message ("Discogs answered in EUR; set your Discogs seller currency to USD"), not silently converted.

## 7. Setup: the manual steps

These go in the README's setup section at the 16.1 pass, and in `.env.example` now. Both are optional: without them, values are typed in by hand and the Fetch buttons don't show.

**Discogs (records)**

1. You already have the token if album search works: `DISCOGS_TOKEN` from discogs.com, Settings, Developers, "Generate new token". The value fetch uses the same one.
2. Fill in your **seller settings**: discogs.com, Settings, Seller Settings. Discogs gives price suggestions only to accounts with these filled in. You don't have to list or sell anything. Set the **currency** to the one in `VALUE_CURRENCY` (USD by default).
3. Restart the app. Settings, Maintenance, **Test value sources** (step 6) says whether it works.

**eBay (books, movies)**

1. Sign up at **developer.ebay.com** (the eBay Developers Program) with an eBay account, and accept the API license agreement. Approval of the account can take a day.
2. Under **Application Keys**, create a keyset for **Production** (not Sandbox, which has no real listings).
3. Before the production keys work, eBay asks how the app handles **Marketplace Account Deletion** notifications. This app stores no eBay user data (only prices), so choose the **exemption** ("not persisting eBay data") rather than setting up a notification endpoint.
4. Copy the keyset's **App ID (Client ID)** and **Cert ID (Client Secret)** into `.env` as `EBAY_CLIENT_ID` and `EBAY_CLIENT_SECRET`. Set `EBAY_MARKETPLACE` if you're not on ebay.com (`EBAY_GB`, `EBAY_DE`, ...) and `VALUE_CURRENCY` to match.
5. Restart the app and use **Test value sources**.

The default Browse API limit (5,000 calls a day) is plenty; nothing needs applying for.

**.env**

```
# Optional: collection values (docs/PHOTOS-VALUE-SPEC.md)
# VALUE_CURRENCY=USD
# EBAY_CLIENT_ID=
# EBAY_CLIENT_SECRET=
# EBAY_MARKETPLACE=EBAY_US
```

## 8. Access and security

| Action | Who | Where enforced |
|---|---|---|
| See photos and condition | anyone who can see the item | `can_view_book` |
| Add, caption, delete photos; set condition, price, value; fetch a value | owner or admin | `blueprints/photos.py`, the edit routes, SQL `WHERE` |
| See price paid, value, collection value | owner (and admins) | the item page and Stats queries |
| Fetch values in bulk | your own items; admins for any user | the job's scope, as cover jobs |

- Photo paths come from the server, never the browser; deletes go through `delete_image_file`; `is_safe_upload_path` on anything read back.
- Metadata stripped from every photo (GPS).
- Keys only in headers; `EBAY_CLIENT_SECRET` and the OAuth token never logged (urllib3 at INFO, ROADMAP loose end, before this ships).
- Photos in the gallery dialog are built with `textContent` / `escapeHtml` for captions; no inline JS (CSP).

## 9. Not in this phase (later, if wanted)

- Reordering the gallery by dragging (photos keep upload order; delete and re-add to change it).
- A dust-jacket grade for books; grades for box sets' individual discs.
- Value history over time (only the latest value and its date are kept).
- Currency conversion.
- Bulk edit of condition (one more entry in `utils/bulk.py`'s `ACTIONS`, easy later).
- Photos on the Add page.

## 10. Execution steps (one commit each)

0. Branch `phase-16a-photos-value`. This spec, ROADMAP 16.0a pointing at it.
1. Migrations 036 to 038, `create_database.sql` folded in, `utils/condition.py` and its agreement test. No UI.
2. Photos: `save_photo`, `blueprints/photos.py`, orphan cleanup and delete/merge handling, tests (including the cleanup one).
3. Edit page Photos section (JS uploads, confirms, captions).
4. Item page "More photos" gallery in the zoom dialog.
5. Condition: edit selects, item page line, validation.
6. Price paid and value: fields on Add and Edit, privacy on the item page, exports.
7. `utils/valuation.py`: Discogs (release id saved on add, matched for existing records) and eBay (token, median), with tests on recorded answers (the network is blocked in tests).
8. Per-item Fetch value; Test value sources in Maintenance.
9. Bulk Fetch values (`cover_jobs.kind`, migration 039, the panel).
10. Stats: Collection value card.
11. `.env.example`, `docs/ARCHITECTURE.md` (the new blueprint, utils, tables, env vars), README notes for 16.1.

Each step: `npm run build:css` when classes change, `pytest`, and a look on the dev server at phone and desktop width in each style.

## 11. Tests

- Access: a friend sees photos and condition but not price or value; a household member the same (unless Phil decides otherwise); a stranger gets 404 on the item and on every photo route; only the owner or an admin can add or delete.
- **The orphan cleanup keeps photos** (a photo file referenced in `item_photos` is not listed as orphaned); deleting an item removes its photo files; merging moves them.
- `save_photo` strips EXIF (a fixture with GPS comes out without it) and turns a sideways phone photo upright.
- Condition codes: the table and `utils/condition.py` agree; a code from another type is refused.
- Money: "12.50" is 1250 cents; blank is NULL; nonsense is refused with a message.
- Valuation on recorded Discogs and eBay answers: the grade picks the Discogs price; the eBay median ignores shipping and needs 3 listings; another currency is refused; a manual value isn't overwritten by the bulk job.
- `test_every_page_loads` with the new routes; `test_csp` for the gallery's markup.

## 12. Open questions for Phil

Built with the draft's answer to each (2026-11-15), pending Phil's say:

1. Movies' grades: **used-media terms** (New, Like New, Very Good, Good, Acceptable). Switching to Goldmine is rows in `condition_grades` (a migration) and `utils/condition.py`.
2. Values to household members: **private to the owner** (and admins). Sharing within a household would change the item page's `can_manage` test for the money and `stats.collection_value`'s owner filter.
3. The phase's place: **16.0a**, before the code review and screenshots.

## 13. Built differently from the draft

- `condition_grades` has a `sleeve_only` column for Discogs' sleeve extras (Generic, No Cover, Not Graded), so the table says which grades the record itself can't have.
- Photos can be cropped and straightened (Phil, 2026-11-15): a Crop button beside Replace and Delete opens the cover's crop tool on that photo and saves to `POST /photos/photo/<id>/crop`.
- Photo routes: `/photos/photo/<id>/delete` and `/caption`, not `/photos/<id>/...`, which would have shared a URL shape with `/photos/<book_id>/<kind>`.
- The Photos section is its own card under the edit form, not inside it (a form can't hold forms); the "This copy" fields (condition, price, value) are inside the form, on Add too.
- "More photos" opens on the first photo after the cover, which the page already shows; Previous goes back to it.
- No merge of items exists anywhere in the code yet (`book_matching` matches but never merges), so there was nothing to move photos for.
- Personal library backups don't hold photos (site backups and the personal export do); a restored item that had been deleted comes back without its photos.
- The "Saved. Add photos?" flash after adding an item was left out: the edit page's Photos card is one click from the item page.
