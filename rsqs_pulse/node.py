from __future__ import annotations
from typing import Any, Callable, Dict
import time
from .crypto import verify_pulse
from .model import Capability, Pulse, Task, TaskResult
from .policy import LocalPolicy

Handler = Callable[[Dict[str, Any]], Dict[str, Any]]


class Node:
    def __init__(self, node_id: str, network: str, secret: bytes, policy: LocalPolicy) -> None:
        self.node_id = node_id
        self.network = network
        self.secret = secret
        self.policy = policy
        self.last_epoch = -1
        self.handlers: Dict[str, Handler] = {}
        self.capabilities: Dict[str, Capability] = {}
        self.results: list[TaskResult] = []

    def register(self, capability: Capability, handler: Handler) -> None:
        self.capabilities[capability.name] = capability
        self.handlers[capability.name] = handler

    def receive(self, pulse: Pulse) -> None:
        now = int(time.time())
        if pulse.network != self.network:
            return
        if not verify_pulse(pulse, self.secret):
            return
        if pulse.expires_at < now:
            return
        if pulse.epoch < self.last_epoch:
            return
        if not self.policy.permits_pulse(pulse.kind):
            return

        self.last_epoch = max(self.last_epoch, pulse.epoch)
        if pulse.kind == "TASK":
            self._handle_task(pulse)

    def _handle_task(self, pulse: Pulse) -> None:
        data = pulse.payload
        task = Task(
            task_id=data["task_id"],
            epoch=pulse.epoch,
            capability=data["capability"],
            operation=data["operation"],
            args=data.get("args", {}),
        )
        if not self.policy.permits_capability(task.capability):
            return
        handler = self.handlers.get(task.capability)
        if handler is None:
            return
        try:
            output = handler(task.args)
            status = "ok"
        except Exception as exc:
            output = {"error": str(exc)}
            status = "error"
        self.results.append(TaskResult(task.task_id, self.node_id, task.epoch, status, output))
