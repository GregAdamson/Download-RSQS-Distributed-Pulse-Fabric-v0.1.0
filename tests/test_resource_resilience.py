import unittest

from rsqs_pulse.dependency_graph import CapabilityRequirement, DependencyGraph, ResourceRequirement
from rsqs_pulse.persistent import SQLiteState
from rsqs_pulse.resilience import ResiliencePlanner, ScarcityAnalyzer
from rsqs_pulse.resource_state import ResourceInventory
from rsqs_pulse.substitution import Substitution, SubstitutionGraph


class ResourceResilienceTests(unittest.TestCase):
    def test_resource_quality_threshold_can_fail_capability(self):
        state = SQLiteState(":memory:")
        inventory = ResourceInventory(state.conn)
        inventory.observe("water", 100, "L", "farm", "sensor", quality=.4)
        graph = DependencyGraph()
        graph.require_resource("irrigate", ResourceRequirement("water", 50, "L", minimum_quality=.8))
        status = graph.evaluate("irrigate", inventory)
        self.assertFalse(status.operational)
        self.assertEqual(status.missing_resources[0].resource, "water")

    def test_capability_failure_propagates_downstream(self):
        state = SQLiteState(":memory:")
        inventory = ResourceInventory(state.conn)
        graph = DependencyGraph()
        graph.require_resource("pump", ResourceRequirement("electricity", 10, "kWh"))
        graph.require_capability("irrigate", CapabilityRequirement("pump"))
        self.assertFalse(graph.evaluate("pump", inventory).operational)
        self.assertFalse(graph.evaluate("irrigate", inventory).operational)
        self.assertEqual(graph.evaluate("irrigate", inventory).failed_dependencies, ("pump",))

    def test_dependency_cycle_is_rejected(self):
        graph = DependencyGraph()
        graph.require_capability("a", CapabilityRequirement("b"))
        with self.assertRaises(ValueError):
            graph.require_capability("b", CapabilityRequirement("a"))

    def test_substitution_ratio_restores_shortage(self):
        state = SQLiteState(":memory:")
        inventory = ResourceInventory(state.conn)
        inventory.observe("diesel", 20, "L", "site", "meter")
        inventory.observe("biodiesel", 44, "L", "site", "meter")
        graph = DependencyGraph()
        graph.require_resource("generator", ResourceRequirement("diesel", 60, "L", location="site"))
        substitutions = SubstitutionGraph()
        substitutions.add(Substitution("diesel", "biodiesel", 1.1, {}))
        plan = ResiliencePlanner(substitutions).plan("generator", graph, inventory)
        self.assertTrue(plan.viable)
        self.assertEqual(len(plan.allocations), 1)
        self.assertAlmostEqual(plan.allocations[0].substitute_quantity, 44.0)

    def test_insufficient_substitute_remains_unresolved(self):
        state = SQLiteState(":memory:")
        inventory = ResourceInventory(state.conn)
        inventory.observe("diesel", 20, "L", "site", "meter")
        inventory.observe("biodiesel", 10, "L", "site", "meter")
        graph = DependencyGraph()
        graph.require_resource("generator", ResourceRequirement("diesel", 60, "L", location="site"))
        substitutions = SubstitutionGraph()
        substitutions.add(Substitution("diesel", "biodiesel", 1.0, {}))
        plan = ResiliencePlanner(substitutions).plan("generator", graph, inventory)
        self.assertFalse(plan.viable)
        self.assertAlmostEqual(plan.unresolved[0].quantity, 30.0)

    def test_scarcity_quantifies_shortage_and_affected_capabilities(self):
        state = SQLiteState(":memory:")
        inventory = ResourceInventory(state.conn)
        inventory.observe("copper", 30, "kg", "warehouse", "inventory")
        graph = DependencyGraph()
        graph.require_resource("motor.build", ResourceRequirement("copper", 20, "kg"))
        graph.require_resource("transformer.build", ResourceRequirement("copper", 30, "kg"))
        finding = ScarcityAnalyzer().analyze(graph, inventory)[0]
        self.assertEqual(finding.resource, "copper")
        self.assertAlmostEqual(finding.required, 50)
        self.assertAlmostEqual(finding.available, 30)
        self.assertAlmostEqual(finding.shortage, 20)
        self.assertAlmostEqual(finding.shortage_ratio, .4)
        self.assertEqual(finding.affected_capabilities, ("motor.build", "transformer.build"))

    def test_resource_inventory_persists(self):
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "resources.db")
            state = SQLiteState(path)
            ResourceInventory(state.conn).observe("water", 12, "ML", "dam", "telemetry", owner="farm-a")
            state.conn.close()
            restored = SQLiteState(path)
            inventory = ResourceInventory(restored.conn)
            self.assertEqual(inventory.available("water", "ML"), 12)
            self.assertEqual(inventory.lots("water")[0].owner, "farm-a")
            restored.conn.close()


if __name__ == "__main__":
    unittest.main()
