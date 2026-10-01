import os
import tempfile
import unittest

from rsqs_pulse.reconciliation import OperationState, OperationStatus, Reconciler

class FakeCapability:
    def __init__(self, initial=OperationState.NOT_APPLIED):
        self.states = {}
        self.initial = initial
        self.calls = 0

    def execute(self, operation_id, args):
        self.calls += 1
        self.states[operation_id] = OperationStatus(operation_id, OperationState.COMPLETE, {"value": args.get("value")}, {"receipt": "device-ack"})
        return {"value": args.get("value")}

    def status(self, operation_id):
        return self.states.get(operation_id, OperationStatus(operation_id, self.initial, {}, {"source": "device"}))

class ReconciliationTests(unittest.TestCase):
    def test_complete_commits_without_retry(self):
        cap = FakeCapability()
        cap.states["op"] = OperationStatus("op", OperationState.COMPLETE, {"value": 7}, {"receipt": "r"})
        decision = Reconciler().inspect(cap, "op")
        self.assertEqual(decision.action, "commit")
        self.assertEqual(cap.calls, 0)

    def test_not_applied_is_only_retry_eligible_state(self):
        cap = FakeCapability(OperationState.NOT_APPLIED)
        self.assertEqual(Reconciler().inspect(cap, "op").action, "retry_eligible")
        cap.initial = OperationState.RUNNING
        self.assertEqual(Reconciler().inspect(cap, "op").action, "wait")
        cap.initial = OperationState.UNKNOWN
        self.assertEqual(Reconciler().inspect(cap, "op").action, "escalate")
        cap.initial = OperationState.FAILED
        self.assertEqual(Reconciler().inspect(cap, "op").action, "fail")

    def test_unknown_never_becomes_retry(self):
        cap = FakeCapability(OperationState.UNKNOWN)
        decision = Reconciler().inspect(cap, "dangerous-op")
        self.assertNotEqual(decision.action, "retry_eligible")
        self.assertEqual(decision.action, "escalate")
        self.assertEqual(cap.calls, 0)

if __name__ == "__main__":
    unittest.main()
