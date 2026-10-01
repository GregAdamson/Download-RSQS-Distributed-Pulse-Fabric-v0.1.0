from __future__ import annotations
import time
from typing import Any, Callable, Dict
from .distributed_runtime import DistributedWorker
from .idempotency import IdempotencyJournal
from .identity import NodeIdentity
from .model import Pulse
from .secure import pulse_bytes

class RecoverableDistributedWorker(DistributedWorker):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.journal = IdempotencyJournal(self.state.conn)

    def _receive(self, pulse: Pulse) -> None:
        if pulse.network != self.network or pulse.kind != "TASK":
            return
        unsigned = Pulse(
            pulse.pulse_id, pulse.network, pulse.epoch, pulse.kind,
            pulse.issued_at, pulse.expires_at, pulse.payload, ""
        )
        if not NodeIdentity.verify(self.authority, pulse_bytes(unsigned), pulse.signature):
            return
        if pulse.expires_at < int(time.time()):
            return
        if pulse.payload.get("target_node") not in (None, self.node_id):
            return
        capability = pulse.payload["capability"]
        task_id = pulse.payload["task_id"]
        prior = self.journal.get(task_id)
        if prior is not None:
            status, output = prior
            if status == "complete":
                self._publish_result(task_id, capability, "ok", output)
            elif status == "failed":
                self._publish_result(task_id, capability, "failed", output)
            return
        if not self.policy.permits_capability(capability) or capability not in self.handlers:
            output = {"reason": "local policy or capability unavailable"}
            self.journal.begin(task_id)
            self.journal.fail(task_id, output)
            self._publish_result(task_id, capability, "denied", output)
            return
        if not self.journal.begin(task_id):
            return
        try:
            output = self.handlers[capability](pulse.payload.get("args", {}))
            if not isinstance(output, dict):
                raise TypeError("capability output must be a dictionary")
            self.state.record_result(task_id, self.node_id, pulse.epoch, "ok", output)
            self.journal.complete(task_id, output)
            self.ledger.append("distributed_action", task_id, {"capability": capability, "output": output})
            self._publish_result(task_id, capability, "ok", output)
        except Exception as exc:
            output = {"error": str(exc)}
            self.journal.fail(task_id, output)
            self.ledger.append("distributed_action_failed", task_id, {"capability": capability, "error": str(exc)})
            self._publish_result(task_id, capability, "failed", output)
