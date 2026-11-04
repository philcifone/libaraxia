-- 018: one definition of "a book on someone's shelf".
--
-- A wishlist entry is a full books row (added_by = the person wishing) plus a
-- wishlist row. Library queries used to exclude those with their own
-- NOT EXISTS clause, and the clauses disagreed (some checked any user's
-- wishlist, some forgot entirely, so stats counted wishlist books as owned).
--
-- A book belongs to its owner's library when it has an owner and that owner
-- has not wishlisted it. Someone else wishlisting a book you own (quick add
-- from your shelf) doesn't take it off your shelf.
--
-- Removed (deaccessioned) books are still in the view: library pages hide
-- them with `removed_at IS NULL` unless "show removed" is on, but stats of
-- what you've read and exports keep them.
--
-- Note for future migrations: a table rebuild of books or wishlist (create
-- new, drop old, rename) must DROP this view first and recreate it after,
-- or SQLite refuses the rename.
CREATE VIEW library_books AS
SELECT b.*
FROM books b
WHERE b.added_by IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM wishlist w
      WHERE w.book_id = b.id AND w.user_id = b.added_by
  );
