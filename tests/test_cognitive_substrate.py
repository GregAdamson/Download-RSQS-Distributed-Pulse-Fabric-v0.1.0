import os
import tempfile
import unittest

from rsqs_pulse.causal import CausalMemory
from rsqs_pulse.experiments import DeterministicExperimentLoop, Experiment
from rsqs_pulse.learning_runtime import LearningRuntime
from rsqs_pulse.persistent import SQLiteState
from rsqs_pulse.sovereign_cell import SovereignCell, SovereignCellRegistry
from rsqs_pulse.state_reasoning import State
from rsqs_pulse.substitution import Substitution, SubstitutionGraph
from rsqs_pulse.world_models import CompetingWorldModels, WorldModel


class CognitiveSubstrateTests(unittest.TestCase):
    def test_sovereign_capability_discovery_respects_scope(self):
        registry = SovereignCellRegistry()
        registry.register(SovereignCell("farm-a", "farm", frozenset({"region:a"}), frozenset({"measure.water"})))
        registry.register(SovereignCell("farm-b", "farm", frozenset({"region:b"}), frozenset({"measure.water"})))
        self.assertEqual([x.cell_id for x in registry.discover("measure.water", "region:a")], ["farm-a"])

    def test_causal_memory_preserves_support_and_opposition(self):
        state = SQLiteState(":memory:")
        memory = CausalMemory(state.conn)
        memory.observe("irrigation", "water", {"yield": 1}, {"yield": 2}, "trial-1", supports=True, confidence=.9)
        memory.observe("irrigation", "water", {"yield": 1}, {"yield": 1}, "trial-2", supports=False, confidence=.4)
        assessment = memory.assess("irrigation", "water")
        self.assertEqual(assessment.observations, 2)
        self.assertAlmostEqual(assessment.support, .9)
        self.assertAlmostEqual(assessment.oppose, .4)

    def test_competing_models_select_lower_prediction_error(self):
        models = CompetingWorldModels()
        models.register(WorldModel("plus-one", lambda state, action, args: State({"x": state.values["x"] + 1})))
        models.register(WorldModel("plus-ten", lambda state, action, args: State({"x": state.values["x"] + 10})))
        ranking = models.evaluate(State({"x": 0}), "increment", {}, State({"x": 1}))
        self.assertEqual(ranking[0].model_id, "plus-one")
        self.assertEqual(models.best().model_id, "plus-one")

    def test_model_can_be_falsified_by_repeated_observation(self):
        models = CompetingWorldModels()
        models.register(WorldModel("wrong", lambda state, action, args: State({"x": 100})))
        models.register(WorldModel("right", lambda state, action, args: State({"x": state.values["x"] + 2})))
        loop = DeterministicExperimentLoop(models)
        state = State({"x": 0})
        for i in range(3):
            result = loop.run(Experiment(str(i), "increment", {}), state, lambda action, args: State({"x": state.values["x"] + 2}))
            state = result.after
        self.assertEqual(models.best().model_id, "right")
        self.assertGreater(models.models["wrong"].mean_error, models.models["right"].mean_error)

    def test_learning_runtime_persists_causal_evidence_and_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "learning.db")
            runtime = LearningRuntime(path)
            runtime.register_model(WorldModel("correct", lambda state, action, args: State({"x": state.values["x"] + args["delta"]})))
            runtime.register_model(WorldModel("wrong", lambda state, action, args: State({"x": state.values["x"] - args["delta"]})))
            result = runtime.experiment(
                "exp-1", "increment-command", "increment", {"delta": 3}, State({"x": 1}),
                lambda action, args: State({"x": 1 + args["delta"]}), "test-rig",
            )
            self.assertEqual(result.best_model, "correct")
            self.assertGreater(result.causal.support, 0)
            self.assertTrue(runtime.ledger.verify())
            runtime.close()

            restored = LearningRuntime(path)
            assessment = restored.causal.assess("increment-command", "increment")
            self.assertEqual(assessment.observations, 1)
            self.assertTrue(restored.ledger.verify())
            restored.close()

    def test_substitution_graph(self):
        graph = SubstitutionGraph()
        graph.add(Substitution("diesel", "biodiesel", 1.05, {"engine": "compatible"}))
        graph.add(Substitution("diesel", "electricity", 4.0, {"engine": "electric"}))
        result = graph.alternatives("diesel", {"engine": "compatible"})
        self.assertEqual([x.substitute for x in result], ["biodiesel"])


if __name__ == "__main__":
    unittest.main()
