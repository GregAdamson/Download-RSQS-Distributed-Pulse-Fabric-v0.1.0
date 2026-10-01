import os
import stat
import tempfile
import unittest

from rsqs_pulse.idempotency import IdempotencyJournal
from rsqs_pulse.persistent import SQLiteState
from rsqs_pulse.persistent_identity import load_or_create_identity

class IdempotencyIdentityTests(unittest.TestCase):
    def test_completed_operation_cannot_begin_twice(self):
        state = SQLiteState(":memory:")
        journal = IdempotencyJournal(state.conn)
        self.assertTrue(journal.begin("task-1"))
        journal.complete("task-1", {"value": 4})
        self.assertFalse(journal.begin("task-1"))
        self.assertEqual(journal.get("task-1"), ("complete", {"value": 4}))

    def test_interrupted_operation_is_detected_after_restart(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "state.db")
            state = SQLiteState(path)
            journal = IdempotencyJournal(state.conn)
            self.assertTrue(journal.begin("task-crash"))
            state.conn.close()
            restored = SQLiteState(path)
            journal = IdempotencyJournal(restored.conn)
            self.assertEqual(journal.interrupted(), ["task-crash"])
            restored.conn.close()

    def test_identity_survives_restart(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "node.key")
            first = load_or_create_identity("node-a", path)
            public = first.public.public_key_b64
            second = load_or_create_identity("node-a", path)
            self.assertEqual(second.public.public_key_b64, public)
            mode = stat.S_IMODE(os.stat(path).st_mode)
            self.assertEqual(mode & 0o077, 0)

if __name__ == "__main__":
    unittest.main()
