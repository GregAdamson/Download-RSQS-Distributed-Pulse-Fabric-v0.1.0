from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, Dict, List
from .taskgraph import GraphTask, TaskGraph


@dataclass(frozen=True)
class SimulatedStep:
    task_id: str
    capability: str
    admitted: bool
    reason: str


class Simulator:
    def __init__(self, admission: Callable[[GraphTask], tuple[bool, str]]) -> None:
        self.admission = admission

    def dry_run(self, graph: TaskGraph) -> List[SimulatedStep]:
        result: List[SimulatedStep] = []
        for task in graph.topological_order():
            admitted, reason = self.admission(task)
            result.append(SimulatedStep(task.task_id, task.capability, admitted, reason))
        return result
