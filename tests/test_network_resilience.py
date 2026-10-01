import unittest

from rsqs_pulse.dependency_graph import CapabilityRequirement, DependencyGraph, ResourceRequirement
from rsqs_pulse.network_resilience import NetworkResiliencePlanner, RecoveryTarget, ResourceShock
from rsqs_pulse.persistent import SQLiteState
from rsqs_pulse.resource_state import ResourceInventory
from rsqs_pulse.substitution import Substitution, SubstitutionGraph


class NetworkResilienceTests(unittest.TestCase):
    def make_inventory(self):
        state = SQLiteState(":memory:")
        return state, ResourceInventory(state.conn)

    def test_shared_substitute_stock_is_not_double_counted(self):
        state, inventory = self.make_inventory()
        inventory.observe("biodiesel", 60, "L", "site", "stock")
        graph = DependencyGraph()
        graph.require_resource("priority-a", ResourceRequirement("diesel", 50, "L", location="site"))
        graph.require_resource("priority-b", ResourceRequirement("diesel", 50, "L", location="site"))
        substitutions = SubstitutionGraph()
        substitutions.add(Substitution("diesel", "biodiesel", 1.0, {}))
        plan = NetworkResiliencePlanner(substitutions).plan(
            [RecoveryTarget("priority-b", 1), RecoveryTarget("priority-a", 10)],
            graph,
            inventory,
        )
        self.assertEqual(plan.recovered_targets, ("priority-a",))
        self.assertEqual(plan.failed_targets, ("priority-b",))
        used = sum(x.supplied_quantity for x in plan.allocations if x.supplied_resource == "biodiesel")
        self.assertAlmostEqual(used, 50.0)

    def test_failed_high_priority_path_rolls_back_allocations(self):
        state, inventory = self.make_inventory()
        inventory.observe("biodiesel", 40, "L", "site", "stock")
        graph = DependencyGraph()
        graph.require_resource("complex", ResourceRequirement("diesel", 40, "L", location="site"))
        graph.require_resource("complex", ResourceRequirement("copper", 100, "kg", location="site"))
        graph.require_resource("simple", ResourceRequirement("diesel", 40, "L", location="site"))
        substitutions = SubstitutionGraph()
        substitutions.add(Substitution("diesel", "biodiesel", 1.0, {}))
        plan = NetworkResiliencePlanner(substitutions).plan(
            [RecoveryTarget("complex", 10), RecoveryTarget("simple", 1)],
            graph,
            inventory,
        )
        self.assertEqual(plan.failed_targets, ("complex",))
        self.assertEqual(plan.recovered_targets, ("simple",))
        used = sum(x.supplied_quantity for x in plan.allocations if x.supplied_resource == "biodiesel")
        self.assertAlmostEqual(used, 40.0)

    def test_shared_dependency_is_allocated_only_once(self):
        state, inventory = self.make_inventory()
        inventory.observe("electricity", 10, "kWh", "site", "meter")
        inventory.observe("water", 20, "L", "site", "tank")
        graph = DependencyGraph()
        graph.require_resource("pump", ResourceRequirement("electricity", 10, "kWh", location="site"))
        graph.require_capability("irrigate-a", CapabilityRequirement("pump"))
        graph.require_capability("irrigate-b", CapabilityRequirement("pump"))
        graph.require_resource("irrigate-a", ResourceRequirement("water", 10, "L", location="site"))
        graph.require_resource("irrigate-b", ResourceRequirement("water", 10, "L", location="site"))
        plan = NetworkResiliencePlanner(SubstitutionGraph()).plan(
            [RecoveryTarget("irrigate-a"), RecoveryTarget("irrigate-b")],
            graph,
            inventory,
        )
        self.assertTrue(plan.viable)
        electricity = [x for x in plan.allocations if x.supplied_resource == "electricity"]
        self.assertEqual(len(electricity), 1)
        self.assertAlmostEqual(electricity[0].supplied_quantity, 10.0)

    def test_resource_shock_propagates_through_dependencies(self):
        state, inventory = self.make_inventory()
        inventory.observe("electricity", 10, "kWh", "site", "meter")
        graph = DependencyGraph()
        graph.require_resource("pump", ResourceRequirement("electricity", 10, "kWh", location="site"))
        graph.require_capability("irrigate", CapabilityRequirement("pump"))
        plan = NetworkResiliencePlanner(SubstitutionGraph()).plan(
            [RecoveryTarget("irrigate")],
            graph,
            inventory,
            shocks=[ResourceShock("electricity", 1.0, unit="kWh", location="site")],
        )
        self.assertFalse(plan.viable)
        self.assertEqual(plan.failed_targets, ("irrigate",))

    def test_substitution_can_recover_upstream_dependency(self):
        state, inventory = self.make_inventory()
        inventory.observe("battery", 10, "kWh", "site", "battery")
        graph = DependencyGraph()
        graph.require_resource("pump", ResourceRequirement("grid-electricity", 10, "kWh", location="site"))
        graph.require_capability("irrigate", CapabilityRequirement("pump"))
        substitutions = SubstitutionGraph()
        substitutions.add(Substitution("grid-electricity", "battery", 1.0, {}))
        plan = NetworkResiliencePlanner(substitutions).plan(
            [RecoveryTarget("irrigate")], graph, inventory
        )
        self.assertTrue(plan.viable)
        self.assertIn("pump", plan.operational_capabilities)
        self.assertIn("irrigate", plan.operational_capabilities)
        self.assertEqual(plan.allocations[0].supplied_resource, "battery")

    def test_partial_shock_leaves_effective_quantity(self):
        state, inventory = self.make_inventory()
        inventory.observe("gas", 100, "GJ", "plant", "meter")
        graph = DependencyGraph()
        graph.require_resource("heat", ResourceRequirement("gas", 40, "GJ", location="plant"))
        plan = NetworkResiliencePlanner(SubstitutionGraph()).plan(
            [RecoveryTarget("heat")],
            graph,
            inventory,
            shocks=[ResourceShock("gas", .5, unit="GJ", location="plant")],
        )
        self.assertTrue(plan.viable)
        self.assertAlmostEqual(plan.allocations[0].supplied_quantity, 40.0)

    def test_quality_constraints_apply_to_substitutes(self):
        state, inventory = self.make_inventory()
        inventory.observe("backup-water", 100, "L", "site", "tank", quality=.4)
        graph = DependencyGraph()
        graph.require_resource("process", ResourceRequirement("water", 50, "L", minimum_quality=.8, location="site"))
        substitutions = SubstitutionGraph()
        substitutions.add(Substitution("water", "backup-water", 1.0, {}))
        plan = NetworkResiliencePlanner(substitutions).plan(
            [RecoveryTarget("process")], graph, inventory
        )
        self.assertFalse(plan.viable)


if __name__ == "__main__":
    unittest.main()
