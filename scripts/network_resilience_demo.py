#!/usr/bin/env python3
from rsqs_pulse.dependency_graph import CapabilityRequirement, DependencyGraph, ResourceRequirement
from rsqs_pulse.network_resilience import NetworkResiliencePlanner, RecoveryTarget, ResourceShock
from rsqs_pulse.persistent import SQLiteState
from rsqs_pulse.resource_state import ResourceInventory
from rsqs_pulse.substitution import Substitution, SubstitutionGraph

state = SQLiteState(":memory:")
inventory = ResourceInventory(state.conn)
inventory.observe("grid-electricity", 20, "kWh", "site", "meter")
inventory.observe("battery", 15, "kWh", "site", "battery")
inventory.observe("water", 20, "L", "site", "tank")

graph = DependencyGraph()
graph.require_resource("pump", ResourceRequirement("grid-electricity", 10, "kWh", location="site"))
graph.require_capability("irrigate-a", CapabilityRequirement("pump"))
graph.require_capability("irrigate-b", CapabilityRequirement("pump"))
graph.require_resource("irrigate-a", ResourceRequirement("water", 10, "L", location="site"))
graph.require_resource("irrigate-b", ResourceRequirement("water", 10, "L", location="site"))

substitutions = SubstitutionGraph()
substitutions.add(Substitution("grid-electricity", "battery", 1.0, {}))

plan = NetworkResiliencePlanner(substitutions).plan(
    [RecoveryTarget("irrigate-a", 10), RecoveryTarget("irrigate-b", 5)],
    graph,
    inventory,
    shocks=[ResourceShock("grid-electricity", 1.0, unit="kWh", location="site")],
)
assert plan.viable
assert set(plan.recovered_targets) == {"irrigate-a", "irrigate-b"}
battery_allocations = [x for x in plan.allocations if x.supplied_resource == "battery"]
assert len(battery_allocations) == 1
assert battery_allocations[0].supplied_quantity == 10
print("NETWORK_RESILIENCE_PROOF=PASS")
