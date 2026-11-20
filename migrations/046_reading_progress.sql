-- 046: manual reading progress (ROADMAP 16.0f, docs/PROGRESS-MERGE-SPEC.md
-- part A). Progress lives on the open reading session (started, not
-- finished), so a re-read starts again at 0. `progress` is 0 to 1 and is
-- what the cover's ring reads; `progress_page` is the page typed, when one
-- was (the app works out `progress` from the book's page count). Seen only
-- by the session's own user. Written by utils/reading_progress.py.
ALTER TABLE reading_sessions ADD COLUMN progress REAL
    CHECK (progress IS NULL OR (progress >= 0 AND progress <= 1));
ALTER TABLE reading_sessions ADD COLUMN progress_page INTEGER
    CHECK (progress_page IS NULL OR progress_page >= 0);
ALTER TABLE reading_sessions ADD COLUMN progress_at TIMESTAMP;

-- When Audiobookshelf's progress last changed, so the ring can show the
-- newer of ABS and manual progress (Phil, 2026-11-20). NULL on rows from
-- before this migration until their next sync.
ALTER TABLE abs_links ADD COLUMN progress_at TIMESTAMP;
