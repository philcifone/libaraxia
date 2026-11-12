-- 034: Movies & TV (ROADMAP 15.1). A TV season box set is a video row like
-- any film (same tape or disc, same statuses, same shelf), so it gets a kind
-- rather than a media type of its own.
--
-- `video_kind`: 'tv', or NULL for a movie. NULL means movie so existing rows
-- need no backfill, and the app stores NULL for a movie too (media.video_kind),
-- so a movie has one spelling. The kinds are rows in `video_kinds`, like
-- media_types and statuses: another kind is an INSERT, and a test checks the
-- table agrees with media.VIDEO_KINDS.
--
-- `season`: free text for TV ("Season 2", "Complete series"); NULL otherwise.
--
-- ADD COLUMN, no rebuild: the library_* views select b.*, which SQLite
-- expands when a query is compiled, so they pick the columns up (see 025).
-- A REFERENCES column may be added this way because its default is NULL.

CREATE TABLE video_kinds (
    name TEXT PRIMARY KEY
);
INSERT INTO video_kinds (name) VALUES ('movie'), ('tv');

ALTER TABLE books ADD COLUMN video_kind TEXT REFERENCES video_kinds(name);
ALTER TABLE books ADD COLUMN season TEXT;
