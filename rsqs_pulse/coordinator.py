from __future__ import annotations
from typing import Any, Dict
from .broker import InMemoryBroker
from .crypto import sign_pulse
from .model import Pulse, Task


class Coordinator:
    def __init__(self, network: str, secret: bytes, broker: InMemoryBroker) -> None:
        self.network = network
        self.secret = secret
        self.broker = broker
        self.epoch = 0

    def emit(self, kind: str, payload: Dict[str, Any], ttl_seconds: int = 30) -> Pulse:
        self.epoch += 1
        pulse = Pulse.new(self.network, self.epoch, kind, payload, ttl_seconds)
        signed = sign_pulse(pulse, self.secret)
        self.broker.publish(signed)
        return signed

    def dispatch_task(self, capability: str, operation: str, args: Dict[str, Any]) -> Task:
        task = Task.new(self.epoch + 1, capability, operation, args)
        self.emit("TASK", {
            "task_id": task.task_id,
            "capability": task.capability,
            "operation": task.operation,
            "args": task.args,
        })
        return task
