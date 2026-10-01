from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List
import json
import time
import uuid


def canonical_json(value: Dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


@dataclass(frozen=True)
class Pulse:
    pulse_id: str
    network: str
    epoch: int
    kind: str
    issued_at: int
    expires_at: int
    payload: Dict[str, Any]
    signature: str = ""

    @staticmethod
    def new(network: str, epoch: int, kind: str, payload: Dict[str, Any], ttl_seconds: int = 30) -> "Pulse":
        now = int(time.time())
        return Pulse(
            pulse_id=str(uuid.uuid4()),
            network=network,
            epoch=epoch,
            kind=kind,
            issued_at=now,
            expires_at=now + ttl_seconds,
            payload=payload,
        )

    def unsigned_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data.pop("signature", None)
        return data


@dataclass(frozen=True)
class Capability:
    name: str
    version: str = "1"
    tags: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class Task:
    task_id: str
    epoch: int
    capability: str
    operation: str
    args: Dict[str, Any]

    @staticmethod
    def new(epoch: int, capability: str, operation: str, args: Dict[str, Any]) -> "Task":
        return Task(str(uuid.uuid4()), epoch, capability, operation, args)


@dataclass(frozen=True)
class TaskResult:
    task_id: str
    node_id: str
    epoch: int
    status: str
    output: Dict[str, Any]
