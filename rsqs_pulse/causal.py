from __future__ import annotations
import json
import sqlite3
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List


@dataclass(frozen=True)
class TransitionEvidence:
    evidence_id: str
    cause: str
    action: str
    context: Dict[str, Any]
    before: Dict[str, Any]
    after: Dict[str, Any]
    supports: bool
    confidence: float
    source: str


@dataclass(frozen=True)
class CausalAssessment:
    cause: str
    action: str
    support: float
    oppose: float
    confidence: float
    observations: int


class CausalMemory:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS causal_evidence(
          evidence_id TEXT PRIMARY KEY,
          cause TEXT NOT NULL,
          action TEXT NOT NULL,
          context_json TEXT NOT NULL,
          before_json TEXT NOT NULL,
          after_json TEXT NOT NULL,
          supports INTEGER NOT NULL,
          confidence REAL NOT NULL,
          source TEXT NOT NULL,
          observed_at INTEGER NOT NULL
        )
        """)
        self.conn.commit()

    def observe(
        self, cause: str, action: str, before: Dict[str, Any], after: Dict[str, Any],
        source: str, context: Dict[str, Any] | None = None, supports: bool = True,
        confidence: float = 1.0,
    ) -> TransitionEvidence:
        confidence = max(0.0, min(1.0, confidence))
        item = TransitionEvidence(
            str(uuid.uuid4()), cause, action, context or {}, before, after,
            supports, confidence, source,
        )
        self.conn.execute(
            """INSERT INTO causal_evidence
               (evidence_id,cause,action,context_json,before_json,after_json,supports,confidence,source,observed_at)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (
                item.evidence_id, cause, action, json.dumps(item.context, sort_keys=True),
                json.dumps(before, sort_keys=True), json.dumps(after, sort_keys=True),
                int(supports), confidence, source, int(time.time()),
            ),
        )
        self.conn.commit()
        return item

    def assess(self, cause: str, action: str) -> CausalAssessment:
        rows = self.conn.execute(
            "SELECT supports,confidence FROM causal_evidence WHERE cause=? AND action=?",
            (cause, action),
        ).fetchall()
        support = sum(float(c) for s, c in rows if s)
        oppose = sum(float(c) for s, c in rows if not s)
        total = support + oppose
        confidence = 0.0 if total == 0 else support / total
        return CausalAssessment(cause, action, support, oppose, confidence, len(rows))
