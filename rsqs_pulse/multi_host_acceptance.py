from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, replace
from typing import Any, Iterable

from .identity import NodeIdentity
from .trust_plane import TrustRegistry


def _canonical(value: dict) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")


@dataclass(frozen=True)
class HostEvidence:
    evidence_id: str
    node_id: str
    host_instance: str
    event: str
    issued_at: int
    details: dict[str, Any]
    signature: str = ""

    def unsigned(self) -> dict:
        value = asdict(self)
        value.pop("signature", None)
        return value


def issue_host_evidence(
    identity: NodeIdentity,
    host_instance: str,
    event: str,
    details: dict[str, Any] | None = None,
    *,
    now: int | None = None,
) -> HostEvidence:
    evidence = HostEvidence(
        evidence_id=str(uuid.uuid4()),
        node_id=identity.node_id,
        host_instance=host_instance,
        event=event,
        issued_at=int(time.time()) if now is None else int(now),
        details=dict(details or {}),
        signature="",
    )
    return replace(
        evidence,
        signature=identity.sign(_canonical(evidence.unsigned())),
    )


@dataclass(frozen=True)
class AcceptanceCriterion:
    name: str
    passed: bool
    evidence_ids: tuple[str, ...]
    operator_attested: bool = False


@dataclass(frozen=True)
class MultiHostAcceptanceReport:
    passed: bool
    criteria: tuple[AcceptanceCriterion, ...]
    enrolled_nodes: tuple[str, ...]
    host_instances: tuple[str, ...]


class MultiHostAcceptanceVerifier:
    REQUIRED_EVENTS = (
        "task_signature_verified",
        "result_signature_verified",
        "local_deny_enforced",
        "worker_offline_before_dispatch",
        "offline_task_no_result",
        "worker_restart_same_state",
        "missed_task_reconciled",
        "coordinator_restart_preserved_results",
        "provenance_valid",
        "no_arbitrary_shell",
    )

    def __init__(self, trust_registry: TrustRegistry) -> None:
        self.trust_registry = trust_registry

    def verify_evidence(self, evidence: HostEvidence) -> bool:
        if not self.trust_registry.authorise(
            evidence.node_id,
            "proof:multi_host",
            now=evidence.issued_at,
        ):
            return False
        public = self.trust_registry.identity(
            evidence.node_id,
            now=evidence.issued_at,
        )
        if public is None:
            return False
        return NodeIdentity.verify(
            public,
            _canonical(evidence.unsigned()),
            evidence.signature,
        )

    def assess(
        self,
        evidence_items: Iterable[HostEvidence],
    ) -> MultiHostAcceptanceReport:
        valid = [item for item in evidence_items if self.verify_evidence(item)]
        by_event: dict[str, list[HostEvidence]] = {}
        for item in valid:
            by_event.setdefault(item.event, []).append(item)

        host_attestations = by_event.get("host_attestation", [])
        role_hosts = {
            str(item.details.get("role")): item.host_instance
            for item in host_attestations
            if item.details.get("role") in {"coordinator", "worker-a", "worker-b"}
        }
        distinct_hosts = (
            set(role_hosts) == {"coordinator", "worker-a", "worker-b"}
            and len(set(role_hosts.values())) == 3
        )
        criteria = [
            AcceptanceCriterion(
                "three_distinct_enrolled_hosts",
                distinct_hosts,
                tuple(item.evidence_id for item in host_attestations),
                operator_attested=True,
            )
        ]

        for event in self.REQUIRED_EVENTS:
            items = by_event.get(event, [])
            criteria.append(
                AcceptanceCriterion(
                    event,
                    bool(items),
                    tuple(item.evidence_id for item in items),
                    operator_attested=(event in {"no_arbitrary_shell"}),
                )
            )

        key_items = by_event.get("key_isolation_attested", [])
        criteria.append(
            AcceptanceCriterion(
                "coordinator_private_key_absent_from_workers",
                len({
                    item.node_id for item in key_items
                    if item.details.get("coordinator_private_key_present") is False
                }) >= 2,
                tuple(item.evidence_id for item in key_items),
                operator_attested=True,
            )
        )

        return MultiHostAcceptanceReport(
            passed=all(item.passed for item in criteria),
            criteria=tuple(criteria),
            enrolled_nodes=tuple(sorted({item.node_id for item in valid})),
            host_instances=tuple(sorted({item.host_instance for item in valid})),
        )
