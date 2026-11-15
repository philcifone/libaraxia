-- 038: price paid and value (ROADMAP 16.0a, docs/PHOTOS-VALUE-SPEC.md
-- sections 5 and 6). Money is whole cents (no float rounding), in the site's
-- one currency (VALUE_CURRENCY). Private to the owner and admins.

ALTER TABLE books ADD COLUMN price_paid_cents INTEGER;
ALTER TABLE books ADD COLUMN value_cents INTEGER;
ALTER TABLE books ADD COLUMN value_source TEXT;             -- 'manual', 'discogs', 'ebay'
ALTER TABLE books ADD COLUMN value_note TEXT;               -- e.g. 'median of 23 listings'
ALTER TABLE books ADD COLUMN value_checked_at TIMESTAMP;
ALTER TABLE books ADD COLUMN discogs_release_id INTEGER;    -- records: for price suggestions
