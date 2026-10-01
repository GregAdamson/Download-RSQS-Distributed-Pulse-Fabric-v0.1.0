from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any

from .resilience_store import ResilienceStore


@dataclass(frozen=True)
class ReconciliationRecord:
    prediction_id: str
    expected_state: Any
    observed_state: Any
    error: Any
    lesson: str
    provenance: str


def _error_vector(expected: Any, observed: Any) -> Any:
    if isinstance(expected, dict) and isinstance(observed, dict):
        keys = sorted(set(expected) | set(observed))
        result = {}
        for key in keys:
            left = expected.get(key)
            right = observed.get(key)
            if isinstance(left, (int, float)) and isinstance(right, (int, float)):
                result[key] = right - left
            else:
                result[key] = left != right
        return result
    if isinstance(expected, (int, float)) and isinstance(observed, (int, float)):
        return observed - expected
    return expected != observed


class LearningReconciliation:
    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self.records: list[ReconciliationRecord] = []
        self.store = ResilienceStore(conn) if conn is not None else None
        if self.store is not None:
            for item in self.store.fetch_lessons():
                self.records.append(
                    ReconciliationRecord(
                        item["prediction_id"],
                        item["expected"],
                        item["observed"],
                        item["error"],
                        item["lesson"],
                        item["provenance"],
                    )
                )

    def reconcile(
        self,
        prediction_id: str,
        expected_state: Any,
        observed_state: Any,
        lesson: str,
        provenance: str,
    ) -> ReconciliationRecord:
        error = _error_vector(expected_state, observed_state)
        record = ReconciliationRecord(
            prediction_id,
            expected_state,
            observed_state,
            error,
            lesson,
            provenance,
        )
        self.records = [
            existing for existing in self.records
            if existing.prediction_id != prediction_id
        ]
        self.records.append(record)
        if self.store is not None:
            self.store.record_lesson(
                prediction_id,
                expected_state,
                observed_state,
                error,
                lesson,
                provenance,
            )
        return record

    def history(self) -> tuple[ReconciliationRecord, ...]:
        return tuple(self.records)
