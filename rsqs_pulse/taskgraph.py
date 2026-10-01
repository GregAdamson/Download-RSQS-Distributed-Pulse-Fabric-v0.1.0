from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Set


@dataclass(frozen=True)
class GraphTask:
    task_id: str
    capability: str
    args: Dict[str, Any] = field(default_factory=dict)
    depends_on: tuple[str, ...] = ()


class TaskGraph:
    def __init__(self, tasks: Iterable[GraphTask]) -> None:
        self.tasks = {t.task_id: t for t in tasks}
        self._validate()

    def _validate(self) -> None:
        for task in self.tasks.values():
            for dep in task.depends_on:
                if dep not in self.tasks:
                    raise ValueError(f"missing dependency: {dep}")
        self.topological_order()

    def topological_order(self) -> List[GraphTask]:
        temporary: Set[str] = set()
        permanent: Set[str] = set()
        ordered: List[GraphTask] = []

        def visit(task_id: str) -> None:
            if task_id in permanent:
                return
            if task_id in temporary:
                raise ValueError("cycle detected")
            temporary.add(task_id)
            for dep in self.tasks[task_id].depends_on:
                visit(dep)
            temporary.remove(task_id)
            permanent.add(task_id)
            ordered.append(self.tasks[task_id])

        for task_id in sorted(self.tasks):
            visit(task_id)
        return ordered


class GraphExecutor:
    def __init__(self, dispatch: Callable[[GraphTask, Dict[str, Any]], Any]) -> None:
        self.dispatch = dispatch

    def run(self, graph: TaskGraph) -> Dict[str, Any]:
        outputs: Dict[str, Any] = {}
        for task in graph.topological_order():
            dep_outputs = {dep: outputs[dep] for dep in task.depends_on}
            outputs[task.task_id] = self.dispatch(task, dep_outputs)
        return outputs
