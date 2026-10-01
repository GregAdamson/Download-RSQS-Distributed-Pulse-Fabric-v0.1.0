from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import asdict, is_dataclass
from typing import Any, Mapping


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


class ResilienceStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS resilience_scenarios(
          scenario_id TEXT PRIMARY KEY,
          payload_json TEXT NOT NULL,
          created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS resilience_trajectories(
          trajectory_id TEXT PRIMARY KEY,
          payload_json TEXT NOT NULL,
          score REAL NOT NULL,
          validated INTEGER NOT NULL,
          created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS resilience_outcomes(
          outcome_id TEXT PRIMARY KEY,
          scenario_id TEXT,
          payload_json TEXT NOT NULL,
          created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS resilience_lessons(
          prediction_id TEXT PRIMARY KEY,
          expected_json TEXT NOT NULL,
          observed_json TEXT NOT NULL,
          error_json TEXT NOT NULL,
          lesson TEXT NOT NULL,
          provenance TEXT NOT NULL,
          created_at INTEGER NOT NULL
        );
        """)
        self.conn.commit()

    def record_scenario(self, scenario_id: str, payload: Any) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO resilience_scenarios(
               scenario_id,payload_json,created_at) VALUES(?,?,?)""",
            (scenario_id, json.dumps(_jsonable(payload), sort_keys=True), int(time.time())),
        )
        self.conn.commit()

    def record_trajectory(
        self,
        trajectory_id: str,
        payload: Any,
        *,
        score: float,
        validated: bool,
    ) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO resilience_trajectories(
               trajectory_id,payload_json,score,validated,created_at)
               VALUES(?,?,?,?,?)""",
            (
                trajectory_id,
                json.dumps(_jsonable(payload), sort_keys=True),
                float(score),
                int(bool(validated)),
                int(time.time()),
            ),
        )
        self.conn.commit()

    def record_outcome(
        self,
        outcome_id: str,
        payload: Any,
        *,
        scenario_id: str | None = None,
    ) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO resilience_outcomes(
               outcome_id,scenario_id,payload_json,created_at) VALUES(?,?,?,?)""",
            (
                outcome_id,
                scenario_id,
                json.dumps(_jsonable(payload), sort_keys=True),
                int(time.time()),
            ),
        )
        self.conn.commit()

    def record_lesson(
        self,
        prediction_id: str,
        expected: Any,
        observed: Any,
        error: Any,
        lesson: str,
        provenance: str,
    ) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO resilience_lessons(
               prediction_id,expected_json,observed_json,error_json,lesson,provenance,created_at)
               VALUES(?,?,?,?,?,?,?)""",
            (
                prediction_id,
                json.dumps(_jsonable(expected), sort_keys=True),
                json.dumps(_jsonable(observed), sort_keys=True),
                json.dumps(_jsonable(error), sort_keys=True),
                lesson,
                provenance,
                int(time.time()),
            ),
        )
        self.conn.commit()

    def fetch_scenario(self, scenario_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT payload_json FROM resilience_scenarios WHERE scenario_id=?",
            (scenario_id,),
        ).fetchone()
        return None if row is None else json.loads(row[0])

    def fetch_trajectory(self, trajectory_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """SELECT payload_json,score,validated
               FROM resilience_trajectories WHERE trajectory_id=?""",
            (trajectory_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "payload": json.loads(row[0]),
            "score": float(row[1]),
            "validated": bool(row[2]),
        }

    def fetch_outcomes(self, scenario_id: str | None = None) -> list[dict[str, Any]]:
        if scenario_id is None:
            rows = self.conn.execute(
                "SELECT outcome_id,scenario_id,payload_json FROM resilience_outcomes ORDER BY rowid"
            ).fetchall()
        else:
            rows = self.conn.execute(
                """SELECT outcome_id,scenario_id,payload_json
                   FROM resilience_outcomes WHERE scenario_id=? ORDER BY rowid""",
                (scenario_id,),
            ).fetchall()
        return [
            {
                "outcome_id": row[0],
                "scenario_id": row[1],
                "payload": json.loads(row[2]),
            }
            for row in rows
        ]

    def fetch_lessons(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """SELECT prediction_id,expected_json,observed_json,error_json,lesson,provenance
               FROM resilience_lessons ORDER BY rowid"""
        ).fetchall()
        return [
            {
                "prediction_id": row[0],
                "expected": json.loads(row[1]),
                "observed": json.loads(row[2]),
                "error": json.loads(row[3]),
                "lesson": row[4],
                "provenance": row[5],
            }
            for row in rows
        ]
