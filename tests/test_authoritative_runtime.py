import os
import tempfile
import unittest

from rsqs_pulse.cognitive_loop import Observation
from rsqs_pulse.operation_ledger import LedgerState, OperationLedger
from rsqs_pulse.persistent import SQLiteState
from rsqs_pulse.policy import LocalPolicy
from rsqs_pulse.runtime import FabricRuntime, RuntimeTransition
from rsqs_pulse.state_reasoning import State, Transition
from rsqs_pulse.temporal_state import StateClass

class AuthoritativeRuntimeTests(unittest.TestCase):
    def test_success_records_complete_operation_and_observed_state(self):
        with tempfile.TemporaryDirectory() as d:
            runtime = FabricRuntime("node", os.path.join(d, "state.db"), LocalPolicy(allowed_capabilities={"measure"}))
            runtime.register_capability("measure", lambda args: {"measured": 7})
            transition = Transition("measure", "measure", lambda state: State({"value": 999}))
            result = runtime.run_cycle(
                [Observation("sensor", {"value": 0})],
                lambda state: state.values.get("value") == 999,
                [RuntimeTransition(transition, {}, reduce=lambda state, output: State({"value": output["measured"]}))],
            )
            self.assertEqual(result.status, "incomplete")
            rows = runtime.state.conn.execute("SELECT operation_id,state FROM operation_ledger").fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][1], LedgerState.COMPLETE.value)
            self.assertEqual(runtime.temporal.latest("value", StateClass.OBSERVED).value, 7)
            self.assertEqual(runtime.health()["unresolved_operations"], 0)
            runtime.close()

    def test_exception_leaves_unknown_operation_for_reconciliation(self):
        with tempfile.TemporaryDirectory() as d:
            runtime = FabricRuntime("node", os.path.join(d, "state.db"), LocalPolicy(allowed_capabilities={"act"}))
            def uncertain(args):
                raise RuntimeError("connection lost after dispatch")
            runtime.register_capability("act", uncertain)
            transition = Transition("act", "act", lambda state: State({"done": True}))
            result = runtime.run_cycle(
                [Observation("sensor", {"done": False})],
                lambda state: state.values.get("done") is True,
                [RuntimeTransition(transition, {})],
            )
            self.assertEqual(result.status, "failed")
            unresolved = runtime.operations.unresolved()
            self.assertEqual(len(unresolved), 1)
            self.assertEqual(unresolved[0].state, LedgerState.UNKNOWN)
            self.assertEqual(runtime.health()["unresolved_operations"], 1)
            self.assertFalse(runtime.current_state().values["done"])
            runtime.close()

    def test_restart_expires_abandoned_running_lease_to_unknown(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "state.db")
            state = SQLiteState(path)
            ledger = OperationLedger(state.conn)
            ledger.create("abandoned", "pump", "node", {}, now=1)
            ledger.start("abandoned", lease_seconds=1, now=1)
            state.conn.close()
            runtime = FabricRuntime("node", path, LocalPolicy(allowed_capabilities=set()))
            self.assertEqual(runtime.operations.get("abandoned").state, LedgerState.UNKNOWN)
            self.assertEqual(runtime.health()["unresolved_operations"], 1)
            runtime.close()

if __name__ == "__main__":
    unittest.main()
