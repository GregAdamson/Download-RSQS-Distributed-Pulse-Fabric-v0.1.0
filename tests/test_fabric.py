import os
import sys
import time
import unittest
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from rsqs_pulse import Capability, Coordinator, InMemoryBroker, LocalPolicy, Node
from rsqs_pulse.crypto import sign_pulse
from rsqs_pulse.model import Pulse


class FabricTests(unittest.TestCase):
    def setUp(self):
        self.secret = b"test-secret"
        self.broker = InMemoryBroker()
        self.coordinator = Coordinator("test-net", self.secret, self.broker)
        self.node = Node("n1", "test-net", self.secret, LocalPolicy(allowed_capabilities={"echo"}))
        self.node.register(Capability("echo"), lambda args: {"echo": args})
        self.broker.subscribe(self.node.receive)

    def test_signed_task_executes(self):
        self.coordinator.dispatch_task("echo", "run", {"x": 1})
        self.assertEqual(len(self.node.results), 1)
        self.assertEqual(self.node.results[0].output["echo"]["x"], 1)

    def test_local_deny_wins(self):
        node = Node("n2", "test-net", self.secret, LocalPolicy(allowed_capabilities=set()))
        node.register(Capability("echo"), lambda args: args)
        self.broker.subscribe(node.receive)
        self.coordinator.dispatch_task("echo", "run", {"x": 1})
        self.assertEqual(node.results, [])

    def test_bad_signature_rejected(self):
        pulse = Pulse.new("test-net", 1, "WAKE", {})
        self.node.receive(pulse)
        self.assertEqual(self.node.last_epoch, -1)

    def test_expired_rejected(self):
        now = int(time.time())
        pulse = Pulse("p", "test-net", 1, "WAKE", now - 10, now - 1, {}, "")
        pulse = sign_pulse(pulse, self.secret)
        self.node.receive(pulse)
        self.assertEqual(self.node.last_epoch, -1)

    def test_epoch_cannot_move_backwards(self):
        self.coordinator.emit("WAKE", {})
        self.coordinator.emit("WAKE", {})
        self.assertEqual(self.node.last_epoch, 2)
        old = Pulse.new("test-net", 1, "WAKE", {})
        old = sign_pulse(old, self.secret)
        self.node.receive(old)
        self.assertEqual(self.node.last_epoch, 2)


if __name__ == "__main__":
    unittest.main()
