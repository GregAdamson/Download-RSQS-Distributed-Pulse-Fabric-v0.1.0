import os
import tempfile
import unittest

from rsqs_pulse.operation_ledger import LedgerState, OperationLedger
from rsqs_pulse.persistent import SQLiteState
from rsqs_pulse.temporal_state import StateClass, TemporalStateStore

class AuthoritativeCoreTests(unittest.TestCase):
    def test_observed_and_predicted_state_are_separate(self):
        state = SQLiteState(":memory:")
        store = TemporalStateStore(state.conn)
        store.assert_fact("tank.level", 7, StateClass.OBSERVED, "sensor", observed_at=100, valid_from=100)
        store.assert_fact("tank.level", 999, StateClass.PREDICTED, "planner", observed_at=101, valid_from=101)
        self.assertEqual(store.latest("tank.level", StateClass.OBSERVED).value, 7)
        self.assertEqual(store.latest("tank.level", StateClass.PREDICTED).value, 999)

    def test_temporal_validity_filters_state(self):
        state = SQLiteState(":memory:")
        store = TemporalStateStore(state.conn)
        store.assert_fact("price", 10, StateClass.OBSERVED, "feed", observed_at=100, valid_from=100, valid_until=199)
        store.assert_fact("price", 12, StateClass.OBSERVED, "feed", observed_at=200, valid_from=200)
        self.assertEqual([x.value for x in store.active_at("price", 150)], [10])
        self.assertEqual([x.value for x in store.active_at("price", 250)], [12])

    def test_expired_running_operation_becomes_unknown_not_retry(self):
        state = SQLiteState(":memory:")
        ledger = OperationLedger(state.conn)
        ledger.create("op-1", "pump", "device-a", {"seconds": 3}, now=100)
        ledger.start("op-1", lease_seconds=10, now=100)
        changed = ledger.expire_running(now=111)
        self.assertEqual(changed, ["op-1"])
        self.assertEqual(ledger.get("op-1").state, LedgerState.UNKNOWN)
        with self.assertRaises(ValueError):
            ledger.transition("op-1", LedgerState.RUNNING, now=112)

    def test_unknown_requires_explicit_reconciliation_before_retry(self):
        state = SQLiteState(":memory:")
        ledger = OperationLedger(state.conn)
        ledger.create("op-2", "pump", "device-a", {}, now=100)
        ledger.start("op-2", 10, now=100)
        ledger.expire_running(now=111)
        ledger.transition("op-2", LedgerState.RETRY_ELIGIBLE, evidence={"device": "confirmed_not_applied"}, now=112)
        ledger.start("op-2", 10, now=113)
        self.assertEqual(ledger.get("op-2").attempts, 2)

    def test_terminal_operation_cannot_reopen(self):
        state = SQLiteState(":memory:")
        ledger = OperationLedger(state.conn)
        ledger.create("op-3", "measure", "sensor", {}, now=1)
        ledger.start("op-3", 10, now=1)
        ledger.transition("op-3", LedgerState.COMPLETE, result={"value": 4}, now=2)
        with self.assertRaises(ValueError):
            ledger.transition("op-3", LedgerState.RUNNING, now=3)

if __name__ == "__main__":
    unittest.main()
