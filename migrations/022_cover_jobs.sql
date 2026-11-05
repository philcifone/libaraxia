-- 022: background cover fetching (Phase 5). One row per "fetch missing
-- covers" run, started from the Goodreads import result, the profile page
-- (scope 'own') or the admin covers page (scope 'all'). A thread in the app
-- works through it (utils/cover_jobs.py); the row is its progress and lets
-- any gunicorn worker report status or pick up a job whose worker died.

CREATE TABLE cover_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,                  -- who started it (and sees its progress)
    scope TEXT NOT NULL CHECK (scope IN ('own', 'all')),
    status TEXT NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'done', 'cancelled')),
    total INTEGER NOT NULL DEFAULT 0,          -- books missing a cover when it started
    checked INTEGER NOT NULL DEFAULT 0,
    found INTEGER NOT NULL DEFAULT 0,
    last_book_id INTEGER NOT NULL DEFAULT 0,   -- cursor: books are done in id order
    worker TEXT,                               -- process working on it
    heartbeat_at TIMESTAMP,                    -- stale => another process may take over
    dismissed INTEGER NOT NULL DEFAULT 0,      -- hidden from the progress panel
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX idx_cover_jobs_user ON cover_jobs(user_id, dismissed);
CREATE INDEX idx_cover_jobs_status ON cover_jobs(status);
