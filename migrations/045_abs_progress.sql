-- 045: how far along each Audiobookshelf item is, for the progress ring on
-- its cover wherever the cover shows (Phil, 2026-11-19; grids, lists, the
-- item page). 0 to 1 while in progress; NULL when finished, not started,
-- or not known (a disconnect clears it). Written by every Sync and by the
-- item page's live line (utils/abs_import.py), never by the browser.
ALTER TABLE abs_links ADD COLUMN progress REAL
    CHECK (progress IS NULL OR (progress > 0 AND progress <= 1));
