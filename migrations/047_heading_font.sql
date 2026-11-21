-- 047: a heading font beside the text font (Settings -> Account ->
-- Appearance, 2026-11-20). Until now users.font set headings and text
-- alike, so everyone starts with headings in the font they already had.
-- Values are models.HEADING_FONTS keys, checked in code like the others.
ALTER TABLE users ADD COLUMN heading_font TEXT NOT NULL DEFAULT 'theme';
UPDATE users SET heading_font = font;
