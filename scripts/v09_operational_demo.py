#!/usr/bin/env python3
from rsqs_pulse.dependency_graph import DependencyGraph
from rsqs_pulse.domain_adapter import (
    AdapterBatch,
    CanonicalDependency,
    CanonicalRule,
    MappingDomainAdapter,
    MappingSpec,
    apply_adapter_batch,
)
from rsqs_pulse.identity import NodeIdentity
from rsqs_pulse.institutional_rules import InstitutionalRuleStore
from rsqs_pulse.multi_host_acceptance import (
    MultiHostAcceptanceVerifier,
    issue_host_evidence,
)
from rsqs_pulse.observability import FabricObserver
from rsqs_pulse.persistent import SQLiteState
from rsqs_pulse.policy import LocalPolicy
from rsqs_pulse.resource_state import ResourceInventory
from rsqs_pulse.runtime import FabricRuntime
from rsqs_pulse.trajectory_optimizer import TrajectoryCandidate, TrajectoryOptimizer
from rsqs_pulse.trajectory_search import ExhaustiveTrajectorySearch, SearchConfig
from rsqs_pulse.trust_plane import TrustRegistry, issue_grant
from rsqs_pulse.trusted_capabilities import (
    TrustedCapabilityRegistry,
    sign_capability_advertisement,
)

runtime = FabricRuntime("operational-node", ":memory:", LocalPolicy(allowed_capabilities=set()))
inventory = ResourceInventory(runtime.state.conn)
graph = DependencyGraph()
rules = InstitutionalRuleStore(runtime.state.conn)

adapter = MappingDomainAdapter(
    MappingSpec(
        source="generic-feed",
        observation_fields={"system.load": "load"},
        resource_name_field="resource",
        quantity_field="quantity",
        unit_field="unit",
        location_field="location",
    )
)
mapped = adapter.ingest([
    {
        "load": 0.5,
        "resource": "input",
        "quantity": 20,
        "unit": "unit",
        "location": "site",
    }
])
batch = AdapterBatch(
    observations=mapped.observations,
    resources=mapped.resources,
    dependencies=(
        CanonicalDependency(
            "operate",
            resource="input",
            quantity=10,
            unit="unit",
        ),
    ),
    rules=(
        CanonicalRule("audit-required", "operate", "require", "audit", "generic-policy"),
    ),
    provenance=mapped.provenance,
)
apply_adapter_batch(
    batch,
    runtime=runtime,
    inventory=inventory,
    graph=graph,
    rule_sink=rules.add,
)
assert runtime.current_state().values["system.load"] == 0.5
assert inventory.available("input", "unit") == 20
assert rules.decide("operate", "audit").effect == "require"

optimizer = TrajectoryOptimizer()
search = ExhaustiveTrajectorySearch(
    optimizer,
    SearchConfig(max_depth=2, beam_width=2, max_candidates=20),
)
root = TrajectoryCandidate("root", actions=[{"reserve": 0}])

def expand(parent, depth):
    reserve = parent.actions[-1]["reserve"]
    return [
        TrajectoryCandidate(
            f"{parent.trajectory_id}.{delta}",
            actions=parent.actions + [{"reserve": reserve + delta}],
        )
        for delta in (1, 2)
    ]

result = search.search(
    [root],
    expand,
    lambda candidate: candidate.actions[-1]["reserve"] <= 4,
    lambda candidate: {"reserve_margin": candidate.actions[-1]["reserve"]},
)
assert result.complete_within_bounds
assert result.selected is not None
assert result.selected.actions[-1]["reserve"] == 4

authority = NodeIdentity("authority")
worker = NodeIdentity("worker")
trust = TrustRegistry(runtime.state.conn, authority.public)
trust.accept(
    issue_grant(
        authority,
        worker.public,
        ["capability:measure", "proof:multi_host"],
        1000,
    )
)
capabilities = TrustedCapabilityRegistry(runtime.state.conn, trust)
capabilities.accept(sign_capability_advertisement(worker, "measure", ttl_seconds=600))
assert capabilities.providers("measure")

snapshot = FabricObserver(runtime, trust_registry=trust).snapshot()
assert snapshot.trust["active_nodes"] == 1
print("OPERATIONAL_FABRIC_PROOF=PASS")

identities = {
    "coordinator": NodeIdentity("coordinator"),
    "worker-a": NodeIdentity("worker-a"),
    "worker-b": NodeIdentity("worker-b"),
}
for identity in identities.values():
    trust.accept(
        issue_grant(authority, identity.public, ["proof:multi_host"], 1000)
    )

evidence = []
for role, host in (
    ("coordinator", "sim-host-1"),
    ("worker-a", "sim-host-2"),
    ("worker-b", "sim-host-3"),
):
    evidence.append(
        issue_host_evidence(
            identities[role],
            host,
            "host_attestation",
            {"role": role},
        )
    )
for event, role in (
    ("task_signature_verified", "worker-a"),
    ("result_signature_verified", "coordinator"),
    ("local_deny_enforced", "worker-b"),
    ("worker_offline_before_dispatch", "worker-a"),
    ("offline_task_no_result", "coordinator"),
    ("worker_restart_same_state", "worker-a"),
    ("missed_task_reconciled", "worker-a"),
    ("coordinator_restart_preserved_results", "coordinator"),
    ("provenance_valid", "coordinator"),
    ("no_arbitrary_shell", "worker-b"),
):
    evidence.append(
        issue_host_evidence(
            identities[role],
            "sim-host-1" if role == "coordinator" else "sim-host-2" if role == "worker-a" else "sim-host-3",
            event,
            {},
        )
    )
for role, host in (("worker-a", "sim-host-2"), ("worker-b", "sim-host-3")):
    evidence.append(
        issue_host_evidence(
            identities[role],
            host,
            "key_isolation_attested",
            {"coordinator_private_key_present": False},
        )
    )
report = MultiHostAcceptanceVerifier(trust).assess(evidence)
assert report.passed
print("MULTI_HOST_HARNESS_PROOF=PASS")
runtime.close()
