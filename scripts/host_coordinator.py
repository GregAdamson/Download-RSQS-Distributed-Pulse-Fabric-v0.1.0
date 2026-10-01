#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import ssl
import time

from rsqs_pulse.distributed_runtime import DistributedCoordinator
from rsqs_pulse.http_transport import HTTPTransportClient
from rsqs_pulse.persistent import SQLiteState
from rsqs_pulse.persistent_identity import load_identity
from rsqs_pulse.trust_plane import TrustRegistry
from rsqs_pulse.trusted_capabilities import TrustedCapabilityRegistry


def main() -> None:
    parser = argparse.ArgumentParser(
        description="RSQS trust-bound coordinator dispatch utility"
    )
    parser.add_argument("--node-id", default="coordinator")
    parser.add_argument("--private-key", required=True)
    parser.add_argument("--network", required=True)
    parser.add_argument("--state", required=True)
    parser.add_argument("--trust-db", required=True)
    parser.add_argument("--transport", required=True)
    parser.add_argument("--token-env", default="RSQS_TRANSPORT_TOKEN")
    parser.add_argument("--ca-cert")
    parser.add_argument("--target", required=True)
    parser.add_argument("--capability", required=True)
    parser.add_argument("--args-json", default="{}")
    parser.add_argument("--ttl", type=int, default=120)
    parser.add_argument("--wait-seconds", type=float, default=10.0)
    parser.add_argument("--dispatch-only", action="store_true")
    args = parser.parse_args()

    token = os.environ.get(args.token_env)
    if not token:
        raise SystemExit(
            f"missing transport token environment variable: {args.token_env}"
        )
    ssl_context = (
        None
        if args.ca_cert is None
        else ssl.create_default_context(cafile=args.ca_cert)
    )
    identity = load_identity(args.node_id, args.private_key)
    trust_state = SQLiteState(args.trust_db)
    trust = TrustRegistry(trust_state.conn, identity.public)
    capabilities = TrustedCapabilityRegistry(trust_state.conn, trust)
    coordinator = DistributedCoordinator(
        args.network,
        identity,
        args.state,
        HTTPTransportClient(
            args.transport,
            token,
            ssl_context=ssl_context,
        ),
        {},
        trust_registry=trust,
        capability_registry=capabilities,
    )

    try:
        task_id = coordinator.dispatch(
            args.target,
            args.capability,
            json.loads(args.args_json),
            ttl_seconds=args.ttl,
        )
        print(json.dumps({"task_id": task_id}, sort_keys=True), flush=True)
        if args.dispatch_only:
            return

        deadline = time.monotonic() + args.wait_seconds
        while time.monotonic() < deadline:
            coordinator.collect_once()
            results = coordinator.results(task_id)
            if results:
                print(
                    json.dumps(
                        {"task_id": task_id, "results": results},
                        sort_keys=True,
                    ),
                    flush=True,
                )
                return
            time.sleep(0.25)
        raise SystemExit(3)
    finally:
        coordinator.close()
        trust_state.conn.close()


if __name__ == "__main__":
    main()
