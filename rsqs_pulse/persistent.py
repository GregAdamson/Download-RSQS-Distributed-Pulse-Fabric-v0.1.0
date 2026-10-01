from __future__ import annotations
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable


class SQLiteState:
    def __init__(self, path: str = ":memory:") -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._init()

    def _init(self) -> None:
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS meta(
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS capabilities(
          node_id TEXT NOT NULL,
          name TEXT NOT NULL,
          version TEXT NOT NULL,
          metadata_json TEXT NOT NULL,
          updated_at INTEGER NOT NULL,
          PRIMARY KEY(node_id, name)
        );
        CREATE TABLE IF NOT EXISTS results(
          task_id TEXT NOT NULL,
          node_id TEXT NOT NULL,
          epoch INTEGER NOT NULL,
          status TEXT NOT NULL,
          output_json TEXT NOT NULL,
          PRIMARY KEY(task_id, node_id)
        );
        CREATE TABLE IF NOT EXISTS offline_events(
          seq INTEGER PRIMARY KEY AUTOINCREMENT,
          node_id TEXT NOT NULL,
          event_json TEXT NOT NULL,
          reconciled INTEGER NOT NULL DEFAULT 0
        );
        """)
        self.conn.commit()

    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        self.conn.commit()

    def get_meta(self, key: str, default: str | None = None) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    def upsert_capability(self, node_id: str, name: str, version: str, metadata: Dict[str, Any], updated_at: int) -> None:
        self.conn.execute(
            """INSERT INTO capabilities(node_id,name,version,metadata_json,updated_at)
               VALUES(?,?,?,?,?)
               ON CONFLICT(node_id,name) DO UPDATE SET
                 version=excluded.version,
                 metadata_json=excluded.metadata_json,
                 updated_at=excluded.updated_at""",
            (node_id, name, version, json.dumps(metadata, sort_keys=True), updated_at),
        )
        self.conn.commit()

    def list_capabilities(self, name: str | None = None) -> list[Dict[str, Any]]:
        sql = "SELECT node_id,name,version,metadata_json,updated_at FROM capabilities"
        params: tuple[Any, ...] = ()
        if name is not None:
            sql += " WHERE name=?"
            params = (name,)
        rows = self.conn.execute(sql, params).fetchall()
        return [
            {
                "node_id": r[0],
                "name": r[1],
                "version": r[2],
                "metadata": json.loads(r[3]),
                "updated_at": r[4],
            }
            for r in rows
        ]

    def record_result(self, task_id: str, node_id: str, epoch: int, status: str, output: Dict[str, Any]) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO results(task_id,node_id,epoch,status,output_json)
               VALUES(?,?,?,?,?)""",
            (task_id, node_id, epoch, status, json.dumps(output, sort_keys=True)),
        )
        self.conn.commit()

    def queue_offline(self, node_id: str, event: Dict[str, Any]) -> int:
        cur = self.conn.execute(
            "INSERT INTO offline_events(node_id,event_json) VALUES(?,?)",
            (node_id, json.dumps(event, sort_keys=True)),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def pending_offline(self, node_id: str) -> Iterable[tuple[int, Dict[str, Any]]]:
        rows = self.conn.execute(
            "SELECT seq,event_json FROM offline_events WHERE node_id=? AND reconciled=0 ORDER BY seq",
            (node_id,),
        ).fetchall()
        for seq, payload in rows:
            yield seq, json.loads(payload)

    def mark_reconciled(self, seq: int) -> None:
        self.conn.execute("UPDATE offline_events SET reconciled=1 WHERE seq=?", (seq,))
        self.conn.commit()
