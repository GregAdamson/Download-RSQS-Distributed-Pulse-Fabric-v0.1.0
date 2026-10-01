from __future__ import annotations
import json
import sqlite3
from typing import Any, Dict

class IdempotencyJournal:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS idempotency_journal(
          operation_id TEXT PRIMARY KEY,
          status TEXT NOT NULL,
          result_json TEXT NOT NULL
        )
        """)
        self.conn.commit()

    def begin(self, operation_id: str) -> bool:
        try:
            self.conn.execute(
                "INSERT INTO idempotency_journal(operation_id,status,result_json) VALUES(?,?,?)",
                (operation_id, "pending", "{}"),
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def complete(self, operation_id: str, result: Dict[str, Any]) -> None:
        self.conn.execute(
            "UPDATE idempotency_journal SET status=?,result_json=? WHERE operation_id=?",
            ("complete", json.dumps(result, sort_keys=True), operation_id),
        )
        self.conn.commit()

    def fail(self, operation_id: str, result: Dict[str, Any]) -> None:
        self.conn.execute(
            "UPDATE idempotency_journal SET status=?,result_json=? WHERE operation_id=?",
            ("failed", json.dumps(result, sort_keys=True), operation_id),
        )
        self.conn.commit()

    def get(self, operation_id: str) -> tuple[str, Dict[str, Any]] | None:
        row = self.conn.execute(
            "SELECT status,result_json FROM idempotency_journal WHERE operation_id=?",
            (operation_id,),
        ).fetchone()
        return None if row is None else (row[0], json.loads(row[1]))

    def interrupted(self) -> list[str]:
        return [row[0] for row in self.conn.execute(
            "SELECT operation_id FROM idempotency_journal WHERE status='pending' ORDER BY operation_id"
        ).fetchall()]
