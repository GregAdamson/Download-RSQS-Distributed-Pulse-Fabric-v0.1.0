#!/usr/bin/env python3
from rsqs_pulse.dependency_graph import CapabilityRequirement, DependencyGraph, ResourceRequirement
from rsqs_pulse.persistent import SQLiteState
from rsqs_pulse.resource_state import ResourceInventory
from rsqs_pulse.substitution import Substitution, SubstitutionGraph
from rsqs_pulse.temporal_allocation import CapabilityDemand, Replenishment, TemporalAllocationPlanner, TransportLink

state = SQLiteState(":memory:")
inventory = ResourceInventory(state.conn)
inventory.observe("battery", 20, "kWh", "warehouse", "stock")
inventory.observe("water", 20, "L", "farm", "tank")

graph = DependencyGraph()
graph.require_resource("pump", ResourceRequirement("grid-electricity", 10, "kWh", location="farm"))
graph.require_capability("irrigate", CapabilityRequirement("pump"))
graph.require_resource("irrigate", ResourceRequirement("water", 10, "L", location="farm"))

substitutions = SubstitutionGraph()
substitutions.add(Substitution("grid-electricity", "battery", 1.0, {}))

plan = TemporalAllocationPlanner(substitutions).plan(
    3,
    [CapabilityDemand("irrigate", (1, 2), minimum_service=1.0)],
    graph,
    inventory,
    replenishments=[Replenishment(2, "water", 10, "L", "farm")],
    transport_links=[TransportLink("warehouse", "farm", "battery", "kWh", 10, 1)],
)
assert plan.viable
assert plan.first_failure_period is None
assert plan.periods[0].transfers_departed[0].resource == "battery"
assert plan.periods[1].transfers_departed[0].resource == "battery"
assert dict(plan.periods[1].service_levels)["irrigate"] == 1.0
assert dict(plan.periods[2].service_levels)["irrigate"] == 1.0
print("TEMPORAL_ALLOCATION_PROOF=PASS")
