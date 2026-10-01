from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping

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
    score: float = float("-inf")
    failure_reason: str | None = None


@dataclass
class TrajectoryOptimizer:
    objective: ResilienceObjective = field(default_factory=ResilienceObjective)

    def generate(
        self,
        strategies: Iterable[Mapping[str, Any]],
    ) -> list[TrajectoryCandidate]:
        candidates = []
        seen = set()
        for strategy in strategies:
            trajectory_id = str(strategy["trajectory_id"])
            if trajectory_id in seen:
                raise ValueError(f"duplicate trajectory_id: {trajectory_id}")
            seen.add(trajectory_id)
            states = list(strategy.get("states", []))
            actions = [dict(action) for action in strategy.get("actions", [])]
            if not all(isinstance(state, TrajectoryState) for state in states):
                raise TypeError("states must contain TrajectoryState instances")
            candidates.append(
                TrajectoryCandidate(
                    trajectory_id=trajectory_id,
                    states=states,
                    actions=actions,
                )
            )
        return candidates

    def validate(
        self,
        candidate: TrajectoryCandidate,
        validator: Callable[[TrajectoryCandidate], bool],
    ) -> TrajectoryCandidate:
        candidate.failure_reason = None
        try:
            candidate.validated = bool(validator(candidate))
            if not candidate.validated:
                candidate.failure_reason = "validator rejected candidate"
        except Exception as exc:
            candidate.validated = False
            candidate.failure_reason = str(exc)
        if not candidate.validated:
            candidate.score = float("-inf")
        return candidate

    def score(
        self,
        candidate: TrajectoryCandidate,
        metrics: Mapping[str, float] | Any,
    ) -> TrajectoryCandidate:
        if candidate.validated:
            candidate.score = self.objective.score(metrics)
        else:
            candidate.score = float("-inf")
        return candidate

    def evaluate(
        self,
        candidate: TrajectoryCandidate,
        validator: Callable[[TrajectoryCandidate], bool],
        metrics_provider: Callable[[TrajectoryCandidate], Mapping[str, float] | Any],
    ) -> TrajectoryCandidate:
        self.validate(candidate, validator)
        if candidate.validated:
            self.score(candidate, metrics_provider(candidate))
        return candidate

    def rank(
        self,
        candidates: Iterable[TrajectoryCandidate],
    ) -> list[TrajectoryCandidate]:
        return sorted(
            [candidate for candidate in candidates if candidate.validated],
            key=lambda candidate: (-candidate.score, candidate.trajectory_id),
        )

    def select(
        self,
        candidates: Iterable[TrajectoryCandidate],
    ) -> TrajectoryCandidate | None:
        ranked = self.rank(candidates)
        return ranked[0] if ranked else None
