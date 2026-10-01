import os
import sys
import unittest
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from rsqs_pulse.broker import InMemoryBroker
from rsqs_pulse.capabilities import CapabilityAdvertisement, CapabilityRegistry
from rsqs_pulse.federation import FederationScope, within_scope
from rsqs_pulse.identity import NodeIdentity
from rsqs_pulse.intent import DeterministicIntentCompiler, IntentStep
from rsqs_pulse.manifests import AgentManifest, sign_manifest, verify_manifest
from rsqs_pulse.model import Pulse
from rsqs_pulse.offline import OfflineJournal
from rsqs_pulse.persistent import SQLiteState
from rsqs_pulse.policy import LocalPolicy
from rsqs_pulse.provenance import ProvenanceLedger
from rsqs_pulse.quorum import QuorumRule
from rsqs_pulse.resources import ResourceProfile
from rsqs_pulse.routing import ResourceAwareRouter
from rsqs_pulse.secure import SecureCoordinator, SecureNode
from rsqs_pulse.simulation import Simulator
from rsqs_pulse.subscriptions import Subscription, SubscriptionRouter
from rsqs_pulse.swarm import SwarmPlanner
from rsqs_pulse.taskgraph import GraphTask, GraphExecutor, TaskGraph
from rsqs_pulse.world_state import WorldState


class V02Tests(unittest.TestCase):
    def test_ed25519_secure_task_and_persistent_epoch(self):
        broker = InMemoryBroker()
        authority = NodeIdentity("authority")
        cstate = SQLiteState(":memory:")
        coordinator = SecureCoordinator("net", authority, broker, cstate)
        nstate = SQLiteState(":memory:")
        node = SecureNode("n1", "net", authority.public, LocalPolicy(allowed_capabilities={"echo"}), nstate)
        node.register("echo", lambda args: {"echo": args["x"]})
        broker.subscribe(node.receive)
        coordinator.emit("TASK", {"task_id": "t1", "capability": "echo", "operation": "run", "args": {"x": 7}})
        row = nstate.conn.execute("SELECT status,output_json FROM results WHERE task_id='t1'").fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(node.last_epoch, 1)
        restored = SecureNode("n1", "net", authority.public, LocalPolicy(allowed_capabilities={"echo"}), nstate)
        self.assertEqual(restored.last_epoch, 1)

    def test_wrong_authority_rejected(self):
        broker = InMemoryBroker()
        authority = NodeIdentity("authority")
        wrong = NodeIdentity("wrong")
        coordinator = SecureCoordinator("net", wrong, broker, SQLiteState(":memory:"))
        state = SQLiteState(":memory:")
        node = SecureNode("n1", "net", authority.public, LocalPolicy(), state)
        broker.subscribe(node.receive)
        coordinator.emit("WAKE", {})
        self.assertEqual(node.last_epoch, -1)

    def test_capability_registry_and_swarm(self):
        state = SQLiteState(":memory:")
        registry = CapabilityRegistry(state)
        registry.advertise(CapabilityAdvertisement("a", "search", metadata={"region": "au"}))
        registry.advertise(CapabilityAdvertisement("b", "search", metadata={"region": "us"}))
        self.assertEqual([x.node_id for x in registry.choose("search", {"region": "au"})], ["a"])
        swarm = SwarmPlanner(registry).assemble("s1", {"search": 2})
        self.assertEqual(len(swarm.members), 2)

    def test_task_graph_and_simulation(self):
        graph = TaskGraph([
            GraphTask("a", "one"),
            GraphTask("b", "two", depends_on=("a",)),
        ])
        order = [x.task_id for x in graph.topological_order()]
        self.assertEqual(order, ["a", "b"])
        result = GraphExecutor(lambda task, deps: {"task": task.task_id, "deps": sorted(deps)}).run(graph)
        self.assertEqual(result["b"]["deps"], ["a"])
        sim = Simulator(lambda task: (task.capability == "one", "policy"))
        self.assertEqual([x.admitted for x in sim.dry_run(graph)], [True, False])

    def test_cycle_fails(self):
        with self.assertRaises(ValueError):
            TaskGraph([
                GraphTask("a", "x", depends_on=("b",)),
                GraphTask("b", "x", depends_on=("a",)),
            ])

    def test_quorum_fail_closed(self):
        rule = QuorumRule(minimum_approvals=2, minimum_total=3)
        self.assertFalse(rule.decide({"a": True, "b": True}))
        self.assertTrue(rule.decide({"a": True, "b": True, "c": False}))

    def test_provenance_chain(self):
        state = SQLiteState(":memory:")
        ledger = ProvenanceLedger(state.conn)
        ledger.append("a", "1", {"x": 1})
        ledger.append("b", "2", {"y": 2})
        self.assertTrue(ledger.verify())
        state.conn.execute("UPDATE provenance SET payload_json='{}' WHERE seq=1")
        state.conn.commit()
        self.assertFalse(ledger.verify())

    def test_offline_reconciliation_is_ordered(self):
        state = SQLiteState(":memory:")
        journal = OfflineJournal("n", state)
        journal.append({"v": 1})
        journal.append({"v": 2})
        seen = []
        count = journal.reconcile(lambda event: seen.append(event["v"]) is None or True)
        self.assertEqual(count, 2)
        self.assertEqual(seen, [1, 2])

    def test_federation_scope(self):
        scope = FederationScope("institute", "au")
        self.assertTrue(within_scope("rsqs.au.institute.research", scope))
        self.assertFalse(within_scope("rsqs.us.institute.research", scope))

    def test_world_state_versioning(self):
        state = SQLiteState(":memory:")
        world = WorldState(state.conn)
        world.assert_fact("weather", {"state": "dry"}, "sensor-a", 0.8)
        world.assert_fact("weather", {"state": "wet"}, "sensor-b", 0.9)
        latest = world.latest("weather")
        self.assertEqual(latest.version, 2)
        self.assertEqual(latest.value["state"], "wet")
        self.assertEqual(len(world.history("weather")), 2)

    def test_resource_aware_routing(self):
        state = SQLiteState(":memory:")
        registry = CapabilityRegistry(state)
        registry.advertise(CapabilityAdvertisement("a", "compute"))
        registry.advertise(CapabilityAdvertisement("b", "compute"))
        resources = {
            "a": ResourceProfile("a", 0.2, 512, 1000, 50),
            "b": ResourceProfile("b", 0.8, 4096, 10000, 10),
        }
        choice = ResourceAwareRouter().choose(registry.providers("compute"), resources, limit=1)
        self.assertEqual(choice[0].node_id, "b")

    def test_signed_agent_manifest(self):
        authority = NodeIdentity("authority")
        manifest = AgentManifest(
            "agent.demo",
            "1.0",
            "abc123",
            ("search",),
            ("read-local",),
            {"purpose": "test"},
        )
        signature = sign_manifest(manifest, authority)
        self.assertTrue(verify_manifest(manifest, signature, authority.public))
        other = NodeIdentity("other")
        self.assertFalse(verify_manifest(manifest, signature, other.public))
        self.assertTrue(manifest.content_address().startswith("agent://sha256/"))

    def test_subscription_router(self):
        router = SubscriptionRouter()
        seen = []
        router.subscribe(Subscription("a", ("WAKE",)), lambda p: seen.append(("a", p.kind)))
        router.subscribe(Subscription("b", ("*",)), lambda p: seen.append(("b", p.kind)))
        pulse = Pulse.new("n", 1, "WAKE", {})
        delivered = router.publish(pulse)
        self.assertEqual(delivered, ["a", "b"])
        self.assertEqual(len(seen), 2)

    def test_deterministic_intent_compiler(self):
        compiler = DeterministicIntentCompiler()
        steps = [
            IntentStep("collect", {"q": "x"}),
            IntentStep("analyse", {"mode": "strict"}, (0,)),
        ]
        g1 = compiler.compile("intent-1", steps)
        g2 = compiler.compile("intent-1", steps)
        self.assertEqual([x.task_id for x in g1.topological_order()], [x.task_id for x in g2.topological_order()])
        self.assertEqual(g1.topological_order()[1].depends_on, (g1.topological_order()[0].task_id,))


if __name__ == "__main__":
    unittest.main()
