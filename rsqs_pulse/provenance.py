from __future__ import annotations
import hashlib
import json
import sqlite3
import time
from typing import Any, Dict


class ProvenanceLedger:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS provenance(
          seq INTEGER PRIMARY KEY AUTOINCREMENT,
          ts INTEGER NOT NULL,
          kind TEXT NOT NULL,
          subject TEXT NOT NULL,
          payload_json TEXT NOT NULL,
          prev_hash TEXT NOT NULL,
          entry_hash TEXT NOT NULL UNIQUE
        )
        """)
        self.conn.commit()

    def append(self, kind: str, subject: str, payload: Dict[str, Any]) -> str:
        row = self.conn.execute("SELECT entry_hash FROM provenance ORDER BY seq DESC LIMIT 1").fetchone()
        prev = row[0] if row else "0" * 64
        ts = int(time.time())
        body = json.dumps(
            {"ts": ts, "kind": kind, "subject": subject, "payload": payload, "prev_hash": prev},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        digest = hashlib.sha256(body.encode("ascii")).hexdigest()
        self.conn.execute(
            "INSERT INTO provenance(ts,kind,subject,payload_json,prev_hash,entry_hash) VALUES(?,?,?,?,?,?)",
            (ts, kind, subject, json.dumps(payload, sort_keys=True), prev, digest),
        )
        self.conn.commit()
        return digest

    def verify(self) -> bool:
        prev = "0" * 64
        rows = self.conn.execute(
            "SELECT ts,kind,subject,payload_json,prev_hash,entry_hash FROM provenance ORDER BY seq"
        ).fetchall()
        for ts, kind, subject, payload_json, recorded_prev, entry_hash in rows:
            if recorded_prev != prev:
                return False
            payload = json.loads(payload_json)
            body = json.dumps(
                {"ts": ts, "kind": kind, "subject": subject, "payload": payload, "prev_hash": prev},
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            )
            if hashlib.sha256(body.encode("ascii")).hexdigest() != entry_hash:
                return False
            prev = entry_hash
        return True
