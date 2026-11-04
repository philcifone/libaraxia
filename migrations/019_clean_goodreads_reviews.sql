-- 019: Goodreads exports reviews as HTML: line breaks are <br/>, so
-- "<br/><br/>" is a paragraph break. The importer stored that as-is, and the
-- tags showed up literally in reviews and in the review editor. Reviews are
-- shown with white-space: pre-wrap, so a newline is the right replacement.
-- Only <br> tags were found in the data (2026-11-04); the importer now cleans
-- full HTML on the way in. Data only; a no-op on a fresh database.
--
-- Order matters: Windows line endings first, then a <br> that already sits
-- on its own line (someone edited around it) becomes a blank line rather
-- than three newlines, then every remaining <br>, then runs of 3+ newlines
-- collapse to a paragraph break, and a trailing <br/> doesn't leave a
-- trailing newline.
UPDATE read_data
SET comment = trim(replace(replace(replace(replace(replace(replace(replace(
        replace(comment, char(13) || char(10), char(10)),
        char(10) || '<br>' || char(10), char(10) || char(10)),
        '<br />', char(10)),
        '<br/>', char(10)),
        '<br>', char(10)),
        '<BR>', char(10)),
        char(10) || char(10) || char(10) || char(10), char(10) || char(10)),
        char(10) || char(10) || char(10), char(10) || char(10)), char(10) || ' ')
WHERE comment LIKE '%<br%';

