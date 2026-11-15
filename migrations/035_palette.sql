-- 035: colour palette per user (Profile -> Appearance -> Colours), next to
-- theme_style, color_mode, accent and font. Values are models.PALETTES keys,
-- checked in code like the others. 'theme' keeps the style's own colours;
-- 'walnut' gives OG the Shelf style's parchment and walnut (Phil, 2026-11-15).
ALTER TABLE users ADD COLUMN palette TEXT NOT NULL DEFAULT 'theme';
