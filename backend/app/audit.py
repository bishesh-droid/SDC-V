"""SQLite audit log: inputs, code edition, tool versions, verdicts, model version, reviewer."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY, created_at TEXT NOT NULL, status TEXT NOT NULL, mode TEXT NOT NULL,
  summary TEXT, record TEXT NOT NULL, reviewer TEXT, reviewed_at TEXT, review_note TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_created ON runs (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs (status);
"""


def _like(q: str) -> str:
    return "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


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

    @staticmethod
    def _where(status: str | None, mode: str | None, q: str | None, reviewed: bool | None):
        cond, args = [], []
        if status:
            cond.append("status = ?"); args.append(status)
        if mode:
            cond.append("mode = ?"); args.append(mode)
        if q:
            cond.append("(id LIKE ? ESCAPE '\\' OR summary LIKE ? ESCAPE '\\' OR reviewer LIKE ? ESCAPE '\\')")
            args += [_like(q)] * 3
        if reviewed is True:
            cond.append("reviewer IS NOT NULL")
        elif reviewed is False:
            cond.append("reviewer IS NULL")
        return (" WHERE " + " AND ".join(cond)) if cond else "", args

    def search(self, limit: int = 50, offset: int = 0, status: str | None = None, mode: str | None = None,
               q: str | None = None, reviewed: bool | None = None) -> tuple[list[dict], int]:
        where, args = self._where(status, mode, q, reviewed)
        with self._conn() as c:
            total = c.execute("SELECT COUNT(*) FROM runs" + where, args).fetchone()[0]
            rows = c.execute("SELECT id, created_at, status, mode, summary, reviewer, reviewed_at FROM runs" + where +
                             " ORDER BY created_at DESC, rowid DESC LIMIT ? OFFSET ?", [*args, limit, offset]).fetchall()
        return [dict(r) for r in rows], total

    def list(self, limit: int = 50) -> list[dict]:
        return self.search(limit)[0]

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

    def stats(self) -> dict:
        day_ago = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(timespec="seconds")
        with self._conn() as c:
            total = c.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
            by_status = {r[0]: r[1] for r in c.execute("SELECT status, COUNT(*) FROM runs GROUP BY status")}
            by_mode = {r[0]: r[1] for r in c.execute("SELECT mode, COUNT(*) FROM runs GROUP BY mode")}
            reviewed = c.execute("SELECT COUNT(*) FROM runs WHERE reviewer IS NOT NULL").fetchone()[0]
            last_day = c.execute("SELECT COUNT(*) FROM runs WHERE created_at >= ?", (day_ago,)).fetchone()[0]
            models = {r[0]: r[1] for r in c.execute(
                "SELECT json_extract(record, '$.llm_model') AS m, COUNT(*) FROM runs WHERE m IS NOT NULL GROUP BY m")}
            narr = {r[0]: r[1] for r in c.execute(
                "SELECT json_extract(record, '$.result.narrative_source') AS s, COUNT(*) FROM runs "
                "WHERE s IS NOT NULL GROUP BY s")}
        return {"total": total, "by_status": by_status, "by_mode": by_mode, "reviewed": reviewed,
                "last_24h": last_day, "models": models, "narrative_source": narr}
