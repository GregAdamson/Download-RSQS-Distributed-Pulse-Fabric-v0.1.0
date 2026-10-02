#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import ssl
import urllib.request
from dataclasses import asdict
from pathlib import Path

from rsqs_pulse.adapter_config import build_observation_adapter


def _post(url, token, observations, *, ssl_context=None, timeout=15.0):
    body = json.dumps(
        {"observations": [asdict(item) for item in observations]},
        sort_keys=True,
    ).encode("utf-8")
    request = urllib.request.Request(
        url.rstrip("/") + "/reality/observations",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    kwargs = {"timeout": timeout}
    if ssl_context is not None:
        kwargs["context"] = ssl_context
    with urllib.request.urlopen(request, **kwargs) as response:
        return json.loads(response.read().decode("utf-8"))


def main():
    parser = argparse.ArgumentParser(
        description="Fetch configured observation sources and ingest into RSQS reality API"
    )
    parser.add_argument("--config", required=True)
    parser.add_argument("--runtime-url", required=True)
    parser.add_argument("--token-env", default="RSQS_REALITY_WRITE_TOKEN")
    parser.add_argument("--ca-cert")
    parser.add_argument("--batch-size", type=int, default=250)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    sources = config.get("sources", config if isinstance(config, list) else None)
    if not isinstance(sources, list):
        raise SystemExit("config must be a list or contain a 'sources' list")

    observations = []
    for source_config in sources:
        adapter = build_observation_adapter(source_config)
        observations.extend(adapter.fetch())

    if args.dry_run:
        print(json.dumps({
            "sources": len(sources),
            "observations": len(observations),
        }, sort_keys=True))
        return

    token = os.environ.get(args.token_env)
    if not token:
        raise SystemExit(
            f"missing reality write token environment variable: {args.token_env}"
        )
    if args.batch_size <= 0:
        raise SystemExit("--batch-size must be positive")

    tls = (
        None if args.ca_cert is None
        else ssl.create_default_context(cafile=args.ca_cert)
    )
    accepted = 0
    fused = 0
    for offset in range(0, len(observations), args.batch_size):
        response = _post(
            args.runtime_url,
            token,
            observations[offset:offset + args.batch_size],
            ssl_context=tls,
        )
        accepted += int(response.get("accepted", 0))
        fused += int(response.get("fused", 0))

    print(json.dumps({
        "sources": len(sources),
        "observations": len(observations),
        "accepted": accepted,
        "fused": fused,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
