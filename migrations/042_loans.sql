-- 042: loans (ROADMAP 16.0d, docs/LENDING-SPEC.md).
-- Who has a physical copy: "bob has my Dune since March". A record, not a
-- lock: nothing is enforced, and a loan doesn't follow the item's shelf
-- state (removing or transferring it leaves the loan as it is).
--
-- lent_by: who handed it over, the owner or a member of their household.
-- borrower_id: a user in the lender's circle, or NULL for someone not on
-- the site. borrower_name is always filled (the typed name, or the user's
-- name when lent), so the row still reads right if their account goes.
-- Dates are plain dates ('YYYY-MM-DD'). One open loan per item.

CREATE TABLE loans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    lent_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    borrower_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    borrower_name TEXT NOT NULL,
    lent_at DATE NOT NULL,
    due_at DATE,
    returned_at DATE,
    note TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CHECK (length(trim(borrower_name)) > 0),
    CHECK (due_at IS NULL OR due_at >= lent_at),
    CHECK (returned_at IS NULL OR returned_at >= lent_at)
);
CREATE UNIQUE INDEX idx_loans_one_open ON loans(book_id) WHERE returned_at IS NULL;
CREATE INDEX idx_loans_book ON loans(book_id);
CREATE INDEX idx_loans_borrower ON loans(borrower_id) WHERE borrower_id IS NOT NULL;
CREATE INDEX idx_loans_lent_by ON loans(lent_by);
