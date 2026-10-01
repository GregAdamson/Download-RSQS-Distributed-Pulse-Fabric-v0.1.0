import os
import tempfile
import unittest

from rsqs_pulse.cognitive_loop import Observation
from rsqs_pulse.distributed_runtime import DistributedCoordinator, DistributedWorker
from rsqs_pulse.domain_adapter import (
    AdapterBatch,
    CanonicalDependency,
    CanonicalRule,
    MappingDomainAdapter,
    MappingSpec,
    apply_adapter_batch,
)
from rsqs_pulse.http_transport import HTTPTransportClient, PulseHTTPServer
from rsqs_pulse.identity import NodeIdentity
from rsqs_pulse.multi_host_acceptance import (
    MultiHostAcceptanceVerifier,
    issue_host_evidence,
)
from rsqs_pulse.observability import FabricObserver
from rsqs_pulse.persistent import SQLiteState
from rsqs_pulse.policy import LocalPolicy
from rsqs_pulse.resilience_store import ResilienceStore
from rsqs_pulse.resource_state import ResourceInventory
from rsqs_pulse.runtime import FabricRuntime
from rsqs_pulse.dependency_graph import DependencyGraph
from rsqs_pulse.trajectory_optimizer import TrajectoryCandidate, TrajectoryOptimizer
from rsqs_pulse.trajectory_search import BoundedTrajectorySearch, SearchConfig
from rsqs_pulse.trust_plane import TrustRegistry, issue_grant


class OperationalV09Tests(unittest.TestCase):
    def test_trust_grant_expiry_revocation_and_rotation(self):
        authority = NodeIdentity("authority")
        worker = NodeIdentity("worker")
        replacement = NodeIdentity("worker")
        state = SQLiteState(":memory:")
        trust = TrustRegistry(state.conn, authority.public)

        grant = issue_grant(
            authority, worker.public, ["capability:math.scale"], 100, now=100
        )
        trust.accept(grant, now=100)
        self.assertTrue(trust.authorise("worker", "math.scale", now=150))
        self.assertFalse(trust.authorise("worker", "other", now=150))
        self.assertFalse(trust.authorise("worker", "math.scale", now=201))

        replacement_grant = issue_grant(
            authority, replacement.public, ["capability:math.scale"], 100, now=300
        )
        trust.replace_for_node(replacement_grant, now=300)
        self.assertEqual(
            trust.identity("worker", now=301).public_key_b64,
            replacement.public.public_key_b64,
        )
        trust.revoke(replacement_grant.grant_id, now=320)
        self.assertFalse(trust.authorise("worker", "math.scale", now=321))

    def test_distributed_coordinator_enforces_trust_scope(self):
        with tempfile.TemporaryDirectory() as d:
            server = PulseHTTPServer("127.0.0.1", 0, "token")
            server.start()
            host, port = server.address
            client = HTTPTransportClient(f"http://{host}:{port}", "token")

            coordinator_identity = NodeIdentity("coordinator")
            worker_identity = NodeIdentity("worker")
            trust_state = SQLiteState(os.path.join(d, "trust.db"))
            trust = TrustRegistry(trust_state.conn, coordinator_identity.public)
            trust.accept(
                issue_grant(
                    coordinator_identity,
                    worker_identity.public,
                    ["capability:math.scale"],
                    1000,
                )
            )

            coordinator = DistributedCoordinator(
                "net",
                coordinator_identity,
                os.path.join(d, "coordinator.db"),
                client,
                {},
                trust_registry=trust,
            )
            worker = DistributedWorker(
                "worker",
                "net",
                coordinator_identity.public,
                worker_identity,
                LocalPolicy(allowed_capabilities={"math.scale"}),
                os.path.join(d, "worker.db"),
                client,
            )
            worker.register(
                "math.scale",
                lambda args: {"value": args["value"] * 2},
            )

            with self.assertRaises(PermissionError):
                coordinator.dispatch("worker", "shell.exec", {})

            task = coordinator.dispatch(
                "worker", "math.scale", {"value": 4}
            )
            worker.poll_once()
            coordinator.collect_once()
            self.assertEqual(
                coordinator.results(task)[0]["output"]["value"],
                8,
            )
            worker.close()
            coordinator.close()
            trust_state.conn.close()
            server.close()

    def test_durable_transport_survives_server_restart(self):
        from rsqs_pulse.model import Pulse
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "events.db")
            server = PulseHTTPServer(
                "127.0.0.1", 0, "token", store_path=path
            )
            server.start()
            host, port = server.address
            client = HTTPTransportClient(f"http://{host}:{port}", "token")
            pulse = Pulse.new("net", 1, "WAKE", {"x": 1}, 60)
            client.publish(pulse)
            server.close()

            restored = PulseHTTPServer(
                "127.0.0.1", 0, "token", store_path=path
            )
            restored.start()
            host, port = restored.address
            restored_client = HTTPTransportClient(
                f"http://{host}:{port}", "token"
            )
            cursor, events = restored_client.poll(0)
            self.assertEqual(cursor, 1)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].pulse_id, pulse.pulse_id)
            restored.close()

    def test_observer_reports_unresolved_trust_and_strategy_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            runtime = FabricRuntime(
                "node",
                os.path.join(d, "runtime.db"),
                LocalPolicy(allowed_capabilities=set()),
            )
            runtime.operations.create("op", "act", "device", {}, now=1)
            runtime.operations.start("op", 1, now=1)
            runtime.operations.expire_running(now=3)

            authority = NodeIdentity("authority")
            trust = TrustRegistry(runtime.state.conn, authority.public)
            node = NodeIdentity("trusted-node")
            trust.accept(
                issue_grant(authority, node.public, ["read"], 1000)
            )
            store = ResilienceStore(runtime.state.conn)
            store.record_scenario("s1", {"shock": "test"})

            snapshot = FabricObserver(
                runtime,
                trust_registry=trust,
                resilience_store=store,
            ).snapshot()
            self.assertEqual(snapshot.status, "degraded")
            self.assertEqual(snapshot.unresolved_operations[0]["state"], "unknown")
            self.assertEqual(snapshot.trust["active_nodes"], 1)
            self.assertEqual(snapshot.strategy_evidence["scenarios"], 1)
            runtime.close()

    def test_bounded_search_explores_only_admissible_paths_and_respects_cap(self):
        optimizer = TrajectoryOptimizer()
        search = BoundedTrajectorySearch(
            optimizer,
            SearchConfig(max_depth=5, beam_width=2, max_candidates=6),
        )
        seed = TrajectoryCandidate(
            "root", actions=[{"value": 0}]
        )

        def expand(parent, depth):
            value = parent.actions[-1]["value"]
            return [
                TrajectoryCandidate(
                    f"{parent.trajectory_id}.{delta}",
                    actions=parent.actions + [{"value": value + delta}],
                )
                for delta in (1, 2)
            ]

        result = search.search(
            [seed],
            expand,
            lambda candidate: candidate.actions[-1]["value"] <= 4,
            lambda candidate: {
                "capability_retention": candidate.actions[-1]["value"]
            },
        )
        self.assertLessEqual(result.explored, 6)
        self.assertIsNotNone(result.selected)
        self.assertLessEqual(
            result.selected.actions[-1]["value"], 4
        )
        self.assertTrue(all(item.validated for item in result.ranked))

    def test_target_agnostic_adapter_applies_to_runtime_resources_and_dependencies(self):
        with tempfile.TemporaryDirectory() as d:
            adapter = MappingDomainAdapter(
                MappingSpec(
                    source="external-feed",
                    observation_fields={"system.load": "load"},
                    resource_name_field="resource",
                    quantity_field="quantity",
                    unit_field="unit",
                    location_field="location",
                    quality_field="quality",
                )
            )
            batch = adapter.ingest([
                {
                    "load": 0.7,
                    "resource": "input-a",
                    "quantity": 12,
                    "unit": "kg",
                    "location": "site",
                    "quality": 0.9,
                }
            ])
            batch = AdapterBatch(
                observations=batch.observations,
                resources=batch.resources,
                dependencies=(
                    CanonicalDependency(
                        "process",
                        resource="input-a",
                        quantity=10,
                        unit="kg",
                    ),
                ),
                rules=(
                    CanonicalRule(
                        "rule-1",
                        "process",
                        "require",
                        "audit",
                        "policy-source",
                    ),
                ),
                provenance=batch.provenance,
            )
            runtime = FabricRuntime(
                "node",
                os.path.join(d, "runtime.db"),
                LocalPolicy(allowed_capabilities=set()),
            )
            inventory = ResourceInventory(runtime.state.conn)
            graph = DependencyGraph()
            rules = []
            counts = apply_adapter_batch(
                batch,
                runtime=runtime,
                inventory=inventory,
                graph=graph,
                rule_sink=rules.append,
            )
            self.assertEqual(runtime.current_state().values["system.load"], 0.7)
            self.assertEqual(inventory.available("input-a", "kg"), 12)
            self.assertEqual(
                graph.resource_requirements["process"][0].resource,
                "input-a",
            )
            self.assertEqual(rules[0].rule_id, "rule-1")
            self.assertEqual(counts["provenance"], 1)
            runtime.close()

    def _make_multihost_fixture(self):
        authority = NodeIdentity("authority")
        identities = {
            "coordinator": NodeIdentity("coordinator"),
            "worker-a": NodeIdentity("worker-a"),
            "worker-b": NodeIdentity("worker-b"),
        }
        state = SQLiteState(":memory:")
        trust = TrustRegistry(state.conn, authority.public)
        for identity in identities.values():
            trust.accept(
                issue_grant(
                    authority,
                    identity.public,
                    ["proof:multi_host"],
                    1000,
                    now=100,
                ),
                now=100,
            )
        return state, trust, identities

    def test_signed_multihost_acceptance_harness(self):
        state, trust, identities = self._make_multihost_fixture()
        evidence = []
        for role, host in (
            ("coordinator", "host-1"),
            ("worker-a", "host-2"),
            ("worker-b", "host-3"),
        ):
            evidence.append(
                issue_host_evidence(
                    identities[role],
                    host,
                    "host_attestation",
                    {"role": role},
                    now=200,
                )
            )

        assignment = [
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
        ]
        for event, node in assignment:
            evidence.append(
                issue_host_evidence(
                    identities[node],
                    f"host-{1 if node == 'coordinator' else 2 if node == 'worker-a' else 3}",
                    event,
                    {},
                    now=210,
                )
            )
        for node, host in (("worker-a", "host-2"), ("worker-b", "host-3")):
            evidence.append(
                issue_host_evidence(
                    identities[node],
                    host,
                    "key_isolation_attested",
                    {"coordinator_private_key_present": False},
                    now=220,
                )
            )

        report = MultiHostAcceptanceVerifier(trust).assess(evidence)
        self.assertTrue(report.passed)
        self.assertEqual(len(report.host_instances), 3)
        state.conn.close()

    def test_multihost_harness_rejects_same_host_claim(self):
        state, trust, identities = self._make_multihost_fixture()
        evidence = [
            issue_host_evidence(
                identity,
                "same-host",
                "host_attestation",
                {"role": role},
                now=200,
            )
            for role, identity in identities.items()
        ]
        report = MultiHostAcceptanceVerifier(trust).assess(evidence)
        self.assertFalse(report.passed)
        state.conn.close()


if __name__ == "__main__":
    unittest.main()
