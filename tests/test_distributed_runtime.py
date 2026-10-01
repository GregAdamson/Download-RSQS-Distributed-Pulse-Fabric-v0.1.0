import os
import tempfile
import unittest

from rsqs_pulse.distributed_runtime import DistributedCoordinator, DistributedWorker
from rsqs_pulse.http_transport import HTTPTransportClient, PulseHTTPServer
from rsqs_pulse.identity import NodeIdentity
from rsqs_pulse.policy import LocalPolicy


class DistributedRuntimeTests(unittest.TestCase):
    def test_signed_task_and_result_across_http(self):
        with tempfile.TemporaryDirectory() as directory:
            server = PulseHTTPServer("127.0.0.1", 0, "token")
            server.start()
            host, port = server.address
            client = HTTPTransportClient(f"http://{host}:{port}", "token")
            authority = NodeIdentity("authority")
            worker_identity = NodeIdentity("worker")
            coordinator = DistributedCoordinator(
                "net", authority, os.path.join(directory, "c.db"), client,
                {"worker": worker_identity.public},
            )
            worker = DistributedWorker(
                "worker", "net", authority.public, worker_identity,
                LocalPolicy(allowed_capabilities={"math.double"}),
                os.path.join(directory, "w.db"), client,
            )
            worker.register("math.double", lambda args: {"value": args["value"] * 2})
            task = coordinator.dispatch("worker", "math.double", {"value": 9})
            worker.poll_once()
            coordinator.collect_once()
            self.assertEqual(coordinator.results(task)[0]["output"]["value"], 18)
            self.assertTrue(worker.ledger.verify())
            self.assertTrue(coordinator.ledger.verify())
            worker.close()
            coordinator.close()
            server.close()

    def test_worker_cursor_survives_restart_and_reconciles(self):
        with tempfile.TemporaryDirectory() as directory:
            server = PulseHTTPServer("127.0.0.1", 0, "token")
            server.start()
            host, port = server.address
            client = HTTPTransportClient(f"http://{host}:{port}", "token")
            authority = NodeIdentity("authority")
            worker_identity = NodeIdentity("worker")
            worker_path = os.path.join(directory, "w.db")
            coordinator = DistributedCoordinator(
                "net", authority, os.path.join(directory, "c.db"), client,
                {"worker": worker_identity.public},
            )
            worker = DistributedWorker(
                "worker", "net", authority.public, worker_identity,
                LocalPolicy(allowed_capabilities={"math.double"}), worker_path, client,
            )
            worker.register("math.double", lambda args: {"value": args["value"] * 2})
            first = coordinator.dispatch("worker", "math.double", {"value": 2})
            worker.poll_once()
            coordinator.collect_once()
            self.assertEqual(coordinator.results(first)[0]["output"]["value"], 4)
            worker.close()

            second = coordinator.dispatch("worker", "math.double", {"value": 5})
            self.assertEqual(coordinator.results(second), [])
            restarted = DistributedWorker(
                "worker", "net", authority.public, worker_identity,
                LocalPolicy(allowed_capabilities={"math.double"}), worker_path, client,
            )
            restarted.register("math.double", lambda args: {"value": args["value"] * 2})
            restarted.poll_once()
            coordinator.collect_once()
            self.assertEqual(coordinator.results(second)[0]["output"]["value"], 10)
            restarted.close()
            coordinator.close()
            server.close()

    def test_local_deny_returns_signed_denial(self):
        with tempfile.TemporaryDirectory() as directory:
            server = PulseHTTPServer("127.0.0.1", 0, "token")
            server.start()
            host, port = server.address
            client = HTTPTransportClient(f"http://{host}:{port}", "token")
            authority = NodeIdentity("authority")
            worker_identity = NodeIdentity("worker")
            coordinator = DistributedCoordinator(
                "net", authority, os.path.join(directory, "c.db"), client,
                {"worker": worker_identity.public},
            )
            worker = DistributedWorker(
                "worker", "net", authority.public, worker_identity,
                LocalPolicy(allowed_capabilities=set()), os.path.join(directory, "w.db"), client,
            )
            calls = []
            worker.register("change", lambda args: calls.append(args) or {"changed": True})
            task = coordinator.dispatch("worker", "change", {})
            worker.poll_once()
            coordinator.collect_once()
            result = coordinator.results(task)[0]
            self.assertEqual(result["status"], "denied")
            self.assertEqual(calls, [])
            worker.close()
            coordinator.close()
            server.close()


if __name__ == "__main__":
    unittest.main()
