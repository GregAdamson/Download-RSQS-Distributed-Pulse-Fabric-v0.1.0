import unittest

from rsqs_pulse.persistent import SQLiteState
from rsqs_pulse.scientific_engine import ScientificEngine, TrialKind

class ScientificEngineTests(unittest.TestCase):
    def test_intervention_requires_explicit_intervention(self):
        state = SQLiteState(":memory:")
        engine = ScientificEngine(state.conn)
        h = engine.register_hypothesis("watering increases growth", "watering", "growth", "h1")
        with self.assertRaises(ValueError):
            engine.record_trial(
                h.hypothesis_id, TrialKind.INTERVENTION,
                {"growth": 1}, {"growth": 2},
                supports=True, confidence=1.0, source="trial",
            )

    def test_observation_alone_does_not_count_as_replication(self):
        state = SQLiteState(":memory:")
        engine = ScientificEngine(state.conn)
        h = engine.register_hypothesis("watering increases growth", "watering", "growth", "h2")
        engine.record_trial(
            h.hypothesis_id, TrialKind.OBSERVATIONAL,
            {"growth": 1}, {"growth": 2},
            supports=True, confidence=.9, source="field",
        )
        summary = engine.summarize(h.hypothesis_id, minimum_interventions=2)
        self.assertEqual(summary.observations, 1)
        self.assertEqual(summary.interventions, 0)
        self.assertFalse(summary.replicated)

    def test_replication_requires_multiple_interventions(self):
        state = SQLiteState(":memory:")
        engine = ScientificEngine(state.conn)
        h = engine.register_hypothesis("watering increases growth", "watering", "growth", "h3")
        engine.record_trial(
            h.hypothesis_id, TrialKind.INTERVENTION,
            {"growth": 1}, {"growth": 2},
            intervention={"water_ml": 10}, controls={"light": "same"},
            supports=True, confidence=.9, source="trial-a",
        )
        self.assertFalse(engine.summarize(h.hypothesis_id, minimum_interventions=2).replicated)
        engine.record_trial(
            h.hypothesis_id, TrialKind.INTERVENTION,
            {"growth": 2}, {"growth": 3},
            intervention={"water_ml": 10}, controls={"light": "same"},
            supports=True, confidence=.8, source="trial-b",
        )
        summary = engine.summarize(h.hypothesis_id, minimum_interventions=2)
        self.assertTrue(summary.replicated)
        self.assertEqual(summary.interventions, 2)
        self.assertGreater(summary.support_weight, summary.oppose_weight)

    def test_counterevidence_is_preserved(self):
        state = SQLiteState(":memory:")
        engine = ScientificEngine(state.conn)
        h = engine.register_hypothesis("treatment helps", "treatment", "outcome", "h4")
        engine.record_trial(
            h.hypothesis_id, TrialKind.INTERVENTION,
            {"outcome": 0}, {"outcome": 1},
            intervention={"dose": 1}, supports=True, confidence=.7, source="a",
        )
        engine.record_trial(
            h.hypothesis_id, TrialKind.INTERVENTION,
            {"outcome": 0}, {"outcome": 0},
            intervention={"dose": 1}, confounders=["temperature"],
            supports=False, confidence=.9, source="b",
        )
        summary = engine.summarize(h.hypothesis_id, minimum_interventions=2)
        self.assertFalse(summary.replicated)
        self.assertGreater(summary.oppose_weight, summary.support_weight)
        history = engine.trial_history(h.hypothesis_id)
        self.assertEqual(history[1].confounders, ("temperature",))

if __name__ == "__main__":
    unittest.main()
