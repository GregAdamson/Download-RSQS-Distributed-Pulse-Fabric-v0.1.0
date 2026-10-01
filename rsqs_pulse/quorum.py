from __future__ import annotations
from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class QuorumRule:
    minimum_approvals: int
    minimum_total: int = 1

    def decide(self, votes: Dict[str, bool]) -> bool:
        if len(votes) < self.minimum_total:
            return False
        return sum(1 for value in votes.values() if value) >= self.minimum_approvals
