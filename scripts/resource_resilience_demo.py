#!/usr/bin/env python3
from rsqs_pulse.dependency_graph import CapabilityRequirement, DependencyGraph, ResourceRequirement
from rsqs_pulse.persistent import SQLiteState
from rsqs_pulse.resilience import ResiliencePlanner, ScarcityAnalyzer
from rsqs_pulse.resource_state import ResourceInventory
from rsqs_pulse.substitution import Substitution, SubstitutionGraph

state = SQLiteState(":memory:")
inventory = ResourceInventory(state.conn)
inventory.observe("diesel", 20, "L", "site", "meter")
inventory.observe("biodiesel", 44, "L", "site", "meter")
inventory.observe("copper", 10, "kg", "site", "inventory")

graph = DependencyGraph()
graph.require_resource("generator", ResourceRequirement("diesel", 60, "L", location="site"))
graph.require_resource("motor", ResourceRequirement("copper", 20, "kg", location="site"))
graph.require_capability("production", CapabilityRequirement("generator"))
graph.require_capability("production", CapabilityRequirement("motor"))

substitutions = SubstitutionGraph()
substitutions.add(Substitution("diesel", "biodiesel", 1.1, {}))
generator_plan = ResiliencePlanner(substitutions).plan("generator", graph, inventory)
assert generator_plan.viable
assert not graph.evaluate("production", inventory).operational
findings = {x.resource: x for x in ScarcityAnalyzer().analyze(graph, inventory)}
assert findings["copper"].shortage == 10
assert findings["diesel"].shortage == 40
print("RESOURCE_RESILIENCE_PROOF=PASS")
