-- 037: condition grades (ROADMAP 16.0a, docs/PHOTOS-VALUE-SPEC.md section 4).
-- The standard terms per type, as a lookup table like statuses: best first by
-- rank. Records use Discogs' Goldmine labels verbatim, so a grade can ask
-- Discogs for its price with no mapping; the sleeve-only rows (Generic,
-- No Cover, Not Graded) are flagged. utils/condition.py keeps the same list
-- and validates codes on save (books.condition can't be an FK into a
-- two-column key); a test checks they agree.

CREATE TABLE condition_grades (
    media_type TEXT NOT NULL REFERENCES media_types(name),
    code TEXT NOT NULL,              -- stored on the item: 'NM', 'fine', ...
    label TEXT NOT NULL,             -- shown: 'Near Mint (NM or M-)'
    rank INTEGER NOT NULL,           -- best first
    sleeve_only INTEGER NOT NULL DEFAULT 0 CHECK (sleeve_only IN (0, 1)),
    PRIMARY KEY (media_type, code)
);
INSERT INTO condition_grades (media_type, code, label, rank, sleeve_only) VALUES
    ('record', 'M', 'Mint (M)', 1, 0),
    ('record', 'NM', 'Near Mint (NM or M-)', 2, 0),
    ('record', 'VG+', 'Very Good Plus (VG+)', 3, 0),
    ('record', 'VG', 'Very Good (VG)', 4, 0),
    ('record', 'G+', 'Good Plus (G+)', 5, 0),
    ('record', 'G', 'Good (G)', 6, 0),
    ('record', 'F', 'Fair (F)', 7, 0),
    ('record', 'P', 'Poor (P)', 8, 0),
    ('record', 'Generic', 'Generic', 9, 1),
    ('record', 'No Cover', 'No Cover', 10, 1),
    ('record', 'Not Graded', 'Not Graded', 11, 1),
    ('book', 'as_new', 'As New', 1, 0),
    ('book', 'fine', 'Fine', 2, 0),
    ('book', 'near_fine', 'Near Fine', 3, 0),
    ('book', 'very_good', 'Very Good', 4, 0),
    ('book', 'good', 'Good', 5, 0),
    ('book', 'fair', 'Fair', 6, 0),
    ('book', 'poor', 'Poor', 7, 0),
    ('video', 'new', 'New (sealed)', 1, 0),
    ('video', 'like_new', 'Like New', 2, 0),
    ('video', 'very_good', 'Very Good', 3, 0),
    ('video', 'good', 'Good', 4, 0),
    ('video', 'acceptable', 'Acceptable', 5, 0);

-- The item (a record: the vinyl, tape or disc) and, records only, the sleeve.
ALTER TABLE books ADD COLUMN condition TEXT;
ALTER TABLE books ADD COLUMN sleeve_condition TEXT;
