from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, Tuple


@dataclass(frozen=True)
class SovereignCell:
    cell_id: str
    cell_type: str
    authority_scope: FrozenSet[str] = frozenset()
    capabilities: FrozenSet[str] = frozenset()
    resources: Dict[str, float] = field(default_factory=dict)
    constraints: Tuple[str, ...] = ()
    relationships: Tuple[str, ...] = ()

    def can(self, capability: str) -> bool:
        return capability in self.capabilities

    def authorised_for(self, scope: str) -> bool:
        return scope in self.authority_scope or "*" in self.authority_scope

    def describe(self) -> Dict[str, Any]:
        return {
            "cell_id": self.cell_id,
            "cell_type": self.cell_type,
            "authority_scope": sorted(self.authority_scope),
            "capabilities": sorted(self.capabilities),
            "resources": dict(sorted(self.resources.items())),
            "constraints": list(self.constraints),
            "relationships": list(self.relationships),
        }


class SovereignCellRegistry:
    def __init__(self) -> None:
        self._cells: Dict[str, SovereignCell] = {}

    def register(self, cell: SovereignCell) -> None:
        self._cells[cell.cell_id] = cell

    def discover(self, capability: str, scope: str | None = None) -> list[SovereignCell]:
        cells = [
            cell for cell in self._cells.values()
            if cell.can(capability) and (scope is None or cell.authorised_for(scope))
        ]
        return sorted(cells, key=lambda cell: cell.cell_id)
