-- 029: reading goals per year (ROADMAP 12.3). Until now one number,
-- users.reading_goal, counted against "this calendar year", so on 1 January
-- last year's goal silently became this year's and the old one was lost.
-- A row per user and year keeps them. The existing goal becomes this year's
-- (the year the migration runs). users.reading_goal stays, unused: dropping
-- a column needs a table rebuild of users, which isn't worth it for this.
CREATE TABLE reading_goals (
    user_id INTEGER NOT NULL,
    year INTEGER NOT NULL,
    goal INTEGER NOT NULL CHECK (goal > 0),
    PRIMARY KEY (user_id, year),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

INSERT INTO reading_goals (user_id, year, goal)
SELECT id, CAST(strftime('%Y', 'now') AS INTEGER), reading_goal
FROM users WHERE reading_goal > 0;
