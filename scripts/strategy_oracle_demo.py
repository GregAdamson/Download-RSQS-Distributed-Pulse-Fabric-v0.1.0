#!/usr/bin/env python3
from rsqs_pulse.dependency_graph import DependencyGraph, ResourceRequirement
from rsqs_pulse.learning_reconciliation import LearningReconciliation
from rsqs_pulse.monte_carlo_resilience import MonteCarloResilienceEngine, ScenarioOutcome
from rsqs_pulse.persistent import SQLiteState
from rsqs_pulse.resilience_oracle import ResilienceOracle
from rsqs_pulse.resource_state import ResourceInventory
from rsqs_pulse.substitution import SubstitutionGraph
from rsqs_pulse.temporal_allocation import CapabilityDemand, TemporalAllocationPlanner
from rsqs_pulse.trajectory_optimizer import TrajectoryOptimizer

state = SQLiteState(":memory:")
inventory = ResourceInventory(state.conn)
inventory.observe("fuel", 10, "L", "site", "initial")

graph = DependencyGraph()
graph.require_resource("operate", ResourceRequirement("fuel", 6, "L", location="site"))

optimizer = TrajectoryOptimizer()
candidates = optimizer.generate([
    {"trajectory_id": "full", "actions": [{"minimum_service": 1.0}]},
    {"trajectory_id": "conserve", "actions": [{"minimum_service": .5}]},
])
plans = {}

def validate(candidate):
    service = candidate.actions[0]["minimum_service"]
    plan = TemporalAllocationPlanner(SubstitutionGraph()).plan(
        2,
        [CapabilityDemand("operate", (0, 1), minimum_service=service)],
        graph,
        inventory,
    )
    plans[candidate.trajectory_id] = plan
    return plan.viable

for candidate in candidates:
    optimizer.evaluate(
        candidate,
        validate,
        lambda item: {
            "capability_retention": 1.0,
            "reserve_margin": 1.0 if item.trajectory_id == "conserve" else 0.0,
            "resource_consumption": item.actions[0]["minimum_service"],
        },
    )

selected = optimizer.select(candidates)
assert selected is not None
assert selected.trajectory_id == "conserve"

engine = MonteCarloResilienceEngine(seed=17)
service = selected.actions[0]["minimum_service"]

def simulate(scenario):
    scenario_state = SQLiteState(":memory:")
    scenario_inventory = ResourceInventory(scenario_state.conn)
    scenario_inventory.observe(
        "fuel", 10 * (1.0 - scenario.reduction), "L", "site", "scenario"
    )
    plan = TemporalAllocationPlanner(SubstitutionGraph()).plan(
        2,
        [CapabilityDemand("operate", (0, 1), minimum_service=service)],
        graph,
        scenario_inventory,
    )
    outcome = ScenarioOutcome(plan.viable, plan.first_failure_period, 1.0 if plan.viable else 0.0)
    scenario_state.conn.close()
    return outcome

scenarios, outcomes, summary = engine.run(["fuel"], 20, simulate)
report = ResilienceOracle(monte_carlo=engine).assess(
    graph, plans["conserve"], outcomes
)
learning = LearningReconciliation(state.conn)
learning.reconcile(
    "strategy-survival",
    {"survival_rate": 1.0},
    {"survival_rate": report.survival_rate},
    "calibrate resilience estimate",
    "monte-carlo:seed-17",
)
assert len(scenarios) == 20
assert report.survival_rate == summary["survival_rate"]
assert learning.history()
print("STRATEGY_ORACLE_PROOF=PASS")
