from __future__ import annotations
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, Iterable
from .taskgraph import GraphTask, TaskGraph


@dataclass(frozen=True)
class IntentStep:
    capability: str
    args: Dict[str, Any]
    depends_on: tuple[int, ...] = ()


class DeterministicIntentCompiler:
    def compile(self, intent_id: str, steps: Iterable[IntentStep]) -> TaskGraph:
        material = list(steps)
        tasks = []
        ids = []
        for index, step in enumerate(material):
            digest = hashlib.sha256(
                json.dumps(
                    {"intent_id": intent_id, "index": index, "capability": step.capability, "args": step.args},
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=True,
                ).encode("ascii")
            ).hexdigest()[:16]
            ids.append(f"{intent_id}-{digest}")
        for index, step in enumerate(material):
            deps = tuple(ids[i] for i in step.depends_on)
            tasks.append(GraphTask(ids[index], step.capability, step.args, deps))
        return TaskGraph(tasks)
