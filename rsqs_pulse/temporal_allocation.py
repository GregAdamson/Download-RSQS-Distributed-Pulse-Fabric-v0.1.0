from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple

from .dependency_graph import CapabilityRequirement, DependencyGraph, ResourceRequirement
from .resource_state import ResourceInventory
from .substitution import SubstitutionGraph


@dataclass(frozen=True)
class Replenishment:
    period: int
    resource: str
    quantity: float
    unit: str
    location: str

    def __post_init__(self) -> None:
        if self.period < 0 or self.quantity < 0:
            raise ValueError("period and quantity must be non-negative")


@dataclass(frozen=True)
class TransportLink:
    source: str
    destination: str
    resource: str
    unit: str
    capacity_per_period: float
    lead_time_periods: int
    loss_fraction: float = 0.0

    def __post_init__(self) -> None:
        if self.capacity_per_period < 0 or self.lead_time_periods < 0:
            raise ValueError("transport capacity and lead time must be non-negative")
        if not 0.0 <= self.loss_fraction < 1.0:
            raise ValueError("loss_fraction must be in [0,1)")


@dataclass(frozen=True)
class CapabilityDemand:
    capability: str
    periods: tuple[int, ...]
    priority: int = 0
    minimum_service: float = 1.0

    def __post_init__(self) -> None:
        if any(period < 0 for period in self.periods):
            raise ValueError("periods must be non-negative")
        if not 0.0 < self.minimum_service <= 1.0:
            raise ValueError("minimum_service must be in (0,1]")


@dataclass(frozen=True)
class TemporalAllocation:
    period: int
    capability: str
    requested_resource: str
    supplied_resource: str
    quantity: float
    equivalent_quantity: float
    unit: str
    location: str | None
    source: str


@dataclass(frozen=True)
class Transfer:
    depart_period: int
    arrive_period: int
    source: str
    destination: str
    resource: str
    unit: str
    shipped_quantity: float
    delivered_quantity: float


@dataclass(frozen=True)
class PeriodResult:
    period: int
    operational_capabilities: tuple[str, ...]
    failed_capabilities: tuple[str, ...]
    allocations: tuple[TemporalAllocation, ...]
    transfers_departed: tuple[Transfer, ...]
    transfers_arrived: tuple[Transfer, ...]
    ending_stock: tuple[tuple[str, str, str, float], ...]


@dataclass(frozen=True)
class TemporalAllocationPlan:
    viable: bool
    periods: tuple[PeriodResult, ...]
    first_failure_period: int | None
    failed_demands: tuple[tuple[int, str], ...]


class TemporalAllocationPlanner:
    """
    Deterministic multi-period allocator.

    This is not a global mathematical optimizer. It is an auditable
    priority-ordered planner that:
      * carries stock between periods,
      * applies scheduled replenishment,
      * consumes resources when capabilities operate,
      * shares upstream capability costs within a period,
      * respects substitution ratios,
      * schedules transport subject to lead time and capacity,
      * prepositions stock using known future demand.
    """

    def __init__(self, substitutions: SubstitutionGraph) -> None:
        self.substitutions = substitutions

    def plan(
        self,
        horizon: int,
        demands: Iterable[CapabilityDemand],
        graph: DependencyGraph,
        inventory: ResourceInventory,
        replenishments: Iterable[Replenishment] = (),
        transport_links: Iterable[TransportLink] = (),
    ) -> TemporalAllocationPlan:
        if horizon <= 0:
            raise ValueError("horizon must be positive")

        demand_list = tuple(sorted(
            demands,
            key=lambda d: (-d.priority, d.capability, d.periods),
        ))
        replenishment_map: Dict[int, List[Replenishment]] = {}
        for item in replenishments:
            if item.period >= horizon:
                continue
            replenishment_map.setdefault(item.period, []).append(item)

        links = tuple(sorted(
            transport_links,
            key=lambda link: (
                link.resource, link.unit, link.source, link.destination,
                link.lead_time_periods, link.capacity_per_period,
            ),
        ))
        link_capacity_used: Dict[tuple[int, int], float] = {}
        arrivals: Dict[int, List[Transfer]] = {}

        stock: Dict[tuple[str, str, str], float] = {}
        for row in inventory.conn.execute(
            "SELECT resource,unit,location,SUM(quantity) FROM resource_lots GROUP BY resource,unit,location"
        ).fetchall():
            stock[(row[0], row[1], row[2])] = float(row[3])

        results: List[PeriodResult] = []
        failed_demands: List[tuple[int, str]] = []

        for period in range(horizon):
            arrived = tuple(arrivals.pop(period, []))
            for transfer in arrived:
                key = (transfer.resource, transfer.unit, transfer.destination)
                stock[key] = stock.get(key, 0.0) + transfer.delivered_quantity

            for item in sorted(
                replenishment_map.get(period, []),
                key=lambda x: (x.resource, x.unit, x.location, x.quantity),
            ):
                key = (item.resource, item.unit, item.location)
                stock[key] = stock.get(key, 0.0) + item.quantity

            self._preposition_for_future(
                period, horizon, demand_list, graph, stock, links,
                link_capacity_used, arrivals,
            )

            period_demands = [
                demand for demand in demand_list if period in demand.periods
            ]
            service_levels: Dict[str, float] = {}
            failed: set[str] = set()
            allocations: List[TemporalAllocation] = []

            for demand in period_demands:
                trial_stock = dict(stock)
                trial_service_levels = dict(service_levels)
                trial_allocations = list(allocations)
                if self._ensure_capability(
                    period, demand.capability, demand.minimum_service, graph, trial_stock,
                    trial_service_levels, trial_allocations, set(),
                ):
                    stock = trial_stock
                    service_levels = trial_service_levels
                    allocations = trial_allocations
                else:
                    failed.add(demand.capability)
                    failed_demands.append((period, demand.capability))

            departed = []
            for arrival_period, scheduled in arrivals.items():
                for transfer in scheduled:
                    if transfer.depart_period == period:
                        departed.append(transfer)

            results.append(
                PeriodResult(
                    period=period,
                    operational_capabilities=tuple(sorted(service_levels)),
                    failed_capabilities=tuple(sorted(failed)),
                    allocations=tuple(allocations),
                    transfers_departed=tuple(sorted(
                        departed,
                        key=lambda t: (t.resource, t.source, t.destination, t.arrive_period),
                    )),
                    transfers_arrived=tuple(sorted(
                        arrived,
                        key=lambda t: (t.resource, t.source, t.destination, t.depart_period),
                    )),
                    ending_stock=tuple(
                        sorted((resource, unit, location, quantity)
                               for (resource, unit, location), quantity in stock.items()
                               if quantity > 1e-12)
                    ),
                )
            )

        first_failure = min((period for period, _ in failed_demands), default=None)
        return TemporalAllocationPlan(
            viable=not failed_demands,
            periods=tuple(results),
            first_failure_period=first_failure,
            failed_demands=tuple(failed_demands),
        )

    def _ensure_capability(
        self,
        period: int,
        capability: str,
        minimum_service: float,
        graph: DependencyGraph,
        stock: Dict[tuple[str, str, str], float],
        service_levels: Dict[str, float],
        allocations: List[TemporalAllocation],
        stack: set[str],
    ) -> bool:
        current_service = service_levels.get(capability, 0.0)
        if current_service + 1e-12 >= minimum_service:
            return True
        if capability in stack:
            return False
        stack = set(stack)
        stack.add(capability)

        for dependency in sorted(
            graph.capability_requirements.get(capability, []),
            key=lambda item: item.capability,
        ):
            if dependency.critical and not self._ensure_capability(
                period, dependency.capability, minimum_service, graph, stock,
                service_levels, allocations, stack,
            ):
                return False

        for req in sorted(
            graph.resource_requirements.get(capability, []),
            key=lambda r: (r.resource, r.unit, r.location or "", r.quantity),
        ):
            if not req.critical:
                continue
            incremental = req.quantity * max(0.0, minimum_service - current_service)
            if incremental <= 1e-12:
                continue
            scaled = ResourceRequirement(
                req.resource, incremental, req.unit, req.minimum_quality,
                req.location, req.critical,
            )
            if not self._consume_requirement(
                period, capability, scaled, stock, allocations
            ):
                return False

        service_levels[capability] = max(current_service, minimum_service)
        return True

    def _consume_requirement(
        self,
        period: int,
        capability: str,
        req: ResourceRequirement,
        stock: Dict[tuple[str, str, str], float],
        allocations: List[TemporalAllocation],
    ) -> bool:
        remaining = req.quantity
        consumed = self._consume_stock(
            stock, req.resource, req.unit, remaining, req.location
        )
        if consumed > 0:
            allocations.append(TemporalAllocation(
                period, capability, req.resource, req.resource,
                consumed, consumed, req.unit, req.location, "stock",
            ))
            remaining -= consumed
        if remaining <= 1e-12:
            return True

        for alt in self.substitutions.alternatives(req.resource):
            substitute_needed = remaining * alt.ratio
            used = self._consume_stock(
                stock, alt.substitute, req.unit, substitute_needed, req.location
            )
            if used <= 0:
                continue
            equivalent = used / alt.ratio
            allocations.append(TemporalAllocation(
                period, capability, req.resource, alt.substitute,
                used, equivalent, req.unit, req.location, "substitution",
            ))
            remaining = max(0.0, remaining - equivalent)
            if remaining <= 1e-12:
                return True
        return False

    @staticmethod
    def _consume_stock(
        stock: Dict[tuple[str, str, str], float],
        resource: str,
        unit: str,
        quantity: float,
        location: str | None,
    ) -> float:
        keys = [
            key for key in stock
            if key[0] == resource and key[1] == unit
            and (location is None or key[2] == location)
            and stock[key] > 1e-12
        ]
        keys.sort()
        needed = quantity
        used = 0.0
        for key in keys:
            take = min(stock[key], needed)
            stock[key] -= take
            used += take
            needed -= take
            if needed <= 1e-12:
                break
        return used

    def _preposition_for_future(
        self,
        period: int,
        horizon: int,
        demands: Sequence[CapabilityDemand],
        graph: DependencyGraph,
        stock: Dict[tuple[str, str, str], float],
        links: Sequence[TransportLink],
        link_capacity_used: Dict[tuple[int, int], float],
        arrivals: Dict[int, List[Transfer]],
    ) -> None:
        future_needs: Dict[tuple[int, str, str, str], float] = {}
        for demand in demands:
            for demand_period in demand.periods:
                if demand_period <= period or demand_period >= horizon:
                    continue
                self._accumulate_needs(
                    demand.capability, demand_period, demand.minimum_service,
                    graph, future_needs, set()
                )

        for index, link in enumerate(links):
            arrival_period = period + link.lead_time_periods
            if arrival_period <= period or arrival_period >= horizon:
                continue
            need_key = (arrival_period, link.resource, link.unit, link.destination)
            required = future_needs.get(need_key, 0.0)
            if required <= 1e-12:
                continue

            already_arriving = sum(
                transfer.delivered_quantity
                for transfer in arrivals.get(arrival_period, [])
                if transfer.resource == link.resource
                and transfer.unit == link.unit
                and transfer.destination == link.destination
            )
            local = stock.get((link.resource, link.unit, link.destination), 0.0)
            shortage = max(0.0, required - local - already_arriving)
            if shortage <= 1e-12:
                continue

            capacity_key = (period, index)
            capacity_left = max(
                0.0,
                link.capacity_per_period - link_capacity_used.get(capacity_key, 0.0),
            )
            source_key = (link.resource, link.unit, link.source)
            source_available = stock.get(source_key, 0.0)
            if capacity_left <= 1e-12 or source_available <= 1e-12:
                continue

            delivered_per_shipped = 1.0 - link.loss_fraction
            shipped_for_shortage = shortage / delivered_per_shipped
            shipped = min(capacity_left, source_available, shipped_for_shortage)
            if shipped <= 1e-12:
                continue

            delivered = shipped * delivered_per_shipped
            stock[source_key] = source_available - shipped
            link_capacity_used[capacity_key] = link_capacity_used.get(capacity_key, 0.0) + shipped
            arrivals.setdefault(arrival_period, []).append(
                Transfer(
                    depart_period=period,
                    arrive_period=arrival_period,
                    source=link.source,
                    destination=link.destination,
                    resource=link.resource,
                    unit=link.unit,
                    shipped_quantity=shipped,
                    delivered_quantity=delivered,
                )
            )

    def _accumulate_needs(
        self,
        capability: str,
        period: int,
        minimum_service: float,
        graph: DependencyGraph,
        needs: Dict[tuple[int, str, str, str], float],
        visited: set[str],
    ) -> None:
        if capability in visited:
            return
        visited = set(visited)
        visited.add(capability)
        for req in graph.resource_requirements.get(capability, []):
            if not req.critical or req.location is None:
                continue
            key = (period, req.resource, req.unit, req.location)
            needs[key] = max(needs.get(key, 0.0), req.quantity * minimum_service)
        for dependency in graph.capability_requirements.get(capability, []):
            if dependency.critical:
                self._accumulate_needs(
                    dependency.capability, period, minimum_service, graph, needs, visited
                )
