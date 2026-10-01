from __future__ import annotations
import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict
from .broker import InMemoryBroker
from .identity import NodeIdentity, PublicIdentity
from .model import Pulse
from .policy import LocalPolicy
from .provenance import ProvenanceLedger
from .persistent import SQLiteState


def pulse_bytes(pulse: Pulse) -> bytes:
    return json.dumps(
        pulse.unsigned_dict(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")


class SecureCoordinator:
    def __init__(self, network: str, identity: NodeIdentity, broker: InMemoryBroker, state: SQLiteState) -> None:
        self.network = network
        self.identity = identity
        self.broker = broker
        self.state = state
        self.ledger = ProvenanceLedger(state.conn)
        self.epoch = int(state.get_meta("epoch", "0") or "0")

    def emit(self, kind: str, payload: Dict[str, Any], ttl_seconds: int = 30) -> Pulse:
        self.epoch += 1
        unsigned = Pulse.new(self.network, self.epoch, kind, payload, ttl_seconds)
        signed = Pulse(
            unsigned.pulse_id,
            unsigned.network,
            unsigned.epoch,
            unsigned.kind,
            unsigned.issued_at,
            unsigned.expires_at,
            unsigned.payload,
            self.identity.sign(pulse_bytes(unsigned)),
        )
        self.state.set_meta("epoch", str(self.epoch))
        self.ledger.append("pulse", signed.pulse_id, {"epoch": signed.epoch, "kind": signed.kind})
        self.broker.publish(signed)
        return signed


@dataclass
class SecureNode:
    node_id: str
    network: str
    authority: PublicIdentity
    policy: LocalPolicy
    state: SQLiteState

    def __post_init__(self) -> None:
        self.last_epoch = int(self.state.get_meta(f"last_epoch:{self.node_id}", "-1") or "-1")
        self.handlers: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {}
        self.ledger = ProvenanceLedger(self.state.conn)

    def register(self, capability: str, handler: Callable[[Dict[str, Any]], Dict[str, Any]]) -> None:
        self.handlers[capability] = handler

    def receive(self, pulse: Pulse) -> None:
        now = int(time.time())
        if pulse.network != self.network:
            return
        unsigned = Pulse(
            pulse.pulse_id, pulse.network, pulse.epoch, pulse.kind,
            pulse.issued_at, pulse.expires_at, pulse.payload, ""
        )
        if not NodeIdentity.verify(self.authority, pulse_bytes(unsigned), pulse.signature):
            return
        if pulse.expires_at < now or pulse.epoch < self.last_epoch:
            return
        if not self.policy.permits_pulse(pulse.kind):
            return
        self.last_epoch = pulse.epoch
        self.state.set_meta(f"last_epoch:{self.node_id}", str(self.last_epoch))
        self.ledger.append("receive", pulse.pulse_id, {"node_id": self.node_id, "kind": pulse.kind, "epoch": pulse.epoch})
        if pulse.kind == "TASK":
            self._task(pulse)

    def _task(self, pulse: Pulse) -> None:
        capability = pulse.payload["capability"]
        if not self.policy.permits_capability(capability):
            self.ledger.append("deny", pulse.pulse_id, {"node_id": self.node_id, "capability": capability})
            return
        handler = self.handlers.get(capability)
        if handler is None:
            return
        output = handler(pulse.payload.get("args", {}))
        task_id = pulse.payload["task_id"]
        self.state.record_result(task_id, self.node_id, pulse.epoch, "ok", output)
        self.ledger.append("result", task_id, {"node_id": self.node_id, "output": output})
