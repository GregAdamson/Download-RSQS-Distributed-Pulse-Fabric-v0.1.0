from __future__ import annotations
import json
import sqlite3
import threading
from dataclasses import asdict
from typing import List, Tuple

from .model import Pulse


class DurablePulseEventStore:
    def __init__(self, path: str) -> None:
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.RLock()
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS pulse_events(
          seq INTEGER PRIMARY KEY AUTOINCREMENT,
          pulse_id TEXT NOT NULL UNIQUE,
          pulse_json TEXT NOT NULL
        )
        """)
        self.conn.commit()

    def append(self, pulse: Pulse) -> int:
        raw = json.dumps(asdict(pulse), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        with self._lock:
            row = self.conn.execute("SELECT seq FROM pulse_events WHERE pulse_id=?", (pulse.pulse_id,)).fetchone()
            if row:
                return int(row[0])
            cur = self.conn.execute("INSERT INTO pulse_events(pulse_id,pulse_json) VALUES(?,?)", (pulse.pulse_id, raw))
            self.conn.commit()
            return int(cur.lastrowid)

    def after(self, cursor: int, limit: int = 100) -> Tuple[int, List[Pulse]]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT seq,pulse_json FROM pulse_events WHERE seq>? ORDER BY seq LIMIT ?",
                (max(0, cursor), max(1, min(limit, 1000))),
            ).fetchall()
        if not rows:
            return cursor, []
        return int(rows[-1][0]), [
            Pulse(
                pulse_id=data["pulse_id"],
                network=data["network"],
                epoch=int(data["epoch"]),
                kind=data["kind"],
                issued_at=int(data["issued_at"]),
                expires_at=int(data["expires_at"]),
                payload=data.get("payload", {}),
                signature=data.get("signature", ""),
            )
            for data in (json.loads(row[1]) for row in rows)
        ]

    def close(self) -> None:
        with self._lock:
            self.conn.close()
