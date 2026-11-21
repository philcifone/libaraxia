-- 048: each user's last sort per media type (Phil, 2026-11-21: "I like my
-- books sorted one way and movies another"). Picking a sort on any grid of
-- that type saves it; a grid opened without a sort in its URL uses it
-- (utils/sorting.py). Keys are sorting.SORTS keys, checked in code; a key
-- that's since been dropped just falls back to the default.
CREATE TABLE sort_preferences (
    user_id INTEGER NOT NULL,
    media_type TEXT NOT NULL,
    sort_by TEXT NOT NULL,
    sort_order TEXT NOT NULL CHECK (sort_order IN ('asc', 'desc')),
    PRIMARY KEY (user_id, media_type),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (media_type) REFERENCES media_types(name)
);
