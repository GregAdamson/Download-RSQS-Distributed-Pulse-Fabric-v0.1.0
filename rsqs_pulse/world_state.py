from __future__ import annotations
import json
import sqlite3
import time
from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass(frozen=True)
class StateFact:
    key: str
    value: Any
    source: str
    confidence: float
    version: int


class WorldState:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS world_state(
          key TEXT NOT NULL,
          version INTEGER NOT NULL,
          value_json TEXT NOT NULL,
          source TEXT NOT NULL,
          confidence REAL NOT NULL,
          observed_at INTEGER NOT NULL,
          PRIMARY KEY(key, version)
        )
        """)
        self.conn.commit()

    def assert_fact(self, key: str, value: Any, source: str, confidence: float = 1.0) -> StateFact:
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence must be in [0,1]")
        row = self.conn.execute("SELECT COALESCE(MAX(version),0) FROM world_state WHERE key=?", (key,)).fetchone()
        version = int(row[0]) + 1
        self.conn.execute(
            "INSERT INTO world_state(key,version,value_json,source,confidence,observed_at) VALUES(?,?,?,?,?,?)",
            (key, version, json.dumps(value, sort_keys=True), source, confidence, int(time.time())),
        )
        self.conn.commit()
        return StateFact(key, value, source, confidence, version)

    def latest(self, key: str) -> StateFact | None:
        row = self.conn.execute(
            "SELECT value_json,source,confidence,version FROM world_state WHERE key=? ORDER BY version DESC LIMIT 1",
            (key,),
        ).fetchone()
        if not row:
            return None
        return StateFact(key, json.loads(row[0]), row[1], float(row[2]), int(row[3]))

    def history(self, key: str) -> List[StateFact]:
        rows = self.conn.execute(
            "SELECT value_json,source,confidence,version FROM world_state WHERE key=? ORDER BY version",
            (key,),
        ).fetchall()
        return [StateFact(key, json.loads(r[0]), r[1], float(r[2]), int(r[3])) for r in rows]
