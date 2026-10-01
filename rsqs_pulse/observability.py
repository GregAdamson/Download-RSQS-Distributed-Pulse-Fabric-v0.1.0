from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .resilience import ScarcityAnalyzer
from .resilience_store import ResilienceStore
from .trust_plane import TrustRegistry


@dataclass(frozen=True)
class OperationalSnapshot:
    node_id: str
    status: str
    health: dict[str, Any]
    world_state: dict[str, Any]
    unresolved_operations: tuple[dict[str, Any], ...]
    capabilities: tuple[str, ...]
    capability_health: tuple[dict[str, Any], ...]
    resource_bottlenecks: tuple[dict[str, Any], ...]
    provenance_valid: bool
    trust: dict[str, Any] | None
    strategy_evidence: dict[str, int] | None
    selected_trajectory: dict[str, Any] | None


class FabricObserver:
    def __init__(
        self,
        runtime,
        *,
        trust_registry: TrustRegistry | None = None,
        resilience_store: ResilienceStore | None = None,
        resource_inventory=None,
        dependency_graph=None,
    ) -> None:
        self.runtime = runtime
        self.trust_registry = trust_registry
        self.resilience_store = resilience_store
        self.resource_inventory = resource_inventory
        self.dependency_graph = dependency_graph

    def snapshot(self) -> OperationalSnapshot:
        health = dict(self.runtime.health())
        world_state = dict(self.runtime.current_state().values)
        unresolved = tuple(
            {
                "operation_id": record.operation_id,
                "capability": record.capability,
                "target": record.target,
                "state": record.state.value,
                "attempts": record.attempts,
                "lease_until": record.lease_until,
            }
            for record in self.runtime.operations.unresolved()
        )
        capabilities = tuple(sorted(self.runtime.handlers))
        capability_health = tuple(
            {
                "name": name,
                "status": "registered",
            }
            for name in capabilities
        )
        trust = (
            None if self.trust_registry is None
            else self.trust_registry.summary()
        )

        bottlenecks = ()
        if (
            self.resource_inventory is not None
            and self.dependency_graph is not None
        ):
            bottlenecks = tuple(
                {
                    "resource": finding.resource,
                    "unit": finding.unit,
                    "required": finding.required,
                    "available": finding.available,
                    "shortage": finding.shortage,
                    "shortage_ratio": finding.shortage_ratio,
                    "affected_capabilities": list(
                        finding.affected_capabilities
                    ),
                }
                for finding in ScarcityAnalyzer().analyze(
                    self.dependency_graph,
                    self.resource_inventory,
                )
                if finding.shortage > 1e-12
            )

        strategy = None
        selected = None
        if self.resilience_store is not None:
            conn = self.resilience_store.conn
            strategy = {
                "scenarios": int(conn.execute(
                    "SELECT COUNT(*) FROM resilience_scenarios"
                ).fetchone()[0]),
                "trajectories": int(conn.execute(
                    "SELECT COUNT(*) FROM resilience_trajectories"
                ).fetchone()[0]),
                "outcomes": int(conn.execute(
                    "SELECT COUNT(*) FROM resilience_outcomes"
                ).fetchone()[0]),
                "lessons": int(conn.execute(
                    "SELECT COUNT(*) FROM resilience_lessons"
                ).fetchone()[0]),
            }
            row = conn.execute(
                """SELECT trajectory_id,payload_json,score
                   FROM resilience_trajectories
                   WHERE validated=1
                   ORDER BY score DESC,trajectory_id
                   LIMIT 1"""
            ).fetchone()
            if row is not None:
                import json
                selected = {
                    "trajectory_id": row[0],
                    "payload": json.loads(row[1]),
                    "score": float(row[2]),
                }

        return OperationalSnapshot(
            node_id=self.runtime.node_id,
            status=str(health["status"]),
            health=health,
            world_state=world_state,
            unresolved_operations=unresolved,
            capabilities=capabilities,
            capability_health=capability_health,
            resource_bottlenecks=bottlenecks,
            provenance_valid=bool(health["provenance_valid"]),
            trust=trust,
            strategy_evidence=strategy,
            selected_trajectory=selected,
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self.snapshot())
