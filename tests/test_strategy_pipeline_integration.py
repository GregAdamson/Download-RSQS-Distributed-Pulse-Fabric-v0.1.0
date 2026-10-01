import unittest

from rsqs_pulse.dependency_graph import DependencyGraph, ResourceRequirement
from rsqs_pulse.learning_reconciliation import LearningReconciliation
from rsqs_pulse.monte_carlo_resilience import MonteCarloResilienceEngine, ScenarioOutcome
from rsqs_pulse.persistent import SQLiteState
from rsqs_pulse.resilience_oracle import ResilienceOracle
from rsqs_pulse.resilience_store import ResilienceStore
from rsqs_pulse.resource_state import ResourceInventory
from rsqs_pulse.substitution import SubstitutionGraph
from rsqs_pulse.temporal_allocation import CapabilityDemand, TemporalAllocationPlanner
from rsqs_pulse.trajectory_optimizer import TrajectoryOptimizer


class StrategyPipelineIntegrationTests(unittest.TestCase):
    def test_temporal_optimizer_monte_carlo_oracle_learning_pipeline(self):
        graph = DependencyGraph()
        graph.require_resource(
            "operate",
            ResourceRequirement("fuel", 6, "L", location="site"),
        )

        base_state = SQLiteState(":memory:")
        base_inventory = ResourceInventory(base_state.conn)
        base_inventory.observe("fuel", 10, "L", "site", "initial-stock")

        optimizer = TrajectoryOptimizer()
        candidates = optimizer.generate([
            {
                "trajectory_id": "full-service",
                "actions": [{"minimum_service": 1.0}],
            },
            {
                "trajectory_id": "conserve",
                "actions": [{"minimum_service": .5}],
            },
        ])

        plans = {}
        def validate(candidate):
            service = candidate.actions[0]["minimum_service"]
            plan = TemporalAllocationPlanner(SubstitutionGraph()).plan(
                2,
                [CapabilityDemand("operate", (0, 1), minimum_service=service)],
                graph,
                base_inventory,
            )
            plans[candidate.trajectory_id] = plan
            return plan.viable

        for candidate in candidates:
            optimizer.evaluate(
                candidate,
                validate,
                lambda item: {
                    "capability_retention": 1.0,
                    "reserve_margin": (
                        1.0 if item.trajectory_id == "conserve" else 0.0
                    ),
                    "resource_consumption": item.actions[0]["minimum_service"],
                },
            )

        selected = optimizer.select(candidates)
        self.assertIsNotNone(selected)
        self.assertEqual(selected.trajectory_id, "conserve")
        self.assertFalse(plans["full-service"].viable)
        self.assertTrue(plans["conserve"].viable)

        monte_carlo = MonteCarloResilienceEngine(seed=17)
        service = selected.actions[0]["minimum_service"]

        def simulate(scenario):
            scenario_state = SQLiteState(":memory:")
            inventory = ResourceInventory(scenario_state.conn)
            remaining = 10 * (1.0 - scenario.reduction)
            inventory.observe("fuel", remaining, "L", "site", "scenario")
            plan = TemporalAllocationPlanner(SubstitutionGraph()).plan(
                2,
                [CapabilityDemand("operate", (0, 1), minimum_service=service)],
                graph,
                inventory,
            )
            score = 1.0 if plan.viable else 0.0
            outcome = ScenarioOutcome(
                survived=plan.viable,
                failure_period=plan.first_failure_period,
                score=score,
            )
            scenario_state.conn.close()
            return outcome

        scenarios, outcomes, summary = monte_carlo.run(
            ["fuel"], 20, simulate
        )
        self.assertEqual(len(scenarios), 20)
        self.assertEqual(len(outcomes), 20)
        self.assertGreaterEqual(summary["survival_rate"], 0.0)
        self.assertLessEqual(summary["survival_rate"], 1.0)

        report = ResilienceOracle(monte_carlo=monte_carlo).assess(
            graph,
            plans["conserve"],
            outcomes,
            top_n=3,
        )
        self.assertTrue(report.viable)
        self.assertEqual(report.survival_rate, summary["survival_rate"])
        self.assertTrue(any(node.node == "fuel" for node in report.critical_nodes))

        store = ResilienceStore(base_state.conn)
        for index, scenario in enumerate(scenarios):
            scenario_id = f"scenario-{index:02d}"
            store.record_scenario(scenario_id, scenario)
            store.record_outcome(
                f"outcome-{index:02d}",
                outcomes[index],
                scenario_id=scenario_id,
            )
        store.record_trajectory(
            selected.trajectory_id,
            {
                "actions": selected.actions,
                "oracle_survival_rate": report.survival_rate,
            },
            score=selected.score,
            validated=selected.validated,
        )

        learning = LearningReconciliation(base_state.conn)
        record = learning.reconcile(
            "strategy-survival",
            {"survival_rate": 1.0},
            {"survival_rate": report.survival_rate},
            "calibrate strategy against shock distribution",
            "monte-carlo:seed-17",
        )
        self.assertAlmostEqual(
            record.error["survival_rate"],
            report.survival_rate - 1.0,
        )
        self.assertEqual(len(store.fetch_outcomes()), 20)
        self.assertEqual(
            store.fetch_trajectory("conserve")["payload"]["oracle_survival_rate"],
            report.survival_rate,
        )
        self.assertEqual(
            store.fetch_lessons()[0]["prediction_id"],
            "strategy-survival",
        )
        base_state.conn.close()


if __name__ == "__main__":
    unittest.main()
