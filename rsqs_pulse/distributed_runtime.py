from __future__ import annotations
import json
import time
import uuid
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any, Callable, Dict

from .http_transport import HTTPTransportClient
from .identity import NodeIdentity, PublicIdentity
from .model import Pulse
from .persistent import SQLiteState
from .policy import LocalPolicy
from .provenance import ProvenanceLedger
from .secure import pulse_bytes

if TYPE_CHECKING:
    from .trust_plane import TrustRegistry
    from .trusted_capabilities import TrustedCapabilityRegistry


def canonical_bytes(value: Dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


@dataclass(frozen=True)
class SignedResult:
    result_id: str
    task_id: str
    node_id: str
    capability: str
    status: str
    output: Dict[str, Any]
    issued_at: int
    signature: str

    def unsigned(self) -> Dict[str, Any]:
        data = asdict(self)
        data.pop("signature", None)
        return data


class DistributedWorker:
    def __init__(
        self,
        node_id: str,
        network: str,
        authority: PublicIdentity,
        identity: NodeIdentity,
        policy: LocalPolicy,
        state_path: str,
        transport: HTTPTransportClient,
    ) -> None:
        self.node_id = node_id
        self.network = network
        self.authority = authority
        self.identity = identity
        self.policy = policy
        self.state = SQLiteState(state_path)
        self.transport = transport
        self.ledger = ProvenanceLedger(self.state.conn)
        self.handlers: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {}
        self.cursor = int(self.state.get_meta("distributed_cursor", "0") or "0")

    def register(self, capability: str, handler: Callable[[Dict[str, Any]], Dict[str, Any]]) -> None:
        self.handlers[capability] = handler

    def poll_once(self) -> int:
        next_cursor, pulses = self.transport.poll(self.cursor)
        processed = 0
        for pulse in pulses:
            self._receive(pulse)
            processed += 1
        self.cursor = next_cursor
        self.state.set_meta("distributed_cursor", str(self.cursor))
        return processed

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
        target = pulse.payload.get("target_node")
        if target not in (None, self.node_id):
            return
        capability = pulse.payload["capability"]
        task_id = pulse.payload["task_id"]
        if not self.policy.permits_capability(capability) or capability not in self.handlers:
            self._publish_result(task_id, capability, "denied", {"reason": "local policy or capability unavailable"})
            return
        output = self.handlers[capability](pulse.payload.get("args", {}))
        self.state.record_result(task_id, self.node_id, pulse.epoch, "ok", output)
        self.ledger.append("distributed_action", task_id, {"capability": capability, "output": output})
        self._publish_result(task_id, capability, "ok", output)

    def _publish_result(self, task_id: str, capability: str, status: str, output: Dict[str, Any]) -> SignedResult:
        unsigned = {
            "result_id": str(uuid.uuid4()),
            "task_id": task_id,
            "node_id": self.node_id,
            "capability": capability,
            "status": status,
            "output": output,
            "issued_at": int(time.time()),
        }
        result = SignedResult(**unsigned, signature=self.identity.sign(canonical_bytes(unsigned)))
        pulse = Pulse.new(self.network, int(time.time() * 1000), "RESULT", {"result": asdict(result)}, ttl_seconds=120)
        self.transport.publish(pulse)
        return result

    def close(self) -> None:
        self.state.conn.close()


class DistributedCoordinator:
    def __init__(
        self,
        network: str,
        identity: NodeIdentity,
        state_path: str,
        transport: HTTPTransportClient,
        trusted_workers: Dict[str, PublicIdentity],
        trust_registry: "TrustRegistry | None" = None,
        capability_registry: "TrustedCapabilityRegistry | None" = None,
    ) -> None:
        self.network = network
        self.identity = identity
        self.state = SQLiteState(state_path)
        self.transport = transport
        self.trusted_workers = dict(trusted_workers)
        self.trust_registry = trust_registry
        self.capability_registry = capability_registry
        self.ledger = ProvenanceLedger(self.state.conn)
        self.cursor = int(self.state.get_meta("coordinator_cursor", "0") or "0")
        self.epoch = int(self.state.get_meta("coordinator_epoch", "0") or "0")
        self._init_schema()

    def _init_schema(self) -> None:
        self.state.conn.execute("""
        CREATE TABLE IF NOT EXISTS distributed_results(
          result_id TEXT PRIMARY KEY,
          task_id TEXT NOT NULL,
          node_id TEXT NOT NULL,
          capability TEXT NOT NULL,
          status TEXT NOT NULL,
          output_json TEXT NOT NULL,
          issued_at INTEGER NOT NULL,
          signature TEXT NOT NULL
        )
        """)
        self.state.conn.commit()

    def dispatch(self, target_node: str, capability: str, args: Dict[str, Any], ttl_seconds: int = 120) -> str:
        if self.trust_registry is not None and not self.trust_registry.authorise(target_node, capability):
            raise PermissionError(f"target node is not authorised for capability: {target_node}:{capability}")
        if self.capability_registry is not None:
            providers = {
                advertisement.node_id
                for advertisement in self.capability_registry.providers(capability)
            }
            if target_node not in providers:
                raise PermissionError(
                    f"target node has no active signed capability advertisement: {target_node}:{capability}"
                )
        self.epoch += 1
        self.state.set_meta("coordinator_epoch", str(self.epoch))
        task_id = str(uuid.uuid4())
        unsigned = Pulse.new(
            self.network,
            self.epoch,
            "TASK",
            {"task_id": task_id, "target_node": target_node, "capability": capability, "args": args},
            ttl_seconds,
        )
        pulse = Pulse(
            unsigned.pulse_id, unsigned.network, unsigned.epoch, unsigned.kind,
            unsigned.issued_at, unsigned.expires_at, unsigned.payload,
            self.identity.sign(pulse_bytes(unsigned)),
        )
        self.transport.publish(pulse)
        self.ledger.append("distributed_dispatch", task_id, {"target_node": target_node, "capability": capability})
        return task_id

    def collect_once(self) -> int:
        next_cursor, pulses = self.transport.poll(self.cursor)
        accepted = 0
        for pulse in pulses:
            if pulse.network != self.network or pulse.kind != "RESULT":
                continue
            raw = pulse.payload.get("result", {})
            try:
                result = SignedResult(**raw)
            except TypeError:
                continue
            if self.trust_registry is not None:
                if not self.trust_registry.authorise(result.node_id, result.capability):
                    continue
                public = self.trust_registry.identity(result.node_id)
            else:
                public = self.trusted_workers.get(result.node_id)
            if public is None or not NodeIdentity.verify(public, canonical_bytes(result.unsigned()), result.signature):
                continue
            self.state.conn.execute(
                """INSERT OR IGNORE INTO distributed_results
                   (result_id,task_id,node_id,capability,status,output_json,issued_at,signature)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (
                    result.result_id, result.task_id, result.node_id, result.capability,
                    result.status, json.dumps(result.output, sort_keys=True),
                    result.issued_at, result.signature,
                ),
            )
            self.state.conn.commit()
            self.ledger.append("distributed_result", result.result_id, result.unsigned())
            accepted += 1
        self.cursor = next_cursor
        self.state.set_meta("coordinator_cursor", str(self.cursor))
        return accepted

    def results(self, task_id: str) -> list[Dict[str, Any]]:
        rows = self.state.conn.execute(
            "SELECT node_id,capability,status,output_json FROM distributed_results WHERE task_id=? ORDER BY node_id",
            (task_id,),
        ).fetchall()
        return [{"node_id": r[0], "capability": r[1], "status": r[2], "output": json.loads(r[3])} for r in rows]

    def close(self) -> None:
        self.state.conn.close()
