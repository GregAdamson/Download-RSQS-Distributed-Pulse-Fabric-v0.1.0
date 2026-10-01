#!/usr/bin/env python3
import argparse
import os
import signal
import ssl
import time

from rsqs_pulse.distributed_runtime import DistributedWorker
from rsqs_pulse.http_transport import HTTPTransportClient
from rsqs_pulse.identity import PublicIdentity
from rsqs_pulse.persistent_identity import load_identity
from rsqs_pulse.policy import LocalPolicy


def main():
    p = argparse.ArgumentParser(description="RSQS enrolled worker proof process")
    p.add_argument("--node-id", required=True)
    p.add_argument("--network", required=True)
    p.add_argument("--authority-id", required=True)
    p.add_argument("--authority-public", required=True)
    p.add_argument("--private-key", required=True)
    p.add_argument("--state", required=True)
    p.add_argument("--transport", required=True)
    p.add_argument("--token-env", default="RSQS_TRANSPORT_TOKEN")
    p.add_argument("--ca-cert")
    p.add_argument("--capability", default="math.scale")
    p.add_argument("--multiplier", type=int, default=2)
    args = p.parse_args()

    token = os.environ.get(args.token_env)
    if not token:
        raise SystemExit(f"missing transport token environment variable: {args.token_env}")
    ssl_context = (
        None
        if args.ca_cert is None
        else ssl.create_default_context(cafile=args.ca_cert)
    )

    worker = DistributedWorker(
        args.node_id,
        args.network,
        PublicIdentity(args.authority_id, args.authority_public),
        load_identity(args.node_id, args.private_key),
        LocalPolicy(allowed_capabilities={args.capability}),
        args.state,
        HTTPTransportClient(
            args.transport,
            token,
            ssl_context=ssl_context,
        ),
    )
    worker.register(
        args.capability,
        lambda payload: {"value": payload["value"] * args.multiplier},
    )
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
