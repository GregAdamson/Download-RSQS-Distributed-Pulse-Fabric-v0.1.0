import os
import tempfile
import unittest

from rsqs_pulse.dependency_centrality import DependencyCentralityAnalyzer
from rsqs_pulse.dependency_graph import CapabilityRequirement, DependencyGraph, ResourceRequirement
from rsqs_pulse.learning_reconciliation import LearningReconciliation
from rsqs_pulse.monte_carlo_resilience import MonteCarloResilienceEngine, ScenarioOutcome
from rsqs_pulse.persistent import SQLiteState
from rsqs_pulse.resilience_oracle import ResilienceOracle
from rsqs_pulse.resilience_store import ResilienceStore
from rsqs_pulse.substitution import Substitution, SubstitutionGraph
from rsqs_pulse.temporal_allocation import TemporalAllocationPlan
from rsqs_pulse.trajectory_optimizer import TrajectoryOptimizer, TrajectoryState


class StrategyExtensionTests(unittest.TestCase):
    def test_dependency_centrality_includes_resource_and_recursive_dependents(self):
        graph = DependencyGraph()
        graph.require_resource("pump", ResourceRequirement("electricity", 10, "kWh"))
        graph.require_capability("irrigate", CapabilityRequirement("pump"))
        graph.require_capability("production", CapabilityRequirement("irrigate"))
        findings = {item.node: item for item in DependencyCentralityAnalyzer().analyze(graph)}
        self.assertEqual(findings["electricity"].node_kind, "resource")
        self.assertEqual(
            findings["electricity"].dependent_capabilities,
            ("irrigate", "production", "pump"),
        )
        self.assertEqual(findings["electricity"].dependency_count, 3)

    def test_substitution_reduces_resource_criticality_penalty(self):
        graph = DependencyGraph()
        graph.require_resource("generator", ResourceRequirement("diesel", 10, "L"))
        base = {x.node: x for x in DependencyCentralityAnalyzer().analyze(graph)}["diesel"]
        substitutions = SubstitutionGraph()
        substitutions.add(Substitution("diesel", "biodiesel", 1.0, {}))
        with_alt = {
            x.node: x
            for x in DependencyCentralityAnalyzer().analyze(graph, substitutions)
        }["diesel"]
        self.assertLess(with_alt.substitution_score, base.substitution_score)
        self.assertLess(with_alt.criticality_score, base.criticality_score)

    def test_trajectory_optimizer_generates_rejects_and_ranks_deterministically(self):
        optimizer = TrajectoryOptimizer()
        candidates = optimizer.generate([
            {
                "trajectory_id": "b",
                "states": [TrajectoryState(0, {"x": 1})],
                "actions": [{"kind": "safe"}],
            },
            {
                "trajectory_id": "a",
                "states": [TrajectoryState(0, {"x": 1})],
                "actions": [{"kind": "safe"}],
            },
            {
                "trajectory_id": "invalid",
                "states": [],
                "actions": [{"kind": "unsafe"}],
            },
        ])
        for candidate in candidates:
            optimizer.evaluate(
                candidate,
                lambda item: item.actions[0]["kind"] == "safe",
                lambda item: {"capability_retention": 1.0},
            )
        ranked = optimizer.rank(candidates)
        self.assertEqual([item.trajectory_id for item in ranked], ["a", "b"])
        self.assertEqual(optimizer.select(candidates).trajectory_id, "a")
        self.assertEqual(candidates[2].score, float("-inf"))
        self.assertEqual(candidates[2].failure_reason, "validator rejected candidate")

    def test_duplicate_trajectory_ids_are_rejected(self):
        optimizer = TrajectoryOptimizer()
        with self.assertRaises(ValueError):
            optimizer.generate([
                {"trajectory_id": "same"},
                {"trajectory_id": "same"},
            ])

    def test_monte_carlo_replays_identically_from_seed(self):
        simulator = lambda scenario: ScenarioOutcome(
            scenario.reduction < .75,
            None if scenario.reduction < .75 else scenario.duration,
            1.0 - scenario.reduction,
        )
        first = MonteCarloResilienceEngine(seed=42).run(["water", "power"], 25, simulator)
        second = MonteCarloResilienceEngine(seed=42).run(["water", "power"], 25, simulator)
        self.assertEqual(first, second)
        self.assertIn("mean_failure_period", first[2])

    def test_learning_reconciliation_persists_error_vector(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "learning.db")
            state = SQLiteState(path)
            learning = LearningReconciliation(state.conn)
            record = learning.reconcile(
                "prediction-1",
                {"stock": 10, "status": "ok"},
                {"stock": 7, "status": "failed"},
                "depletion was faster than predicted",
                "sensor:1",
            )
            self.assertEqual(record.error["stock"], -3)
            self.assertTrue(record.error["status"])
            state.conn.close()

            restored = SQLiteState(path)
            learning = LearningReconciliation(restored.conn)
            history = learning.history()
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0].prediction_id, "prediction-1")
            self.assertEqual(history[0].error["stock"], -3)
            restored.conn.close()

    def test_resilience_store_persists_all_planned_artifact_classes(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "resilience.db")
            state = SQLiteState(path)
            store = ResilienceStore(state.conn)
            store.record_scenario("s1", {"resource": "water", "reduction": .5})
            store.record_trajectory("t1", {"actions": ["substitute"]}, score=4.0, validated=True)
            store.record_outcome("o1", {"survived": True}, scenario_id="s1")
            store.record_lesson("p1", {"x": 1}, {"x": 2}, {"x": 1}, "update model", "sensor")
            state.conn.close()

            restored = SQLiteState(path)
            store = ResilienceStore(restored.conn)
            self.assertEqual(store.fetch_scenario("s1")["resource"], "water")
            self.assertTrue(store.fetch_trajectory("t1")["validated"])
            self.assertEqual(store.fetch_outcomes("s1")[0]["outcome_id"], "o1")
            self.assertEqual(store.fetch_lessons()[0]["prediction_id"], "p1")
            restored.conn.close()

    def test_oracle_combines_temporal_monte_carlo_and_dependency_evidence(self):
        graph = DependencyGraph()
        graph.require_resource("pump", ResourceRequirement("electricity", 10, "kWh"))
        graph.require_capability("irrigate", CapabilityRequirement("pump"))
        temporal = TemporalAllocationPlan(
            viable=False,
            periods=(),
            first_failure_period=2,
            failed_demands=((2, "irrigate"),),
        )
        outcomes = (
            ScenarioOutcome(True, None, 1.0),
            ScenarioOutcome(False, 2, 0.0),
        )
        report = ResilienceOracle().assess(graph, temporal, outcomes, top_n=2)
        self.assertFalse(report.viable)
        self.assertEqual(report.survival_rate, .5)
        self.assertEqual(report.first_failure_period, 2)
        self.assertEqual(report.evidence["scenario_count"], 2)
        self.assertTrue(any(item.node == "electricity" for item in report.critical_nodes))


if __name__ == "__main__":
    unittest.main()
