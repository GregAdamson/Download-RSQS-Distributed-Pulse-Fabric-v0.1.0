from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Sequence

from .dependency_graph import DependencyGraph, ResourceRequirement
from .resource_state import ResourceInventory, ResourceLot
from .substitution import SubstitutionGraph


@dataclass(frozen=True)
class ResourceShock:
    resource: str
    fraction_lost: float = 1.0
    unit: str | None = None
    location: str | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.fraction_lost <= 1.0:
            raise ValueError("fraction_lost must be in [0,1]")


@dataclass(frozen=True)
class RecoveryTarget:
    capability: str
    priority: int = 0


@dataclass(frozen=True)
class NetworkAllocation:
    capability: str
    requested_resource: str
    supplied_resource: str
    supplied_quantity: float
    equivalent_quantity: float
    ratio: float
    unit: str
    location: str | None


@dataclass(frozen=True)
class CapabilityRecovery:
    capability: str
    recovered: bool
    reason: str


@dataclass(frozen=True)
class NetworkResiliencePlan:
    viable: bool
    recovered_targets: tuple[str, ...]
    failed_targets: tuple[str, ...]
    operational_capabilities: tuple[str, ...]
    allocations: tuple[NetworkAllocation, ...]
    unresolved: tuple[tuple[str, ResourceRequirement], ...]
    shocks: tuple[ResourceShock, ...]


class _ResourcePool:
    def __init__(self, lots: Iterable[ResourceLot], shocks: Sequence[ResourceShock]) -> None:
        self._lots: Dict[str, ResourceLot] = {lot.lot_id: lot for lot in lots}
        self.remaining: Dict[str, float] = {}
        for lot in self._lots.values():
            quantity = lot.quantity
            for shock in shocks:
                if shock.resource != lot.resource:
                    continue
                if shock.unit is not None and shock.unit != lot.unit:
                    continue
                if shock.location is not None and shock.location != lot.location:
                    continue
                quantity *= 1.0 - shock.fraction_lost
            self.remaining[lot.lot_id] = max(0.0, quantity)

    def clone(self) -> "_ResourcePool":
        clone = object.__new__(_ResourcePool)
        clone._lots = self._lots
        clone.remaining = dict(self.remaining)
        return clone

    def consume(
        self,
        resource: str,
        unit: str,
        quantity: float,
        *,
        location: str | None = None,
        minimum_quality: float = 0.0,
    ) -> float:
        if quantity <= 0:
            return 0.0
        candidates = [
            lot for lot in self._lots.values()
            if lot.resource == resource
            and lot.unit == unit
            and lot.quality >= minimum_quality
            and (location is None or lot.location == location)
            and self.remaining.get(lot.lot_id, 0.0) > 0
        ]
        candidates.sort(key=lambda lot: (-lot.quality, lot.lead_time_days, lot.lot_id))
        needed = quantity
        consumed = 0.0
        for lot in candidates:
            available = self.remaining[lot.lot_id]
            used = min(available, needed)
            self.remaining[lot.lot_id] -= used
            consumed += used
            needed -= used
            if needed <= 1e-12:
                break
        return consumed


@dataclass
class _PlanningState:
    pool: _ResourcePool
    operational: set[str]
    allocations: List[NetworkAllocation]
    unresolved: List[tuple[str, ResourceRequirement]]

    def clone(self) -> "_PlanningState":
        return _PlanningState(
            self.pool.clone(),
            set(self.operational),
            list(self.allocations),
            list(self.unresolved),
        )


class NetworkResiliencePlanner:
    def __init__(self, substitutions: SubstitutionGraph) -> None:
        self.substitutions = substitutions

    def plan(
        self,
        targets: Iterable[RecoveryTarget],
        graph: DependencyGraph,
        inventory: ResourceInventory,
        shocks: Iterable[ResourceShock] = (),
    ) -> NetworkResiliencePlan:
        shock_tuple = tuple(sorted(
            shocks,
            key=lambda x: (x.resource, x.unit or "", x.location or "", x.fraction_lost),
        ))
        lots: List[ResourceLot] = []
        rows = inventory.conn.execute(
            """SELECT lot_id,resource,quantity,unit,location,quality,owner,replenishment_per_day,
                      lead_time_days,observed_at,source
               FROM resource_lots ORDER BY resource,unit,location,lot_id"""
        ).fetchall()
        lots = [ResourceLot(*row) for row in rows]
        state = _PlanningState(_ResourcePool(lots, shock_tuple), set(), [], [])

        ordered_targets = sorted(targets, key=lambda target: (-target.priority, target.capability))
        recovered: List[str] = []
        failed: List[str] = []

        for target in ordered_targets:
            trial = state.clone()
            if self._ensure_capability(target.capability, graph, trial, set()):
                state = trial
                recovered.append(target.capability)
            else:
                failed.append(target.capability)

        return NetworkResiliencePlan(
            viable=not failed,
            recovered_targets=tuple(recovered),
            failed_targets=tuple(failed),
            operational_capabilities=tuple(sorted(state.operational)),
            allocations=tuple(state.allocations),
            unresolved=tuple(state.unresolved),
            shocks=shock_tuple,
        )

    def _ensure_capability(
        self,
        capability: str,
        graph: DependencyGraph,
        state: _PlanningState,
        stack: set[str],
    ) -> bool:
        if capability in state.operational:
            return True
        if capability in stack:
            return False
        stack = set(stack)
        stack.add(capability)

        for dependency in sorted(
            graph.capability_requirements.get(capability, []),
            key=lambda item: item.capability,
        ):
            if not dependency.critical:
                continue
            if not self._ensure_capability(dependency.capability, graph, state, stack):
                return False

        for requirement in sorted(
            graph.resource_requirements.get(capability, []),
            key=lambda item: (
                item.resource, item.unit, item.location or "",
                item.minimum_quality, item.quantity,
            ),
        ):
            if not requirement.critical:
                continue
            if not self._satisfy_requirement(capability, requirement, state):
                state.unresolved.append((capability, requirement))
                return False

        state.operational.add(capability)
        return True

    def _satisfy_requirement(
        self,
        capability: str,
        requirement: ResourceRequirement,
        state: _PlanningState,
    ) -> bool:
        original = state.pool.consume(
            requirement.resource,
            requirement.unit,
            requirement.quantity,
            location=requirement.location,
            minimum_quality=requirement.minimum_quality,
        )
        if original > 0:
            state.allocations.append(
                NetworkAllocation(
                    capability=capability,
                    requested_resource=requirement.resource,
                    supplied_resource=requirement.resource,
                    supplied_quantity=original,
                    equivalent_quantity=original,
                    ratio=1.0,
                    unit=requirement.unit,
                    location=requirement.location,
                )
            )

        remaining = max(0.0, requirement.quantity - original)
        if remaining <= 1e-12:
            return True

        for substitute in self.substitutions.alternatives(requirement.resource):
            substitute_needed = remaining * substitute.ratio
            used = state.pool.consume(
                substitute.substitute,
                requirement.unit,
                substitute_needed,
                location=requirement.location,
                minimum_quality=requirement.minimum_quality,
            )
            if used <= 0:
                continue
            equivalent = used / substitute.ratio
            state.allocations.append(
                NetworkAllocation(
                    capability=capability,
                    requested_resource=requirement.resource,
                    supplied_resource=substitute.substitute,
                    supplied_quantity=used,
                    equivalent_quantity=equivalent,
                    ratio=substitute.ratio,
                    unit=requirement.unit,
                    location=requirement.location,
                )
            )
            remaining = max(0.0, remaining - equivalent)
            if remaining <= 1e-12:
                return True
        return False
