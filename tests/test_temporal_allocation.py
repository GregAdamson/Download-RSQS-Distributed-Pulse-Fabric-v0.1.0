import unittest

from rsqs_pulse.dependency_graph import CapabilityRequirement, DependencyGraph, ResourceRequirement
from rsqs_pulse.persistent import SQLiteState
from rsqs_pulse.resource_state import ResourceInventory
from rsqs_pulse.substitution import Substitution, SubstitutionGraph
from rsqs_pulse.temporal_allocation import (
    CapabilityDemand,
    Replenishment,
    TemporalAllocationPlanner,
    TransportLink,
)


class TemporalAllocationTests(unittest.TestCase):
    def inventory(self):
        state = SQLiteState(":memory:")
        return state, ResourceInventory(state.conn)

    def test_stock_carries_forward_and_depletes(self):
        state, inventory = self.inventory()
        inventory.observe("fuel", 10, "L", "site", "stock")
        graph = DependencyGraph()
        graph.require_resource("run", ResourceRequirement("fuel", 4, "L", location="site"))
        plan = TemporalAllocationPlanner(SubstitutionGraph()).plan(
            3, [CapabilityDemand("run", (0, 1, 2))], graph, inventory
        )
        self.assertFalse(plan.viable)
        self.assertEqual(plan.first_failure_period, 2)
        self.assertEqual(plan.failed_demands, ((2, "run"),))

    def test_replenishment_arrives_before_period_demand(self):
        state, inventory = self.inventory()
        inventory.observe("fuel", 5, "L", "site", "stock")
        graph = DependencyGraph()
        graph.require_resource("run", ResourceRequirement("fuel", 5, "L", location="site"))
        plan = TemporalAllocationPlanner(SubstitutionGraph()).plan(
            2,
            [CapabilityDemand("run", (0, 1))],
            graph,
            inventory,
            replenishments=[Replenishment(1, "fuel", 5, "L", "site")],
        )
        self.assertTrue(plan.viable)

    def test_transport_prepositions_for_lead_time(self):
        state, inventory = self.inventory()
        inventory.observe("water", 10, "L", "source", "stock")
        graph = DependencyGraph()
        graph.require_resource("process", ResourceRequirement("water", 10, "L", location="dest"))
        link = TransportLink("source", "dest", "water", "L", 10, 2)
        plan = TemporalAllocationPlanner(SubstitutionGraph()).plan(
            3, [CapabilityDemand("process", (2,))], graph, inventory,
            transport_links=[link],
        )
        self.assertTrue(plan.viable)
        self.assertEqual(len(plan.periods[0].transfers_departed), 1)
        self.assertEqual(plan.periods[0].transfers_departed[0].arrive_period, 2)
        self.assertEqual(len(plan.periods[2].transfers_arrived), 1)

    def test_transport_capacity_shortfall_surfaces_failure(self):
        state, inventory = self.inventory()
        inventory.observe("water", 10, "L", "source", "stock")
        graph = DependencyGraph()
        graph.require_resource("process", ResourceRequirement("water", 10, "L", location="dest"))
        link = TransportLink("source", "dest", "water", "L", 5, 2)
        plan = TemporalAllocationPlanner(SubstitutionGraph()).plan(
            3, [CapabilityDemand("process", (2,))], graph, inventory,
            transport_links=[link],
        )
        self.assertFalse(plan.viable)
        self.assertEqual(plan.first_failure_period, 2)

    def test_current_demand_is_not_cannibalized_for_future(self):
        state, inventory = self.inventory()
        inventory.observe("water", 10, "L", "source", "stock")
        graph = DependencyGraph()
        graph.require_resource("today", ResourceRequirement("water", 10, "L", location="source"))
        graph.require_resource("tomorrow", ResourceRequirement("water", 10, "L", location="dest"))
        link = TransportLink("source", "dest", "water", "L", 10, 1)
        plan = TemporalAllocationPlanner(SubstitutionGraph()).plan(
            2,
            [CapabilityDemand("today", (0,), priority=10), CapabilityDemand("tomorrow", (1,), priority=1)],
            graph,
            inventory,
            transport_links=[link],
        )
        self.assertNotIn("today", plan.periods[0].failed_capabilities)
        self.assertIn("tomorrow", plan.periods[1].failed_capabilities)
        self.assertEqual(plan.periods[0].transfers_departed, ())

    def test_minimum_service_tops_up_shared_dependency(self):
        state, inventory = self.inventory()
        inventory.observe("electricity", 10, "kWh", "site", "meter")
        inventory.observe("water", 20, "L", "site", "tank")
        graph = DependencyGraph()
        graph.require_resource("pump", ResourceRequirement("electricity", 10, "kWh", location="site"))
        graph.require_capability("irrigate-a", CapabilityRequirement("pump"))
        graph.require_capability("irrigate-b", CapabilityRequirement("pump"))
        graph.require_resource("irrigate-a", ResourceRequirement("water", 10, "L", location="site"))
        graph.require_resource("irrigate-b", ResourceRequirement("water", 10, "L", location="site"))
        plan = TemporalAllocationPlanner(SubstitutionGraph()).plan(
            1,
            [
                CapabilityDemand("irrigate-a", (0,), priority=10, minimum_service=.5),
                CapabilityDemand("irrigate-b", (0,), priority=5, minimum_service=1.0),
            ],
            graph,
            inventory,
        )
        self.assertTrue(plan.viable)
        levels = dict(plan.periods[0].service_levels)
        self.assertEqual(levels["pump"], 1.0)
        pump_electricity = [
            item for item in plan.periods[0].allocations
            if item.capability == "pump" and item.supplied_resource == "electricity"
        ]
        self.assertAlmostEqual(sum(item.quantity for item in pump_electricity), 10.0)

    def test_quality_threshold_survives_transport(self):
        state, inventory = self.inventory()
        inventory.observe("water", 10, "L", "source", "stock", quality=.4)
        graph = DependencyGraph()
        graph.require_resource(
            "process", ResourceRequirement("water", 10, "L", minimum_quality=.8, location="dest")
        )
        plan = TemporalAllocationPlanner(SubstitutionGraph()).plan(
            2,
            [CapabilityDemand("process", (1,))],
            graph,
            inventory,
            transport_links=[TransportLink("source", "dest", "water", "L", 10, 1)],
        )
        self.assertFalse(plan.viable)
        self.assertEqual(plan.periods[0].transfers_departed, ())

    def test_substitute_can_be_prepositioned(self):
        state, inventory = self.inventory()
        inventory.observe("battery", 10, "kWh", "source", "battery")
        graph = DependencyGraph()
        graph.require_resource(
            "pump", ResourceRequirement("grid-electricity", 10, "kWh", location="dest")
        )
        substitutions = SubstitutionGraph()
        substitutions.add(Substitution("grid-electricity", "battery", 1.0, {}))
        plan = TemporalAllocationPlanner(substitutions).plan(
            2,
            [CapabilityDemand("pump", (1,))],
            graph,
            inventory,
            transport_links=[TransportLink("source", "dest", "battery", "kWh", 10, 1)],
        )
        self.assertTrue(plan.viable)
        self.assertEqual(plan.periods[0].transfers_departed[0].resource, "battery")

    def test_transport_loss_is_accounted_for(self):
        state, inventory = self.inventory()
        inventory.observe("water", 12.5, "L", "source", "stock")
        graph = DependencyGraph()
        graph.require_resource("process", ResourceRequirement("water", 10, "L", location="dest"))
        plan = TemporalAllocationPlanner(SubstitutionGraph()).plan(
            2,
            [CapabilityDemand("process", (1,))],
            graph,
            inventory,
            transport_links=[TransportLink("source", "dest", "water", "L", 12.5, 1, loss_fraction=.2)],
        )
        self.assertTrue(plan.viable)
        transfer = plan.periods[0].transfers_departed[0]
        self.assertAlmostEqual(transfer.shipped_quantity, 12.5)
        self.assertAlmostEqual(transfer.delivered_quantity, 10.0)

    def test_scheduled_replenishment_avoids_unnecessary_transport(self):
        state, inventory = self.inventory()
        inventory.observe("water", 10, "L", "source", "stock")
        graph = DependencyGraph()
        graph.require_resource("process", ResourceRequirement("water", 10, "L", location="dest"))
        plan = TemporalAllocationPlanner(SubstitutionGraph()).plan(
            2,
            [CapabilityDemand("process", (1,))],
            graph,
            inventory,
            replenishments=[Replenishment(1, "water", 10, "L", "dest")],
            transport_links=[TransportLink("source", "dest", "water", "L", 10, 1)],
        )
        self.assertTrue(plan.viable)
        self.assertEqual(plan.periods[0].transfers_departed, ())

    def test_independent_future_needs_are_summed_but_shared_dependency_once(self):
        state, inventory = self.inventory()
        inventory.observe("electricity", 10, "kWh", "source", "meter")
        inventory.observe("water", 10, "L", "source", "tank")
        graph = DependencyGraph()
        graph.require_resource("pump", ResourceRequirement("electricity", 10, "kWh", location="dest"))
        graph.require_capability("a", CapabilityRequirement("pump"))
        graph.require_capability("b", CapabilityRequirement("pump"))
        graph.require_resource("a", ResourceRequirement("water", 5, "L", location="dest"))
        graph.require_resource("b", ResourceRequirement("water", 5, "L", location="dest"))
        plan = TemporalAllocationPlanner(SubstitutionGraph()).plan(
            2,
            [CapabilityDemand("a", (1,)), CapabilityDemand("b", (1,))],
            graph,
            inventory,
            transport_links=[
                TransportLink("source", "dest", "electricity", "kWh", 10, 1),
                TransportLink("source", "dest", "water", "L", 10, 1),
            ],
        )
        self.assertTrue(plan.viable)
        shipped = {
            transfer.resource: transfer.shipped_quantity
            for transfer in plan.periods[0].transfers_departed
        }
        self.assertAlmostEqual(shipped["electricity"], 10.0)
        self.assertAlmostEqual(shipped["water"], 10.0)

    def test_zero_lead_transport_is_rejected(self):
        with self.assertRaises(ValueError):
            TransportLink("a", "b", "water", "L", 10, 0)


if __name__ == "__main__":
    unittest.main()
