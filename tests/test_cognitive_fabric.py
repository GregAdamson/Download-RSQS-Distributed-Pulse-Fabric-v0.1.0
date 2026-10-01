import unittest

from rsqs_pulse.capabilities import CapabilityAdvertisement, CapabilityRegistry
from rsqs_pulse.cognitive_loop import CognitiveLoop, Observation
from rsqs_pulse.dal import DALGraph, DALNode
from rsqs_pulse.fractal import FabricDescriptor, FabricRegistry
from rsqs_pulse.institutional_api import InstitutionalCapability, InstitutionalGateway
from rsqs_pulse.institutions import InstitutionAssembler, RoleRequirement
from rsqs_pulse.oracle import DistributedOracle, EvidenceClaim
from rsqs_pulse.persistent import SQLiteState
from rsqs_pulse.resource_exchange import ResourceExchange, ResourceNeed, ResourceOffer
from rsqs_pulse.state_reasoning import Constraint, State, TrajectoryPlanner, Transition


class CognitiveFabricTests(unittest.TestCase):
    def test_state_trajectory_and_authority(self):
        planner = TrajectoryPlanner()
        transitions = [
            Transition("increment", "counter.increment", lambda s: State({"n": s.values["n"] + 1}), cost=1),
        ]
        constraints = [Constraint("limit", lambda s: s.values["n"] <= 3)]
        paths = planner.plan(State({"n": 0}), lambda s: s.values["n"] == 2, transitions, constraints)
        self.assertEqual(paths[0].final_state.values["n"], 2)
        loop = CognitiveLoop(planner)
        perceived = loop.perceive(State({"n": 0}), [Observation("sensor", {"n": 1})])
        decision = loop.decide(
            perceived,
            lambda s: s.values["n"] == 2,
            transitions,
            constraints,
            lambda trajectory: (True, "local policy permits"),
        )
        self.assertTrue(decision.authorised)

    def test_oracle_preserves_disagreement(self):
        claims = [
            EvidenceClaim("a", "p", True, 0.9, "e1"),
            EvidenceClaim("b", "p", False, 0.8, "e2"),
        ]
        assessment = DistributedOracle().assess("p", claims)
        self.assertGreater(assessment.support_weight, 0)
        self.assertGreater(assessment.oppose_weight, 0)
        self.assertEqual(len(assessment.evidence), 2)

    def test_resource_exchange(self):
        matches = ResourceExchange().match(
            [ResourceOffer("farm-a", "water", 10, "ML", {"region": "x"})],
            [ResourceNeed("farm-b", "water", 4, "ML", {"region": "x"})],
        )
        self.assertEqual(matches[0].quantity, 4)

    def test_temporary_institution(self):
        state = SQLiteState(":memory:")
        registry = CapabilityRegistry(state)
        registry.advertise(CapabilityAdvertisement("research-node", "research"))
        registry.advertise(CapabilityAdvertisement("verify-node", "verify"))
        institution = InstitutionAssembler(registry).assemble(
            "inst-1",
            "answer question",
            [RoleRequirement("researcher", "research"), RoleRequirement("verifier", "verify")],
            {"execute": "local-only"},
        )
        self.assertEqual(len(institution.members), 2)

    def test_fractal_fabrics(self):
        registry = FabricRegistry()
        registry.register(FabricDescriptor("local-a", "local", ("sense",), ("local",)))
        registry.register(FabricDescriptor("regional-a", "regional", ("analyse",), ("regional",), ("local-a",)))
        self.assertEqual(registry.get("regional-a").children, ("local-a",))
        self.assertEqual(registry.providers("sense")[0].fabric_id, "local-a")

    def test_dal_graph(self):
        graph = DALGraph()
        graph.add_node(DALNode("OBSERVATION", "o1", {"value": 1}))
        graph.add_node(DALNode("STATE", "s1", {"value": 1}))
        graph.connect("o1", "updates", "s1")
        nodes, edges = graph.snapshot()
        self.assertEqual(len(nodes), 2)
        self.assertEqual(edges[0].relation, "updates")

    def test_institutional_gateway_requires_write_authority(self):
        gateway = InstitutionalGateway()
        gateway.expose(InstitutionalCapability("status", "read status", lambda args: {"ok": True}))
        gateway.expose(InstitutionalCapability("change", "change state", lambda args: {"changed": True}, read_only=False))
        self.assertTrue(gateway.invoke("status", {})["ok"])
        with self.assertRaises(PermissionError):
            gateway.invoke("change", {})
        self.assertTrue(gateway.invoke("change", {}, allow_write=True)["changed"])


if __name__ == "__main__":
    unittest.main()
