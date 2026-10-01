from __future__ import annotations
import json
import sqlite3
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict

class LedgerState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"
    UNKNOWN = "unknown"
    RETRY_ELIGIBLE = "retry_eligible"
    ESCALATED = "escalated"

_ALLOWED = {
    LedgerState.PENDING: {LedgerState.RUNNING, LedgerState.FAILED, LedgerState.ESCALATED},
    LedgerState.RUNNING: {LedgerState.COMPLETE, LedgerState.FAILED, LedgerState.UNKNOWN},
    LedgerState.UNKNOWN: {LedgerState.COMPLETE, LedgerState.FAILED, LedgerState.RETRY_ELIGIBLE, LedgerState.ESCALATED},
    LedgerState.RETRY_ELIGIBLE: {LedgerState.RUNNING, LedgerState.ESCALATED},
    LedgerState.COMPLETE: set(),
    LedgerState.FAILED: set(),
    LedgerState.ESCALATED: set(),
}

@dataclass(frozen=True)
class OperationRecord:
    operation_id: str
    capability: str
    target: str
    state: LedgerState
    args: Dict[str, Any]
    result: Dict[str, Any]
    evidence: Dict[str, Any]
    authority_ref: str | None
    created_at: int
    updated_at: int
    lease_until: int | None
    attempts: int

class OperationLedger:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS operation_ledger(
          operation_id TEXT PRIMARY KEY,
          capability TEXT NOT NULL,
          target TEXT NOT NULL,
          state TEXT NOT NULL,
          args_json TEXT NOT NULL,
          result_json TEXT NOT NULL,
          evidence_json TEXT NOT NULL,
          authority_ref TEXT,
          created_at INTEGER NOT NULL,
          updated_at INTEGER NOT NULL,
          lease_until INTEGER,
          attempts INTEGER NOT NULL
        )
        """)
        self.conn.commit()

    def create(self, operation_id: str, capability: str, target: str, args: Dict[str, Any], authority_ref: str | None = None, now: int | None = None) -> OperationRecord:
        now = int(time.time()) if now is None else int(now)
        self.conn.execute(
            """INSERT INTO operation_ledger(operation_id,capability,target,state,args_json,result_json,
               evidence_json,authority_ref,created_at,updated_at,lease_until,attempts)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (operation_id, capability, target, LedgerState.PENDING.value, json.dumps(args, sort_keys=True),
             "{}", "{}", authority_ref, now, now, None, 0),
        )
        self.conn.commit()
        return self.get(operation_id)

    def get(self, operation_id: str) -> OperationRecord:
        row = self.conn.execute(
            """SELECT capability,target,state,args_json,result_json,evidence_json,authority_ref,
                      created_at,updated_at,lease_until,attempts
               FROM operation_ledger WHERE operation_id=?""",
            (operation_id,),
        ).fetchone()
        if row is None:
            raise KeyError(operation_id)
        return OperationRecord(
            operation_id, row[0], row[1], LedgerState(row[2]), json.loads(row[3]),
            json.loads(row[4]), json.loads(row[5]), row[6], int(row[7]), int(row[8]),
            None if row[9] is None else int(row[9]), int(row[10]),
        )

    def transition(self, operation_id: str, new_state: LedgerState, *, result: Dict[str, Any] | None = None, evidence: Dict[str, Any] | None = None, now: int | None = None, lease_until: int | None = None) -> OperationRecord:
        current = self.get(operation_id)
        if new_state not in _ALLOWED[current.state]:
            raise ValueError(f"invalid operation transition: {current.state.value}->{new_state.value}")
        now = int(time.time()) if now is None else int(now)
        attempts = current.attempts + (1 if new_state == LedgerState.RUNNING else 0)
        self.conn.execute(
            """UPDATE operation_ledger SET state=?,result_json=?,evidence_json=?,updated_at=?,
               lease_until=?,attempts=? WHERE operation_id=?""",
            (
                new_state.value,
                json.dumps(current.result if result is None else result, sort_keys=True),
                json.dumps(current.evidence if evidence is None else evidence, sort_keys=True),
                now, lease_until, attempts, operation_id,
            ),
        )
        self.conn.commit()
        return self.get(operation_id)

    def start(self, operation_id: str, lease_seconds: int, now: int | None = None) -> OperationRecord:
        now = int(time.time()) if now is None else int(now)
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        return self.transition(operation_id, LedgerState.RUNNING, now=now, lease_until=now + lease_seconds)

    def expire_running(self, now: int | None = None) -> list[str]:
        now = int(time.time()) if now is None else int(now)
        rows = self.conn.execute(
            """SELECT operation_id FROM operation_ledger
               WHERE state=? AND lease_until IS NOT NULL AND lease_until<? ORDER BY operation_id""",
            (LedgerState.RUNNING.value, now),
        ).fetchall()
        changed = []
        for (operation_id,) in rows:
            self.transition(
                operation_id, LedgerState.UNKNOWN, now=now, lease_until=None,
                evidence={"reason": "execution lease expired; external outcome requires reconciliation"},
            )
            changed.append(operation_id)
        return changed

    def unresolved(self) -> list[OperationRecord]:
        rows = self.conn.execute(
            """SELECT operation_id FROM operation_ledger
               WHERE state IN (?,?,?,?) ORDER BY created_at,operation_id""",
            (
                LedgerState.PENDING.value, LedgerState.RUNNING.value,
                LedgerState.UNKNOWN.value, LedgerState.RETRY_ELIGIBLE.value,
            ),
        ).fetchall()
        return [self.get(row[0]) for row in rows]
