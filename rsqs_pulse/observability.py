from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .resilience_store import ResilienceStore
from .trust_plane import TrustRegistry


@dataclass(frozen=True)
class OperationalSnapshot:
    node_id: str
    status: str
    health: dict[str, Any]
    unresolved_operations: tuple[dict[str, Any], ...]
    capabilities: tuple[str, ...]
    provenance_valid: bool
    trust: dict[str, Any] | None
    strategy_evidence: dict[str, int] | None


class FabricObserver:
    def __init__(
        self,
        runtime,
        *,
        trust_registry: TrustRegistry | None = None,
        resilience_store: ResilienceStore | None = None,
    ) -> None:
        self.runtime = runtime
        self.trust_registry = trust_registry
        self.resilience_store = resilience_store

    def snapshot(self) -> OperationalSnapshot:
        health = dict(self.runtime.health())
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
        trust = (
            None if self.trust_registry is None
            else self.trust_registry.summary()
        )
        strategy = None
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
        return OperationalSnapshot(
            node_id=self.runtime.node_id,
            status=str(health["status"]),
            health=health,
            unresolved_operations=unresolved,
            capabilities=tuple(sorted(self.runtime.handlers)),
            provenance_valid=bool(health["provenance_valid"]),
            trust=trust,
            strategy_evidence=strategy,
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self.snapshot())
