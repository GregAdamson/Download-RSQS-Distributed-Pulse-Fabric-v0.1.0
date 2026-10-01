import os
import sqlite3
import tempfile
import unittest
from multiprocessing import Process

from rsqs_pulse.distributed_runtime import DistributedCoordinator
from rsqs_pulse.http_transport import HTTPTransportClient, PulseHTTPServer
from rsqs_pulse.identity import NodeIdentity, PublicIdentity
from rsqs_pulse.persistent_identity import load_or_create_identity
from rsqs_pulse.policy import LocalPolicy
from rsqs_pulse.reconciled_worker import ReconciledDistributedWorker
from rsqs_pulse.reconciliation import OperationState, OperationStatus


class FileBackedDevice:
    def __init__(self, path, crash_after_apply=False):
        self.path = path
        self.crash_after_apply = crash_after_apply
        with sqlite3.connect(self.path) as conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS device_operations(
              operation_id TEXT PRIMARY KEY,
              value INTEGER NOT NULL,
              apply_count INTEGER NOT NULL
            )
            """)
            conn.commit()

    def execute(self, operation_id, args):
        with sqlite3.connect(self.path) as conn:
            row = conn.execute(
                "SELECT value,apply_count FROM device_operations WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO device_operations(operation_id,value,apply_count) VALUES(?,?,1)",
                    (operation_id, int(args["value"])),
                )
                conn.commit()
                value = int(args["value"])
            else:
                value = int(row[0])
        if self.crash_after_apply:
            os._exit(77)
        return {"value": value}

    def status(self, operation_id):
        with sqlite3.connect(self.path) as conn:
            row = conn.execute(
                "SELECT value,apply_count FROM device_operations WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
        if row is None:
            return OperationStatus(
                operation_id, OperationState.NOT_APPLIED, {},
                {"device_db": self.path, "applied": False},
            )
        return OperationStatus(
            operation_id, OperationState.COMPLETE,
            {"value": int(row[0])},
            {"device_db": self.path, "applied": True, "apply_count": int(row[1])},
        )

    def apply_count(self, operation_id):
        with sqlite3.connect(self.path) as conn:
            row = conn.execute(
                "SELECT apply_count FROM device_operations WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
        return 0 if row is None else int(row[0])


def run_worker_once(base_url, token, authority_public, key_path, worker_db, device_db, crash_after_apply):
    identity = load_or_create_identity("worker", key_path)
    worker = ReconciledDistributedWorker(
        "worker", "net", authority_public, identity,
        LocalPolicy(allowed_capabilities={"device.set"}),
        worker_db,
        HTTPTransportClient(base_url, token),
    )
    worker.register_reconciliable(
        "device.set",
        FileBackedDevice(device_db, crash_after_apply=crash_after_apply),
    )
    worker.poll_once()
    worker.close()


class FaultInjectionReconciliationTests(unittest.TestCase):
    def test_process_death_after_external_effect_does_not_duplicate_effect(self):
        with tempfile.TemporaryDirectory() as d:
            server = PulseHTTPServer("127.0.0.1", 0, "token")
            server.start()
            host, port = server.address
            base_url = f"http://{host}:{port}"
            client = HTTPTransportClient(base_url, "token")

            authority = NodeIdentity("authority")
            key_path = os.path.join(d, "worker.key")
            worker_identity = load_or_create_identity("worker", key_path)
            worker_db = os.path.join(d, "worker.db")
            device_db = os.path.join(d, "device.db")
            device = FileBackedDevice(device_db)

            coordinator = DistributedCoordinator(
                "net", authority, os.path.join(d, "coordinator.db"), client,
                {"worker": worker_identity.public},
            )
            task_id = coordinator.dispatch("worker", "device.set", {"value": 42})

            first = Process(
                target=run_worker_once,
                args=(base_url, "token", authority.public, key_path, worker_db, device_db, True),
            )
            first.start()
            first.join(10)
            self.assertEqual(first.exitcode, 77)
            self.assertEqual(device.apply_count(task_id), 1)

            second = Process(
                target=run_worker_once,
                args=(base_url, "token", authority.public, key_path, worker_db, device_db, False),
            )
            second.start()
            second.join(10)
            self.assertEqual(second.exitcode, 0)

            coordinator.collect_once()
            results = coordinator.results(task_id)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["status"], "ok")
            self.assertEqual(results[0]["output"]["value"], 42)
            self.assertEqual(device.apply_count(task_id), 1)

            coordinator.close()
            server.close()


if __name__ == "__main__":
    unittest.main()
