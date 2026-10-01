import os
import tempfile
import unittest

from rsqs_pulse.cognitive_loop import Observation
from rsqs_pulse.policy import LocalPolicy
from rsqs_pulse.runtime import FabricRuntime, RuntimeTransition
from rsqs_pulse.state_reasoning import Constraint, State, Transition


class RuntimeIntegrationTests(unittest.TestCase):
    def test_complete_cycle_persists_and_recovers(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "state.db")
            runtime = FabricRuntime("node-a", path, LocalPolicy(allowed_capabilities={"counter.increment"}))
            calls = []
            runtime.register_capability("counter.increment", lambda args: calls.append(args) or {"ok": True})
            transition = Transition(
                "increment",
                "counter.increment",
                lambda state: State({**state.values, "counter": state.values.get("counter", 0) + 1}),
                cost=1,
            )
            result = runtime.run_cycle(
                [Observation("sensor", {"counter": 0})],
                lambda state: state.values.get("counter") == 2,
                [RuntimeTransition(transition, {"delta": 1})],
                [Constraint("safe", lambda state: state.values.get("counter", 0) <= 2)],
                max_depth=3,
            )
            self.assertEqual(result.status, "achieved")
            self.assertEqual(result.executed, ("increment", "increment"))
            self.assertEqual(len(calls), 2)
            self.assertEqual(runtime.current_state().values["counter"], 2)
            self.assertTrue(runtime.health()["provenance_valid"])
            runtime.close()

            restored = FabricRuntime("node-a", path, LocalPolicy(allowed_capabilities={"counter.increment"}))
            self.assertEqual(restored.current_state().values["counter"], 2)
            self.assertEqual(restored.health()["cycles"], 1)
            self.assertEqual(restored.health()["actions"], 2)
            self.assertTrue(restored.health()["provenance_valid"])
            restored.close()

    def test_local_deny_prevents_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "state.db")
            runtime = FabricRuntime("node-a", path, LocalPolicy(allowed_capabilities=set()))
            calls = []
            runtime.register_capability("dangerous.change", lambda args: calls.append(args) or {"ok": True})
            transition = Transition(
                "change",
                "dangerous.change",
                lambda state: State({**state.values, "changed": True}),
            )
            result = runtime.run_cycle(
                [Observation("sensor", {"changed": False})],
                lambda state: state.values.get("changed") is True,
                [RuntimeTransition(transition, {})],
            )
            self.assertEqual(result.status, "denied")
            self.assertEqual(calls, [])
            self.assertFalse(runtime.current_state().values["changed"])
            runtime.close()

    def test_unavailable_capability_denies_trajectory(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = FabricRuntime("node-a", os.path.join(directory, "state.db"), LocalPolicy(allowed_capabilities={"missing"}))
            transition = Transition("change", "missing", lambda state: State({"done": True}))
            result = runtime.run_cycle(
                [Observation("sensor", {"done": False})],
                lambda state: state.values.get("done") is True,
                [RuntimeTransition(transition, {})],
            )
            self.assertEqual(result.status, "denied")
            runtime.close()


if __name__ == "__main__":
    unittest.main()
