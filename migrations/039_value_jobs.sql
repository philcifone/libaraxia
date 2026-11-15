-- 039: bulk Fetch values (ROADMAP 16.0a, docs/PHOTOS-VALUE-SPEC.md section 6)
-- runs as a background job like Fetch covers: cover_jobs grows a kind
-- rather than a second job system, and the worker branches on it
-- (utils/cover_jobs.py). A value job's choices: which sections
-- (media_types, comma-separated, NULL = all) and how recent a value may be
-- before it's fetched again (skip_days, NULL = refetch everything). Values
-- typed by hand are never overwritten, whatever the choices.

ALTER TABLE cover_jobs ADD COLUMN kind TEXT NOT NULL DEFAULT 'cover' CHECK (kind IN ('cover', 'value'));
ALTER TABLE cover_jobs ADD COLUMN media_types TEXT;
ALTER TABLE cover_jobs ADD COLUMN skip_days INTEGER;
