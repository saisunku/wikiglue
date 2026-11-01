"""wikiglue's own bookkeeping (state_dir/glue.db): which bookmarks are in the
vault, who to tell when a job finishes, which results were already posted.

Plain sqlite3: every query is tiny and local, so blocking calls are fine.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS bookmarks (
    id         TEXT PRIMARY KEY,     -- Karakeep bookmark id
    user       TEXT NOT NULL,        -- users.<key>
    status     TEXT NOT NULL,        -- pending | written | skipped
    raw_dir    TEXT,                 -- vault-relative, once written
    first_seen REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS notify (  -- chat messages waiting for a bookmark's ingest
    bookmark_id TEXT PRIMARY KEY,
    room_id     TEXT NOT NULL,
    event_id    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS results ( -- job results already handled
    job_id  TEXT PRIMARY KEY,
    handled REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS mail (     -- emails seen in a user's "Family Wiki" Maildir
    id      TEXT PRIMARY KEY,        -- source (user or mailbox) + Message-ID (or Maildir key)
    user    TEXT NOT NULL,           -- the source's key
    status  TEXT NOT NULL,           -- written | skipped (before setup) | rejected (sender) | failed
    raw_dir TEXT,
    seen    REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class State:
    def __init__(self, path: Path):
        self.db = sqlite3.connect(path, isolation_level=None)  # autocommit
        self.db.executescript(SCHEMA)

    # --- bookmarks ---

    def bookmark_status(self, bookmark_id: str) -> str | None:
        row = self.db.execute("SELECT status FROM bookmarks WHERE id = ?", (bookmark_id,)).fetchone()
        return row[0] if row else None

    def bookmark_first_seen(self, bookmark_id: str) -> float | None:
        row = self.db.execute("SELECT first_seen FROM bookmarks WHERE id = ?", (bookmark_id,)).fetchone()
        return row[0] if row else None

    def set_bookmark(self, bookmark_id: str, user: str, status: str, raw_dir: str | None = None) -> None:
        self.db.execute(
            "INSERT INTO bookmarks (id, user, status, raw_dir, first_seen) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET status = excluded.status, raw_dir = excluded.raw_dir",
            (bookmark_id, user, status, raw_dir, time.time()),
        )

    # --- mail ---

    def mail_status(self, mail_id: str) -> str | None:
        row = self.db.execute("SELECT status FROM mail WHERE id = ?", (mail_id,)).fetchone()
        return row[0] if row else None

    def set_mail(self, mail_id: str, user: str, status: str, raw_dir: str | None = None) -> None:
        self.db.execute(
            "INSERT INTO mail (id, user, status, raw_dir, seen) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET status = excluded.status, raw_dir = excluded.raw_dir",
            (mail_id, user, status, raw_dir, time.time()),
        )

    def has_bookmarks(self, user: str) -> bool:
        return self.db.execute("SELECT 1 FROM bookmarks WHERE user = ? LIMIT 1", (user,)).fetchone() is not None

    # --- chat notifications for bookmarks ---

    def add_notify(self, bookmark_id: str, room_id: str, event_id: str) -> None:
        self.db.execute("INSERT OR REPLACE INTO notify VALUES (?, ?, ?)", (bookmark_id, room_id, event_id))

    def pop_notify(self, bookmark_id: str) -> tuple[str, str] | None:
        row = self.db.execute(
            "SELECT room_id, event_id FROM notify WHERE bookmark_id = ?", (bookmark_id,)
        ).fetchone()
        self.db.execute("DELETE FROM notify WHERE bookmark_id = ?", (bookmark_id,))
        return row

    def get_notify(self, bookmark_id: str) -> tuple[str, str] | None:
        return self.db.execute(
            "SELECT room_id, event_id FROM notify WHERE bookmark_id = ?", (bookmark_id,)
        ).fetchone()

    # --- job results ---

    def result_handled(self, job_id: str) -> bool:
        return self.db.execute("SELECT 1 FROM results WHERE job_id = ?", (job_id,)).fetchone() is not None

    def mark_result_handled(self, job_id: str) -> None:
        self.db.execute("INSERT OR IGNORE INTO results VALUES (?, ?)", (job_id, time.time()))

    # --- settings ---

    def get(self, key: str) -> str | None:
        row = self.db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def put(self, key: str, value: str) -> None:
        self.db.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (key, value))
