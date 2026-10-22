"""SQLite audit log: inputs, code edition, tool versions, verdicts, model version, reviewer."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from . import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY, created_at TEXT NOT NULL, status TEXT NOT NULL, mode TEXT NOT NULL,
  summary TEXT, record TEXT NOT NULL, reviewer TEXT, reviewed_at TEXT, review_note TEXT
);
"""


class AuditLog:
    def __init__(self, path: Path | str | None = None):
        self.path = str(path or (config.DATA_DIR / "audit.db"))
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._conn() as c:
            c.executescript(_SCHEMA)

    def _conn(self):
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        return c

    def save(self, run_id: str, status: str, mode: str, summary: str, record: dict) -> None:
        with self._lock, self._conn() as c:
            c.execute("INSERT OR REPLACE INTO runs (id, created_at, status, mode, summary, record) VALUES (?,?,?,?,?,?)",
                      (run_id, datetime.now(timezone.utc).isoformat(timespec="seconds"), status, mode, summary,
                       json.dumps(record, default=str)))

    def list(self, limit: int = 50) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT id, created_at, status, mode, summary, reviewer FROM runs "
                             "ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def get(self, run_id: str) -> dict | None:
        with self._conn() as c:
            r = c.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["record"] = json.loads(d["record"])
        return d

    def review(self, run_id: str, reviewer: str, note: str) -> bool:
        with self._lock, self._conn() as c:
            cur = c.execute("UPDATE runs SET reviewer=?, reviewed_at=?, review_note=? WHERE id=?",
                            (reviewer, datetime.now(timezone.utc).isoformat(timespec="seconds"), note, run_id))
        return cur.rowcount > 0
