-- 028: font choice per user (Profile -> Appearance -> Font), next to
-- theme_style, color_mode and accent. Values are models.FONTS keys, checked
-- in code like the others; 'theme' keeps each style's own fonts.
ALTER TABLE users ADD COLUMN font TEXT NOT NULL DEFAULT 'theme';
