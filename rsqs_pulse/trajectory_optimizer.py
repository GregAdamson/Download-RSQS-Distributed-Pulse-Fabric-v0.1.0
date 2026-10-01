from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from .resilience_objectives import ResilienceObjective


@dataclass(frozen=True)
class TrajectoryState:
    period: int
    state: Any
    provenance: dict[str, Any] = field(default_factory=dict)


@dataclass
class TrajectoryCandidate:
    trajectory_id: str
    states: list[TrajectoryState] = field(default_factory=list)
    actions: list[dict[str, Any]] = field(default_factory=list)
    validated: bool = False
    score: float = float('-inf')
    failure_reason: str | None = None


@dataclass
class TrajectoryOptimizer:
    objective: ResilienceObjective = field(default_factory=ResilienceObjective)

    def validate(
        self,
        candidate: TrajectoryCandidate,
        validator: Callable[[TrajectoryCandidate], bool],
    ) -> TrajectoryCandidate:
        try:
            candidate.validated = bool(validator(candidate))
        except Exception as exc:
            candidate.validated = False
            candidate.failure_reason = str(exc)
        return candidate

    def score(
        self,
        candidate: TrajectoryCandidate,
        metrics: dict[str, float],
    ) -> TrajectoryCandidate:
        if candidate.validated:
            candidate.score = self.objective.score(metrics)
        return candidate

    def rank(
        self,
        candidates: Iterable[TrajectoryCandidate],
    ) -> list[TrajectoryCandidate]:
        return sorted(
            [c for c in candidates if c.validated],
            key=lambda c: (c.score, c.trajectory_id),
            reverse=True,
        )

    def select(
        self,
        candidates: Iterable[TrajectoryCandidate],
    ) -> TrajectoryCandidate | None:
        ranked = self.rank(candidates)
        return ranked[0] if ranked else None
