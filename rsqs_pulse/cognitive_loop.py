from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable
from .state_reasoning import Constraint, State, Trajectory, TrajectoryPlanner, Transition


@dataclass(frozen=True)
class Observation:
    source: str
    values: Dict[str, Any]


@dataclass(frozen=True)
class ActionDecision:
    trajectory: Trajectory | None
    authorised: bool
    reason: str


class CognitiveLoop:
    def __init__(self, planner: TrajectoryPlanner | None = None) -> None:
        self.planner = planner or TrajectoryPlanner()

    def perceive(self, current: State, observations: Iterable[Observation]) -> State:
        values = dict(current.values)
        for observation in observations:
            values.update(observation.values)
        return State(values)

    def decide(
        self,
        current: State,
        desired: Callable[[State], bool],
        transitions: Iterable[Transition],
        constraints: Iterable[Constraint],
        authorise: Callable[[Trajectory], tuple[bool, str]],
        max_depth: int = 4,
    ) -> ActionDecision:
        trajectories = self.planner.plan(current, desired, transitions, constraints, max_depth)
        if not trajectories:
            return ActionDecision(None, False, "no admissible trajectory")
        for trajectory in trajectories:
            allowed, reason = authorise(trajectory)
            if allowed:
                return ActionDecision(trajectory, True, reason)
        return ActionDecision(trajectories[0], False, "all admissible trajectories denied")
