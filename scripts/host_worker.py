#!/usr/bin/env python3
import argparse
import base64
import json
import os
import signal
import time
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from rsqs_pulse.distributed_runtime import DistributedWorker
from rsqs_pulse.http_transport import HTTPTransportClient
from rsqs_pulse.identity import NodeIdentity, PublicIdentity
from rsqs_pulse.policy import LocalPolicy


def load_private(node_id: str, path: str) -> NodeIdentity:
    raw = base64.b64decode(open(path, "rt", encoding="ascii").read().strip())
    return NodeIdentity(node_id, Ed25519PrivateKey.from_private_bytes(raw))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--node-id", required=True)
    p.add_argument("--network", required=True)
    p.add_argument("--authority-id", required=True)
    p.add_argument("--authority-public", required=True)
    p.add_argument("--private-key", required=True)
    p.add_argument("--state", required=True)
    p.add_argument("--transport", required=True)
    p.add_argument("--token", required=True)
    p.add_argument("--capability", default="math.scale")
    p.add_argument("--multiplier", type=int, default=2)
    args = p.parse_args()

    worker = DistributedWorker(
        args.node_id,
        args.network,
        PublicIdentity(args.authority_id, args.authority_public),
        load_private(args.node_id, args.private_key),
        LocalPolicy(allowed_capabilities={args.capability}),
        args.state,
        HTTPTransportClient(args.transport, args.token),
    )
    worker.register(args.capability, lambda payload: {"value": payload["value"] * args.multiplier})
    running = True
    def stop(*_):
        nonlocal running
        running = False
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        while running:
            worker.poll_once()
            time.sleep(0.25)
    finally:
        worker.close()


if __name__ == "__main__":
    main()
