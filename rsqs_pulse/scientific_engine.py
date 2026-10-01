from __future__ import annotations
import json
import sqlite3
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Iterable

class TrialKind(str, Enum):
    OBSERVATIONAL = "observational"
    INTERVENTION = "intervention"

@dataclass(frozen=True)
class Hypothesis:
    hypothesis_id: str
    proposition: str
    cause: str
    effect: str

@dataclass(frozen=True)
class TrialRecord:
    trial_id: str
    hypothesis_id: str
    kind: TrialKind
    before: Dict[str, Any]
    after: Dict[str, Any]
    intervention: Dict[str, Any]
    controls: Dict[str, Any]
    confounders: tuple[str, ...]
    supports: bool
    confidence: float
    source: str
    observed_at: int

@dataclass(frozen=True)
class ReplicationSummary:
    hypothesis_id: str
    interventions: int
    observations: int
    support_weight: float
    oppose_weight: float
    support_ratio: float
    replicated: bool

class ScientificEngine:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS hypotheses(
          hypothesis_id TEXT PRIMARY KEY,
          proposition TEXT NOT NULL,
          cause TEXT NOT NULL,
          effect TEXT NOT NULL,
          created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS scientific_trials(
          trial_id TEXT PRIMARY KEY,
          hypothesis_id TEXT NOT NULL,
          kind TEXT NOT NULL,
          before_json TEXT NOT NULL,
          after_json TEXT NOT NULL,
          intervention_json TEXT NOT NULL,
          controls_json TEXT NOT NULL,
          confounders_json TEXT NOT NULL,
          supports INTEGER NOT NULL,
          confidence REAL NOT NULL,
          source TEXT NOT NULL,
          observed_at INTEGER NOT NULL,
          FOREIGN KEY(hypothesis_id) REFERENCES hypotheses(hypothesis_id)
        );
        """)
        self.conn.commit()

    def register_hypothesis(self, proposition: str, cause: str, effect: str, hypothesis_id: str | None = None) -> Hypothesis:
        hypothesis_id = hypothesis_id or str(uuid.uuid4())
        self.conn.execute(
            "INSERT INTO hypotheses(hypothesis_id,proposition,cause,effect,created_at) VALUES(?,?,?,?,?)",
            (hypothesis_id, proposition, cause, effect, int(time.time())),
        )
        self.conn.commit()
        return Hypothesis(hypothesis_id, proposition, cause, effect)

    def record_trial(
        self,
        hypothesis_id: str,
        kind: TrialKind,
        before: Dict[str, Any],
        after: Dict[str, Any],
        *,
        intervention: Dict[str, Any] | None = None,
        controls: Dict[str, Any] | None = None,
        confounders: Iterable[str] = (),
        supports: bool,
        confidence: float,
        source: str,
        observed_at: int | None = None,
    ) -> TrialRecord:
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence must be in [0,1]")
        if kind == TrialKind.INTERVENTION and not intervention:
            raise ValueError("intervention trials require an explicit intervention")
        if self.conn.execute("SELECT 1 FROM hypotheses WHERE hypothesis_id=?", (hypothesis_id,)).fetchone() is None:
            raise KeyError(hypothesis_id)
        trial = TrialRecord(
            str(uuid.uuid4()), hypothesis_id, kind, dict(before), dict(after),
            dict(intervention or {}), dict(controls or {}), tuple(sorted(set(confounders))),
            bool(supports), confidence, source,
            int(time.time()) if observed_at is None else int(observed_at),
        )
        self.conn.execute(
            """INSERT INTO scientific_trials(
               trial_id,hypothesis_id,kind,before_json,after_json,intervention_json,
               controls_json,confounders_json,supports,confidence,source,observed_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                trial.trial_id, trial.hypothesis_id, trial.kind.value,
                json.dumps(trial.before, sort_keys=True), json.dumps(trial.after, sort_keys=True),
                json.dumps(trial.intervention, sort_keys=True), json.dumps(trial.controls, sort_keys=True),
                json.dumps(trial.confounders), int(trial.supports), trial.confidence,
                trial.source, trial.observed_at,
            ),
        )
        self.conn.commit()
        return trial

    def summarize(self, hypothesis_id: str, minimum_interventions: int = 2) -> ReplicationSummary:
        rows = self.conn.execute(
            "SELECT kind,supports,confidence FROM scientific_trials WHERE hypothesis_id=?",
            (hypothesis_id,),
        ).fetchall()
        interventions = sum(1 for kind, _, _ in rows if kind == TrialKind.INTERVENTION.value)
        observations = sum(1 for kind, _, _ in rows if kind == TrialKind.OBSERVATIONAL.value)
        support = sum(float(conf) for _, supports, conf in rows if supports)
        oppose = sum(float(conf) for _, supports, conf in rows if not supports)
        total = support + oppose
        ratio = 0.0 if total == 0 else support / total
        replicated = interventions >= minimum_interventions and support > oppose
        return ReplicationSummary(hypothesis_id, interventions, observations, support, oppose, ratio, replicated)

    def trial_history(self, hypothesis_id: str) -> list[TrialRecord]:
        rows = self.conn.execute(
            """SELECT trial_id,kind,before_json,after_json,intervention_json,controls_json,
                      confounders_json,supports,confidence,source,observed_at
               FROM scientific_trials WHERE hypothesis_id=? ORDER BY observed_at,trial_id""",
            (hypothesis_id,),
        ).fetchall()
        return [
            TrialRecord(
                row[0], hypothesis_id, TrialKind(row[1]), json.loads(row[2]), json.loads(row[3]),
                json.loads(row[4]), json.loads(row[5]), tuple(json.loads(row[6])),
                bool(row[7]), float(row[8]), row[9], int(row[10]),
            )
            for row in rows
        ]
