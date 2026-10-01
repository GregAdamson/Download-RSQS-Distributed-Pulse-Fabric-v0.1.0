import os
import tempfile
import unittest

from rsqs_pulse.cognitive_loop import Observation
from rsqs_pulse.durable_transport import DurablePulseEventStore
from rsqs_pulse.learning_runtime import LearningRuntime
from rsqs_pulse.model import Pulse
from rsqs_pulse.policy import LocalPolicy
from rsqs_pulse.runtime import FabricRuntime, RuntimeTransition
from rsqs_pulse.state_reasoning import State, Transition
from rsqs_pulse.world_models import WorldModel


class HardeningTests(unittest.TestCase):
    def test_runtime_reduces_actual_output_not_prediction(self):
        with tempfile.TemporaryDirectory() as d:
            runtime = FabricRuntime("n", os.path.join(d, "s.db"), LocalPolicy(allowed_capabilities={"set"}))
            runtime.register_capability("set", lambda args: {"actual": 4})
            predicted = Transition("set", "set", lambda state: State({"x": 999}))
            spec = RuntimeTransition(predicted, {}, reduce=lambda state, output: State({"x": output["actual"]}))
            result = runtime.run_cycle([Observation("sensor", {"x": 0})], lambda s: s.values["x"] == 999, [spec])
            self.assertEqual(result.status, "incomplete")
            self.assertEqual(result.final_state["x"], 4)
            self.assertEqual(runtime.current_state().values["x"], 4)
            runtime.close()

    def test_handler_failure_is_persisted_not_masqueraded_as_success(self):
        with tempfile.TemporaryDirectory() as d:
            runtime = FabricRuntime("n", os.path.join(d, "s.db"), LocalPolicy(allowed_capabilities={"fail"}))
            def fail(args):
                raise RuntimeError("physical actuator unavailable")
            runtime.register_capability("fail", fail)
            transition = Transition("fail", "fail", lambda state: State({"done": True}))
            result = runtime.run_cycle([Observation("sensor", {"done": False})], lambda s: s.values["done"], [RuntimeTransition(transition, {})])
            self.assertEqual(result.status, "failed")
            self.assertFalse(runtime.current_state().values["done"])
            self.assertEqual(runtime.health()["failed_actions"], 1)
            runtime.close()

    def test_model_evidence_survives_restart(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "learn.db")
            runtime = LearningRuntime(path)
            runtime.register_model(WorldModel("m", lambda s, a, args: State({"x": s.values["x"] + 1})))
            runtime.experiment("e1", "cause", "inc", {}, State({"x": 0}), lambda a, args: State({"x": 1}), "rig", lambda before, after: after.values["x"] > before.values["x"])
            self.assertEqual(runtime.models.models["m"].observations, 1)
            runtime.close()
            restored = LearningRuntime(path)
            restored.register_model(WorldModel("m", lambda s, a, args: State({"x": s.values["x"] + 1})))
            self.assertEqual(restored.models.models["m"].observations, 1)
            restored.close()

    def test_explicit_outcome_can_reject_unrelated_state_change(self):
        runtime = LearningRuntime(":memory:")
        runtime.register_model(WorldModel("m", lambda s, a, args: State({"target": 0, "noise": 1})))
        result = runtime.experiment(
            "e", "treatment", "act", {}, State({"target": 0, "noise": 0}),
            lambda a, args: State({"target": 0, "noise": 1}), "rig",
            lambda before, after: after.values["target"] > before.values["target"],
        )
        self.assertEqual(result.causal.support, 0)
        self.assertGreater(result.causal.oppose, 0)
        runtime.close()

    def test_durable_event_store_survives_restart_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "events.db")
            pulse = Pulse.new("net", 1, "WAKE", {"x": 1})
            store = DurablePulseEventStore(path)
            first = store.append(pulse)
            duplicate = store.append(pulse)
            self.assertEqual(first, duplicate)
            store.close()
            restored = DurablePulseEventStore(path)
            cursor, events = restored.after(0)
            self.assertEqual(cursor, first)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].pulse_id, pulse.pulse_id)
            restored.close()


if __name__ == "__main__":
    unittest.main()
