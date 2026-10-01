from __future__ import annotations
import time
from typing import Dict

from .distributed_runtime import DistributedWorker
from .idempotency import IdempotencyJournal
from .identity import NodeIdentity
from .model import Pulse
from .reconciliation import ReconciliableCapability, Reconciler
from .secure import pulse_bytes

class ReconciledDistributedWorker(DistributedWorker):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.journal = IdempotencyJournal(self.state.conn)
        self.reconciliable: Dict[str, ReconciliableCapability] = {}
        self.reconciler = Reconciler()

    def register_reconciliable(self, capability: str, implementation: ReconciliableCapability) -> None:
        self.reconciliable[capability] = implementation

    def _receive(self, pulse: Pulse) -> None:
        if pulse.network != self.network or pulse.kind != "TASK":
            return
        unsigned = Pulse(pulse.pulse_id, pulse.network, pulse.epoch, pulse.kind, pulse.issued_at, pulse.expires_at, pulse.payload, "")
        if not NodeIdentity.verify(self.authority, pulse_bytes(unsigned), pulse.signature):
            return
        if pulse.expires_at < int(time.time()) or pulse.payload.get("target_node") not in (None, self.node_id):
            return
        capability = pulse.payload["capability"]
        task_id = pulse.payload["task_id"]
        implementation = self.reconciliable.get(capability)
        if implementation is None or not self.policy.permits_capability(capability):
            self._publish_result(task_id, capability, "denied", {"reason": "reconciliable capability unavailable or denied"})
            return

        prior = self.journal.get(task_id)
        if prior is not None:
            status, stored = prior
            if status == "complete":
                self._publish_result(task_id, capability, "ok", stored)
                return
            decision = self.reconciler.inspect(implementation, task_id)
            if decision.action == "commit":
                output = decision.status.output
                self.journal.complete(task_id, output)
                self.state.record_result(task_id, self.node_id, pulse.epoch, "ok", output)
                self.ledger.append("reconciled_complete", task_id, {"evidence": decision.status.evidence})
                self._publish_result(task_id, capability, "ok", output)
            elif decision.action == "fail":
                output = {"reason": decision.reason, "evidence": decision.status.evidence}
                self.journal.fail(task_id, output)
                self._publish_result(task_id, capability, "failed", output)
            elif decision.action == "retry_eligible":
                self._execute_confirmed_not_applied(task_id, capability, pulse.payload.get("args", {}), implementation, pulse.epoch)
            else:
                self._publish_result(task_id, capability, decision.action, {"reason": decision.reason, "evidence": decision.status.evidence})
            return

        if not self.journal.begin(task_id):
            return
        self._execute(task_id, capability, pulse.payload.get("args", {}), implementation, pulse.epoch)

    def _execute_confirmed_not_applied(self, task_id, capability, args, implementation, epoch):
        self._execute(task_id, capability, args, implementation, epoch)

    def _execute(self, task_id, capability, args, implementation, epoch):
        try:
            output = implementation.execute(task_id, dict(args))
            if not isinstance(output, dict):
                raise TypeError("capability output must be a dictionary")
            confirmation = self.reconciler.inspect(implementation, task_id)
            if confirmation.action != "commit":
                self.ledger.append("execution_unconfirmed", task_id, {"action": confirmation.action, "evidence": confirmation.status.evidence})
                self._publish_result(task_id, capability, confirmation.action, {"reason": confirmation.reason, "evidence": confirmation.status.evidence})
                return
            durable = confirmation.status.output or output
            self.state.record_result(task_id, self.node_id, epoch, "ok", durable)
            self.journal.complete(task_id, durable)
            self.ledger.append("reconciled_action", task_id, {"capability": capability, "evidence": confirmation.status.evidence})
            self._publish_result(task_id, capability, "ok", durable)
        except Exception as exc:
            decision = self.reconciler.inspect(implementation, task_id)
            if decision.action == "commit":
                output = decision.status.output
                self.journal.complete(task_id, output)
                self.state.record_result(task_id, self.node_id, epoch, "ok", output)
                self._publish_result(task_id, capability, "ok", output)
                return
            self.ledger.append("execution_exception", task_id, {"error": str(exc), "reconciliation": decision.action})
            self._publish_result(task_id, capability, decision.action, {"error": str(exc), "evidence": decision.status.evidence})
