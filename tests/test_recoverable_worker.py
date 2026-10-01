import os
import tempfile
import unittest

from rsqs_pulse.distributed_runtime import DistributedCoordinator
from rsqs_pulse.http_transport import HTTPTransportClient, PulseHTTPServer
from rsqs_pulse.identity import NodeIdentity
from rsqs_pulse.policy import LocalPolicy
from rsqs_pulse.recoverable_worker import RecoverableDistributedWorker

class RecoverableWorkerTests(unittest.TestCase):
    def test_duplicate_poll_does_not_repeat_completed_side_effect(self):
        with tempfile.TemporaryDirectory() as d:
            server = PulseHTTPServer("127.0.0.1", 0, "token")
            server.start()
            host, port = server.address
            client = HTTPTransportClient(f"http://{host}:{port}", "token")
            authority = NodeIdentity("authority")
            worker_identity = NodeIdentity("worker")
            coordinator = DistributedCoordinator("net", authority, os.path.join(d, "c.db"), client, {"worker": worker_identity.public})
            worker = RecoverableDistributedWorker(
                "worker", "net", authority.public, worker_identity,
                LocalPolicy(allowed_capabilities={"effect"}), os.path.join(d, "w.db"), client,
            )
            calls = []
            worker.register("effect", lambda args: calls.append(args) or {"count": len(calls)})
            task = coordinator.dispatch("worker", "effect", {"x": 1})
            worker.poll_once()
            self.assertEqual(len(calls), 1)
            worker.cursor = 0
            worker.state.set_meta("distributed_cursor", "0")
            worker.poll_once()
            self.assertEqual(len(calls), 1)
            coordinator.collect_once()
            self.assertEqual(coordinator.results(task)[0]["output"]["count"], 1)
            worker.close()
            coordinator.close()
            server.close()

    def test_failed_operation_is_not_automatically_retried(self):
        with tempfile.TemporaryDirectory() as d:
            server = PulseHTTPServer("127.0.0.1", 0, "token")
            server.start()
            host, port = server.address
            client = HTTPTransportClient(f"http://{host}:{port}", "token")
            authority = NodeIdentity("authority")
            worker_identity = NodeIdentity("worker")
            coordinator = DistributedCoordinator("net", authority, os.path.join(d, "c.db"), client, {"worker": worker_identity.public})
            worker = RecoverableDistributedWorker(
                "worker", "net", authority.public, worker_identity,
                LocalPolicy(allowed_capabilities={"effect"}), os.path.join(d, "w.db"), client,
            )
            calls = []
            def fail(args):
                calls.append(args)
                raise RuntimeError("actuator uncertain")
            worker.register("effect", fail)
            coordinator.dispatch("worker", "effect", {})
            worker.poll_once()
            worker.cursor = 0
            worker.poll_once()
            self.assertEqual(len(calls), 1)
            worker.close()
            coordinator.close()
            server.close()

if __name__ == "__main__":
    unittest.main()
