from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List


@dataclass(frozen=True)
class State:
    values: Dict[str, Any]


@dataclass(frozen=True)
class Constraint:
    name: str
    predicate: Callable[[State], bool]


@dataclass(frozen=True)
class Transition:
    name: str
    capability: str
    apply: Callable[[State], State]
    reversible: bool = False
    cost: float = 0.0


@dataclass(frozen=True)
class Trajectory:
    transitions: tuple[Transition, ...]
    final_state: State
    cost: float


class TrajectoryPlanner:
    def plan(
        self,
        initial: State,
        desired: Callable[[State], bool],
        transitions: Iterable[Transition],
        constraints: Iterable[Constraint] = (),
        max_depth: int = 4,
    ) -> List[Trajectory]:
        constraints = tuple(constraints)
        transitions = tuple(transitions)
        found: List[Trajectory] = []
        frontier = [(initial, tuple(), 0.0)]
        seen = {repr(sorted(initial.values.items()))}
        while frontier:
            state, path, cost = frontier.pop(0)
            if desired(state):
                found.append(Trajectory(path, state, cost))
                continue
            if len(path) >= max_depth:
                continue
            for transition in transitions:
                candidate = transition.apply(state)
                if not all(c.predicate(candidate) for c in constraints):
                    continue
                key = repr(sorted(candidate.values.items()))
                if key in seen:
                    continue
                seen.add(key)
                frontier.append((candidate, path + (transition,), cost + transition.cost))
        return sorted(found, key=lambda x: (x.cost, len(x.transitions), tuple(t.name for t in x.transitions)))
