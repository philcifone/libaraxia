-- Per-user appearance settings (Profile → Appearance).
-- theme_style: 'house' (Gruvbox, square, bold lines) or 'classic' (the original look)
-- color_mode:  'system' (follow the OS), 'light' or 'dark'
-- The app treats missing columns as house/system, so it runs before this migration too.
--
-- Note: users already has legacy theme_mode (default 'dark') and accent_color columns
-- from the original schema. Nothing reads them; they are left alone here and can be
-- dropped when the schema is consolidated (ROADMAP Phase 2.1).
ALTER TABLE users ADD COLUMN theme_style TEXT NOT NULL DEFAULT 'house';
ALTER TABLE users ADD COLUMN color_mode TEXT NOT NULL DEFAULT 'system';
