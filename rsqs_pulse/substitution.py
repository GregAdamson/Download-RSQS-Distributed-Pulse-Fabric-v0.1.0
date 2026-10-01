from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple


@dataclass(frozen=True)
class Substitution:
    resource: str
    substitute: str
    ratio: float
    constraints: Dict[str, str]


class SubstitutionGraph:
    def __init__(self) -> None:
        self._edges: Dict[str, List[Substitution]] = {}

    def add(self, substitution: Substitution) -> None:
        if substitution.ratio <= 0:
            raise ValueError("ratio must be positive")
        self._edges.setdefault(substitution.resource, []).append(substitution)

    def alternatives(self, resource: str, required: Dict[str, str] | None = None) -> List[Substitution]:
        required = required or {}
        result = [
            item for item in self._edges.get(resource, [])
            if all(item.constraints.get(k) == v for k, v in required.items())
        ]
        return sorted(result, key=lambda item: (item.ratio, item.substitute))
