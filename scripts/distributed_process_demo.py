#!/usr/bin/env python3
import multiprocessing as mp
import os
import tempfile
import time

from rsqs_pulse.distributed_runtime import DistributedCoordinator, DistributedWorker
from rsqs_pulse.http_transport import HTTPTransportClient, PulseHTTPServer
from rsqs_pulse.identity import NodeIdentity
from rsqs_pulse.policy import LocalPolicy


def worker_process(node_id, network, authority, worker_identity, state_path, base_url, token, capability, multiplier):
    worker = DistributedWorker(
        node_id,
        network,
        authority,
        worker_identity,
        LocalPolicy(allowed_capabilities={capability}),
        state_path,
        HTTPTransportClient(base_url, token),
    )
    worker.register(capability, lambda args: {"value": args["value"] * multiplier})
    deadline = time.time() + 4
    while time.time() < deadline:
        worker.poll_once()
        time.sleep(0.05)
    worker.close()


def main():
    with tempfile.TemporaryDirectory() as directory:
        server = PulseHTTPServer("127.0.0.1", 0, "demo-token")
        server.start()
        host, port = server.address
        base_url = f"http://{host}:{port}"

        authority = NodeIdentity("coordinator")
        worker_a_identity = NodeIdentity("worker-a")
        worker_b_identity = NodeIdentity("worker-b")
        coordinator_path = os.path.join(directory, "coordinator.db")
        worker_a_path = os.path.join(directory, "worker-a.db")
        worker_b_path = os.path.join(directory, "worker-b.db")

        coordinator = DistributedCoordinator(
            "rsqs-demo",
            authority,
            coordinator_path,
            HTTPTransportClient(base_url, "demo-token"),
            {"worker-a": worker_a_identity.public, "worker-b": worker_b_identity.public},
        )

        proc_a = mp.Process(target=worker_process, args=(
            "worker-a", "rsqs-demo", authority.public, worker_a_identity,
            worker_a_path, base_url, "demo-token", "math.scale", 2,
        ))
        proc_b = mp.Process(target=worker_process, args=(
            "worker-b", "rsqs-demo", authority.public, worker_b_identity,
            worker_b_path, base_url, "demo-token", "math.scale", 3,
        ))
        proc_a.start()
        proc_b.start()

        task_a = coordinator.dispatch("worker-a", "math.scale", {"value": 7})
        task_b = coordinator.dispatch("worker-b", "math.scale", {"value": 7})

        deadline = time.time() + 5
        while time.time() < deadline and (not coordinator.results(task_a) or not coordinator.results(task_b)):
            coordinator.collect_once()
            time.sleep(0.05)

        assert coordinator.results(task_a)[0]["output"]["value"] == 14
        assert coordinator.results(task_b)[0]["output"]["value"] == 21

        proc_a.terminate()
        proc_a.join(timeout=2)
        offline_task = coordinator.dispatch("worker-a", "math.scale", {"value": 11})
        time.sleep(0.2)
        assert coordinator.results(offline_task) == []

        proc_a = mp.Process(target=worker_process, args=(
            "worker-a", "rsqs-demo", authority.public, worker_a_identity,
            worker_a_path, base_url, "demo-token", "math.scale", 2,
        ))
        proc_a.start()
        deadline = time.time() + 5
        while time.time() < deadline and not coordinator.results(offline_task):
            coordinator.collect_once()
            time.sleep(0.05)
        assert coordinator.results(offline_task)[0]["output"]["value"] == 22

        proc_a.join(timeout=5)
        proc_b.join(timeout=5)
        coordinator.close()

        restored = DistributedCoordinator(
            "rsqs-demo",
            authority,
            coordinator_path,
            HTTPTransportClient(base_url, "demo-token"),
            {"worker-a": worker_a_identity.public, "worker-b": worker_b_identity.public},
        )
        assert restored.results(task_a)[0]["output"]["value"] == 14
        assert restored.results(task_b)[0]["output"]["value"] == 21
        assert restored.results(offline_task)[0]["output"]["value"] == 22
        assert restored.ledger.verify()
        restored.close()
        server.close()
        print("DISTRIBUTED_PROCESS_PROOF=PASS")


if __name__ == "__main__":
    main()
