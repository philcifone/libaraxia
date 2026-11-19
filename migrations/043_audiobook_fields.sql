-- 043: an audiobook's narrator (ROADMAP 16.0e, docs/AUDIOBOOKSHELF-SPEC.md
-- section 7). Free text, as Audiobookshelf writes it ("Ray Porter, Jane
-- Doe"); set for format 'Audiobook' only. An audiobook's length needs no
-- column: it goes in runtime_minutes, which books didn't use. The 'Ebook'
-- format needs no migration either (books.format has no CHECK).

ALTER TABLE books ADD COLUMN narrator TEXT;
