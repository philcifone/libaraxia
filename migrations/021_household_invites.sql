-- 021: household invites (Phase 4). Joining a household now needs the
-- invitee's consent: the owner sends an invite, the friend accepts or
-- declines it on the notifications page (utils/households.py). A pending
-- invite is a row here; accepting, declining or cancelling deletes it.

CREATE TABLE household_invites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    inviter_id INTEGER NOT NULL,
    invitee_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (inviter_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (invitee_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE (inviter_id, invitee_id)
);
CREATE INDEX idx_household_invites_invitee ON household_invites(invitee_id);

-- Every household has exactly one owner from now on. Admin-created ones
-- could have none: give those to the longest-standing member.
UPDATE library_members SET role = 'owner'
WHERE id IN (
    SELECT (SELECT m2.id FROM library_members m2
            WHERE m2.library_id = m.library_id ORDER BY m2.added_at, m2.id LIMIT 1)
    FROM library_members m
    GROUP BY m.library_id
    HAVING SUM(m.role = 'owner') = 0
);

-- A household of one shares nothing; dissolve those (the user just has
-- their own library, as before they joined).
DELETE FROM library_members
WHERE library_id IN (SELECT library_id FROM library_members GROUP BY library_id HAVING COUNT(*) = 1);
