from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Iterable, List


@dataclass(frozen=True)
class EvidenceClaim:
    source: str
    proposition: str
    supports: bool
    confidence: float
    evidence_ref: str


@dataclass(frozen=True)
class OracleAssessment:
    proposition: str
    support_weight: float
    oppose_weight: float
    unresolved_weight: float
    evidence: tuple[EvidenceClaim, ...]


class DistributedOracle:
    def assess(self, proposition: str, claims: Iterable[EvidenceClaim]) -> OracleAssessment:
        relevant: List[EvidenceClaim] = [c for c in claims if c.proposition == proposition]
        support = sum(max(0.0, min(1.0, c.confidence)) for c in relevant if c.supports)
        oppose = sum(max(0.0, min(1.0, c.confidence)) for c in relevant if not c.supports)
        total = support + oppose
        unresolved = 1.0 if total == 0 else abs(support - oppose) / max(total, 1.0)
        return OracleAssessment(proposition, support, oppose, unresolved, tuple(relevant))
