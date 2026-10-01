from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ReconciliationRecord:
    prediction_id: str
    expected_state: Any
    observed_state: Any
    error: Any
    lesson: str
    provenance: str


class LearningReconciliation:
    def __init__(self) -> None:
        self.records: list[ReconciliationRecord] = []

    def reconcile(
        self,
        prediction_id: str,
        expected_state: Any,
        observed_state: Any,
        lesson: str,
        provenance: str,
    ) -> ReconciliationRecord:
        record = ReconciliationRecord(
            prediction_id,
            expected_state,
            observed_state,
            expected_state != observed_state,
            lesson,
            provenance,
        )
        self.records.append(record)
        return record

    def history(self) -> tuple[ReconciliationRecord, ...]:
        return tuple(self.records)
