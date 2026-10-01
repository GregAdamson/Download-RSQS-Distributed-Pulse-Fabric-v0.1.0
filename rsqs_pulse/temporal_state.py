from __future__ import annotations
import json
import sqlite3
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any

class StateClass(str, Enum):
    OBSERVED = "observed"
    BELIEVED = "believed"
    PREDICTED = "predicted"
    DESIRED = "desired"
    COUNTERFACTUAL = "counterfactual"

@dataclass(frozen=True)
class TemporalFact:
    fact_id: str
    key: str
    value: Any
    state_class: StateClass
    unit: str | None
    source: str
    observed_at: int
    valid_from: int
    valid_until: int | None
    confidence: float
    evidence_ref: str | None
    jurisdiction: str | None
    owner: str | None
    privacy_scope: str
    supersedes: str | None

class TemporalStateStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS temporal_facts(
          fact_id TEXT PRIMARY KEY,
          key TEXT NOT NULL,
          value_json TEXT NOT NULL,
          state_class TEXT NOT NULL,
          unit TEXT,
          source TEXT NOT NULL,
          observed_at INTEGER NOT NULL,
          valid_from INTEGER NOT NULL,
          valid_until INTEGER,
          confidence REAL NOT NULL,
          evidence_ref TEXT,
          jurisdiction TEXT,
          owner TEXT,
          privacy_scope TEXT NOT NULL,
          supersedes TEXT
        )
        """)
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_temporal_facts_key_class_time ON temporal_facts(key,state_class,valid_from)")
        self.conn.commit()

    def assert_fact(
        self,
        key: str,
        value: Any,
        state_class: StateClass,
        source: str,
        *,
        unit: str | None = None,
        observed_at: int | None = None,
        valid_from: int | None = None,
        valid_until: int | None = None,
        confidence: float = 1.0,
        evidence_ref: str | None = None,
        jurisdiction: str | None = None,
        owner: str | None = None,
        privacy_scope: str = "local",
        supersedes: str | None = None,
    ) -> TemporalFact:
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence must be in [0,1]")
        now = int(time.time())
        observed_at = now if observed_at is None else int(observed_at)
        valid_from = observed_at if valid_from is None else int(valid_from)
        if valid_until is not None and int(valid_until) < valid_from:
            raise ValueError("valid_until must be >= valid_from")
        fact = TemporalFact(
            str(uuid.uuid4()), key, value, state_class, unit, source, observed_at,
            valid_from, None if valid_until is None else int(valid_until), confidence,
            evidence_ref, jurisdiction, owner, privacy_scope, supersedes,
        )
        self.conn.execute(
            """INSERT INTO temporal_facts(
               fact_id,key,value_json,state_class,unit,source,observed_at,valid_from,
               valid_until,confidence,evidence_ref,jurisdiction,owner,privacy_scope,supersedes
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                fact.fact_id, fact.key, json.dumps(value, sort_keys=True), fact.state_class.value,
                fact.unit, fact.source, fact.observed_at, fact.valid_from, fact.valid_until,
                fact.confidence, fact.evidence_ref, fact.jurisdiction, fact.owner,
                fact.privacy_scope, fact.supersedes,
            ),
        )
        self.conn.commit()
        return fact

    def active_at(self, key: str, when: int, state_class: StateClass = StateClass.OBSERVED) -> list[TemporalFact]:
        rows = self.conn.execute(
            """SELECT fact_id,value_json,unit,source,observed_at,valid_from,valid_until,
                      confidence,evidence_ref,jurisdiction,owner,privacy_scope,supersedes
               FROM temporal_facts
               WHERE key=? AND state_class=? AND valid_from<=?
                 AND (valid_until IS NULL OR valid_until>=?)
               ORDER BY valid_from DESC, observed_at DESC, rowid DESC""",
            (key, state_class.value, int(when), int(when)),
        ).fetchall()
        return [self._row(key, state_class, row) for row in rows]

    def latest(self, key: str, state_class: StateClass = StateClass.OBSERVED) -> TemporalFact | None:
        row = self.conn.execute(
            """SELECT fact_id,value_json,unit,source,observed_at,valid_from,valid_until,
                      confidence,evidence_ref,jurisdiction,owner,privacy_scope,supersedes
               FROM temporal_facts WHERE key=? AND state_class=?
               ORDER BY valid_from DESC, observed_at DESC, rowid DESC LIMIT 1""",
            (key, state_class.value),
        ).fetchone()
        return None if row is None else self._row(key, state_class, row)

    def history(self, key: str, state_class: StateClass | None = None) -> list[TemporalFact]:
        if state_class is None:
            rows = self.conn.execute(
                """SELECT state_class,fact_id,value_json,unit,source,observed_at,valid_from,
                          valid_until,confidence,evidence_ref,jurisdiction,owner,privacy_scope,supersedes
                   FROM temporal_facts WHERE key=? ORDER BY observed_at,rowid""",
                (key,),
            ).fetchall()
            return [self._row(key, StateClass(row[0]), row[1:]) for row in rows]
        rows = self.conn.execute(
            """SELECT fact_id,value_json,unit,source,observed_at,valid_from,valid_until,
                      confidence,evidence_ref,jurisdiction,owner,privacy_scope,supersedes
               FROM temporal_facts WHERE key=? AND state_class=? ORDER BY observed_at,rowid""",
            (key, state_class.value),
        ).fetchall()
        return [self._row(key, state_class, row) for row in rows]

    @staticmethod
    def _row(key: str, state_class: StateClass, row) -> TemporalFact:
        return TemporalFact(
            row[0], key, json.loads(row[1]), state_class, row[2], row[3], int(row[4]),
            int(row[5]), None if row[6] is None else int(row[6]), float(row[7]), row[8],
            row[9], row[10], row[11], row[12],
        )
