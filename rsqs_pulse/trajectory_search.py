from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Mapping

from .trajectory_optimizer import TrajectoryCandidate, TrajectoryOptimizer


@dataclass(frozen=True)
class SearchConfig:
    max_depth: int = 4
    beam_width: int = 8
    max_candidates: int = 256

    def __post_init__(self) -> None:
        if self.max_depth < 0:
            raise ValueError("max_depth must be non-negative")
        if self.beam_width <= 0 or self.max_candidates <= 0:
            raise ValueError("beam_width and max_candidates must be positive")


@dataclass(frozen=True)
class SearchResult:
    selected: TrajectoryCandidate | None
    ranked: tuple[TrajectoryCandidate, ...]
    explored: int
    depth_reached: int
    exhausted: bool


class BoundedTrajectorySearch:
    """
    Deterministic bounded beam search above the admissibility validator.

    It never converts an invalid candidate into an admissible one and never
    executes actions. The caller supplies expansion, validation and scoring.
    """

    def __init__(
        self,
        optimizer: TrajectoryOptimizer | None = None,
        config: SearchConfig | None = None,
    ) -> None:
        self.optimizer = optimizer or TrajectoryOptimizer()
        self.config = config or SearchConfig()

    def search(
        self,
        seeds: Iterable[TrajectoryCandidate],
        expander: Callable[[TrajectoryCandidate, int], Iterable[TrajectoryCandidate]],
        validator: Callable[[TrajectoryCandidate], bool],
        metrics_provider: Callable[[TrajectoryCandidate], Mapping[str, float] | object],
    ) -> SearchResult:
        seen: set[str] = set()
        explored = 0
        depth_reached = 0

        def evaluate(candidate: TrajectoryCandidate) -> TrajectoryCandidate | None:
            nonlocal explored
            if candidate.trajectory_id in seen:
                return None
            if explored >= self.config.max_candidates:
                return None
            seen.add(candidate.trajectory_id)
            explored += 1
            return self.optimizer.evaluate(candidate, validator, metrics_provider)

        frontier = []
        for candidate in seeds:
            evaluated = evaluate(candidate)
            if evaluated is not None and evaluated.validated:
                frontier.append(evaluated)
        frontier = self.optimizer.rank(frontier)[: self.config.beam_width]
        all_valid = list(frontier)

        exhausted = False
        for depth in range(1, self.config.max_depth + 1):
            if not frontier or explored >= self.config.max_candidates:
                exhausted = not frontier
                break
            next_frontier = []
            for parent in frontier:
                children = sorted(
                    expander(parent, depth),
                    key=lambda item: item.trajectory_id,
                )
                for child in children:
                    evaluated = evaluate(child)
                    if evaluated is not None and evaluated.validated:
                        next_frontier.append(evaluated)
                    if explored >= self.config.max_candidates:
                        break
                if explored >= self.config.max_candidates:
                    break
            if not next_frontier:
                exhausted = True
                break
            frontier = self.optimizer.rank(next_frontier)[: self.config.beam_width]
            all_valid.extend(frontier)
            depth_reached = depth

        ranked = tuple(self.optimizer.rank(all_valid))
        return SearchResult(
            selected=ranked[0] if ranked else None,
            ranked=ranked,
            explored=explored,
            depth_reached=depth_reached,
            exhausted=exhausted,
        )
