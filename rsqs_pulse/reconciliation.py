from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Protocol

class OperationState(str, Enum):
    NOT_APPLIED = "not_applied"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"
    UNKNOWN = "unknown"

@dataclass(frozen=True)
class OperationStatus:
    operation_id: str
    state: OperationState
    output: Dict[str, Any]
    evidence: Dict[str, Any]

class ReconciliableCapability(Protocol):
    def execute(self, operation_id: str, args: Dict[str, Any]) -> Dict[str, Any]: ...
    def status(self, operation_id: str) -> OperationStatus: ...

@dataclass(frozen=True)
class ReconciliationDecision:
    operation_id: str
    action: str
    status: OperationStatus
    reason: str

class Reconciler:
    def inspect(self, capability: ReconciliableCapability, operation_id: str) -> ReconciliationDecision:
        status = capability.status(operation_id)
        if status.state == OperationState.COMPLETE:
            return ReconciliationDecision(operation_id, "commit", status, "capability confirms durable completion")
        if status.state == OperationState.NOT_APPLIED:
            return ReconciliationDecision(operation_id, "retry_eligible", status, "capability confirms operation was not applied")
        if status.state == OperationState.FAILED:
            return ReconciliationDecision(operation_id, "fail", status, "capability confirms failure")
        if status.state == OperationState.RUNNING:
            return ReconciliationDecision(operation_id, "wait", status, "capability reports operation still running")
        return ReconciliationDecision(operation_id, "escalate", status, "external effect cannot be determined safely")
