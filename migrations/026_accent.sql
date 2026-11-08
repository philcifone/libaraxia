-- 026: accent colour per user (ROADMAP 8B.5), next to theme_style and
-- color_mode (013). Values are models.ACCENTS keys, checked in code like the
-- other two; 'green' is the House look as it was.
ALTER TABLE users ADD COLUMN accent TEXT NOT NULL DEFAULT 'green';
