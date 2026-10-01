import datetime
import ipaddress
import json
import os
import queue
import ssl
import tempfile
import threading
import unittest
import urllib.request

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from rsqs_pulse.daemon import RuntimeHTTPDaemon
from rsqs_pulse.dependency_graph import DependencyGraph
from rsqs_pulse.distributed_runtime import DistributedCoordinator
from rsqs_pulse.domain_adapter import CanonicalRule
from rsqs_pulse.http_transport import HTTPTransportClient, PulseHTTPServer
from rsqs_pulse.identity import NodeIdentity
from rsqs_pulse.institutional_rules import InstitutionalRuleStore
from rsqs_pulse.model import Pulse
from rsqs_pulse.observability import FabricObserver
from rsqs_pulse.persistent import SQLiteState
from rsqs_pulse.policy import LocalPolicy
from rsqs_pulse.runtime import FabricRuntime
from rsqs_pulse.trajectory_optimizer import TrajectoryCandidate, TrajectoryOptimizer
from rsqs_pulse.trajectory_search import (
    ExhaustiveTrajectorySearch,
    SearchConfig,
)
from rsqs_pulse.trust_plane import TrustRegistry, issue_grant
from rsqs_pulse.trusted_capabilities import (
    TrustedCapabilityRegistry,
    sign_capability_advertisement,
)


class OperationalV09ExtendedTests(unittest.TestCase):
    def test_signed_capability_advertisement_tracks_key_rotation(self):
        authority = NodeIdentity("authority")
        worker = NodeIdentity("worker")
        replacement = NodeIdentity("worker")
        state = SQLiteState(":memory:")
        trust = TrustRegistry(state.conn, authority.public)
        trust.accept(
            issue_grant(
                authority,
                worker.public,
                ["capability:measure"],
                1000,
                now=100,
            ),
            now=100,
        )
        registry = TrustedCapabilityRegistry(state.conn, trust)
        ad = sign_capability_advertisement(
            worker,
            "measure",
            ttl_seconds=500,
            now=110,
        )
        registry.accept(ad, now=110)
        self.assertEqual(registry.providers("measure", now=120)[0].node_id, "worker")

        trust.replace_for_node(
            issue_grant(
                authority,
                replacement.public,
                ["capability:measure"],
                1000,
                now=200,
            ),
            now=200,
        )
        self.assertEqual(registry.providers("measure", now=201), ())

        replacement_ad = sign_capability_advertisement(
            replacement,
            "measure",
            ttl_seconds=500,
            now=201,
        )
        registry.accept(replacement_ad, now=201)
        self.assertEqual(
            registry.providers("measure", now=202)[0].advertisement_id,
            replacement_ad.advertisement_id,
        )

    def test_coordinator_can_require_signed_capability_advertisement(self):
        with tempfile.TemporaryDirectory() as d:
            server = PulseHTTPServer("127.0.0.1", 0, "token")
            server.start()
            host, port = server.address
            client = HTTPTransportClient(f"http://{host}:{port}", "token")
            authority = NodeIdentity("authority")
            worker = NodeIdentity("worker")
            trust_state = SQLiteState(os.path.join(d, "trust.db"))
            trust = TrustRegistry(trust_state.conn, authority.public)
            trust.accept(
                issue_grant(
                    authority,
                    worker.public,
                    ["capability:measure"],
                    1000,
                )
            )
            capabilities = TrustedCapabilityRegistry(trust_state.conn, trust)
            coordinator = DistributedCoordinator(
                "net",
                authority,
                os.path.join(d, "coordinator.db"),
                client,
                {},
                trust_registry=trust,
                capability_registry=capabilities,
            )
            with self.assertRaises(PermissionError):
                coordinator.dispatch("worker", "measure", {})

            capabilities.accept(
                sign_capability_advertisement(
                    worker,
                    "measure",
                    ttl_seconds=1000,
                )
            )
            task_id = coordinator.dispatch("worker", "measure", {})
            self.assertTrue(task_id)
            coordinator.close()
            trust_state.conn.close()
            server.close()

    def test_exhaustive_search_reports_complete_and_truncated_spaces(self):
        def expand(parent, depth):
            value = parent.actions[-1]["value"]
            return [
                TrajectoryCandidate(
                    f"{parent.trajectory_id}.{delta}",
                    actions=parent.actions + [{"value": value + delta}],
                )
                for delta in (1, 2)
            ]

        validator = lambda candidate: candidate.actions[-1]["value"] <= 4
        metrics = lambda candidate: {
            "capability_retention": candidate.actions[-1]["value"]
        }
        root = TrajectoryCandidate("root", actions=[{"value": 0}])

        complete = ExhaustiveTrajectorySearch(
            TrajectoryOptimizer(),
            SearchConfig(max_depth=2, beam_width=2, max_candidates=20),
        ).search([root], expand, validator, metrics)
        self.assertTrue(complete.complete_within_bounds)
        self.assertFalse(complete.truncated_by_candidate_cap)
        self.assertEqual(complete.selected.actions[-1]["value"], 4)

        truncated = ExhaustiveTrajectorySearch(
            TrajectoryOptimizer(),
            SearchConfig(max_depth=5, beam_width=2, max_candidates=2),
        ).search(
            [TrajectoryCandidate("root", actions=[{"value": 0}])],
            expand,
            validator,
            metrics,
        )
        self.assertFalse(truncated.complete_within_bounds)
        self.assertTrue(truncated.truncated_by_candidate_cap)
        self.assertEqual(truncated.explored, 2)

    def test_institutional_rule_precedence_is_deterministic(self):
        state = SQLiteState(":memory:")
        rules = InstitutionalRuleStore(state.conn)
        rules.add(CanonicalRule("allow-global", "*", "allow", "*", "source"))
        rules.add(CanonicalRule("require-audit", "process", "require", "audit", "source"))
        rules.add(CanonicalRule("deny-audit", "process", "deny", "audit", "source"))

        decision = rules.decide("process", "audit")
        self.assertEqual(decision.effect, "deny")
        self.assertEqual(decision.rule_ids, ("deny-audit",))

        rules.remove("deny-audit")
        decision = rules.decide("process", "audit")
        self.assertEqual(decision.effect, "require")
        self.assertEqual(decision.rule_ids, ("require-audit",))

        decision = rules.decide("other", "anything")
        self.assertEqual(decision.effect, "allow")

    def test_tls_pulse_transport_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            subject = issuer = x509.Name([
                x509.NameAttribute(NameOID.COMMON_NAME, "localhost")
            ])
            now = datetime.datetime.now(datetime.timezone.utc)
            cert = (
                x509.CertificateBuilder()
                .subject_name(subject)
                .issuer_name(issuer)
                .public_key(key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(now - datetime.timedelta(minutes=1))
                .not_valid_after(now + datetime.timedelta(days=1))
                .add_extension(
                    x509.SubjectAlternativeName([
                        x509.IPAddress(ipaddress.ip_address("127.0.0.1"))
                    ]),
                    critical=False,
                )
                .sign(key, hashes.SHA256())
            )
            cert_path = os.path.join(d, "cert.pem")
            key_path = os.path.join(d, "key.pem")
            with open(cert_path, "wb") as fh:
                fh.write(cert.public_bytes(serialization.Encoding.PEM))
            with open(key_path, "wb") as fh:
                fh.write(
                    key.private_bytes(
                        serialization.Encoding.PEM,
                        serialization.PrivateFormat.PKCS8,
                        serialization.NoEncryption(),
                    )
                )

            server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            server_context.load_cert_chain(cert_path, key_path)
            client_context = ssl.create_default_context(cafile=cert_path)

            server = PulseHTTPServer(
                "127.0.0.1",
                0,
                "token",
                ssl_context=server_context,
            )
            server.start()
            host, port = server.address
            client = HTTPTransportClient(
                f"https://{host}:{port}",
                "token",
                ssl_context=client_context,
            )
            pulse = Pulse.new("net", 1, "WAKE", {"tls": True}, 60)
            client.publish(pulse)
            cursor, events = client.poll(0)
            self.assertEqual(cursor, 1)
            self.assertEqual(events[0].payload["tls"], True)
            server.close()

    def test_observability_http_endpoint(self):
        with tempfile.TemporaryDirectory() as d:
            ready = queue.Queue()
            state_path = os.path.join(d, "runtime.db")

            def serve():
                runtime = FabricRuntime(
                    "node",
                    state_path,
                    LocalPolicy(allowed_capabilities={"noop"}),
                )
                runtime.register_capability("noop", lambda args: {"ok": True})
                daemon = RuntimeHTTPDaemon(runtime, "127.0.0.1", 0)
                ready.put(daemon)
                daemon.serve_forever()
                runtime.close()

            thread = threading.Thread(target=serve, daemon=True)
            thread.start()
            daemon = ready.get(timeout=5)
            host, port = daemon.address
            with urllib.request.urlopen(
                f"http://{host}:{port}/observability",
                timeout=5,
            ) as response:
                payload = json.loads(response.read().decode("ascii"))
            self.assertEqual(payload["node_id"], "node")
            self.assertIn("noop", payload["capabilities"])
            self.assertTrue(payload["provenance_valid"])
            daemon.close()
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())


    def test_observer_exposes_bottleneck_and_selected_strategy(self):
        from rsqs_pulse.dependency_graph import ResourceRequirement
        from rsqs_pulse.resilience_store import ResilienceStore
        from rsqs_pulse.resource_state import ResourceInventory

        with tempfile.TemporaryDirectory() as d:
            runtime = FabricRuntime(
                "node",
                os.path.join(d, "runtime.db"),
                LocalPolicy(allowed_capabilities=set()),
            )
            inventory = ResourceInventory(runtime.state.conn)
            inventory.observe("water", 2, "L", "site", "meter")
            graph = DependencyGraph()
            graph.require_resource(
                "process",
                ResourceRequirement("water", 5, "L", location="site"),
            )
            store = ResilienceStore(runtime.state.conn)
            store.record_trajectory(
                "low",
                {"name": "low"},
                score=1.0,
                validated=True,
            )
            store.record_trajectory(
                "high",
                {"name": "high"},
                score=4.0,
                validated=True,
            )
            snapshot = FabricObserver(
                runtime,
                resilience_store=store,
                resource_inventory=inventory,
                dependency_graph=graph,
            ).snapshot()
            self.assertEqual(snapshot.resource_bottlenecks[0]["resource"], "water")
            self.assertEqual(snapshot.resource_bottlenecks[0]["shortage"], 3)
            self.assertEqual(snapshot.selected_trajectory["trajectory_id"], "high")
            runtime.close()


if __name__ == "__main__":
    unittest.main()
