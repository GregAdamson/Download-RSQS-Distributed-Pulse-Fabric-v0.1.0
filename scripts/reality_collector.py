#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import ssl
import time
import urllib.request
from dataclasses import asdict
from pathlib import Path

from rsqs_pulse.adapter_config import build_observation_adapter
from rsqs_pulse.collector import CollectorSource, ObservationCollector
from rsqs_pulse.persistent import SQLiteState


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
        description="Continuously collect explicitly configured reality feeds"
    )
    parser.add_argument("--config", required=True)
    parser.add_argument("--collector-state", required=True)
    parser.add_argument("--runtime-url", required=True)
    parser.add_argument("--token-env", default="RSQS_REALITY_WRITE_TOKEN")
    parser.add_argument("--ca-cert")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--sleep-seconds", type=float, default=1.0)
    args = parser.parse_args()

    token = os.environ.get(args.token_env)
    if not token:
        raise SystemExit(
            f"missing reality write token environment variable: {args.token_env}"
        )
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    raw_sources = config.get("sources")
    if not isinstance(raw_sources, list):
        raise SystemExit("config must contain a 'sources' list")

    sources = []
    for raw in raw_sources:
        sources.append(
            CollectorSource(
                source_id=str(raw["source_id"]),
                adapter=build_observation_adapter(raw["adapter"]),
                interval_seconds=int(raw.get("interval_seconds", 60)),
                max_backoff_seconds=int(raw.get("max_backoff_seconds", 3600)),
            )
        )

    tls = (
        None if args.ca_cert is None
        else ssl.create_default_context(cafile=args.ca_cert)
    )
    state = SQLiteState(args.collector_state)
    collector = ObservationCollector(state.conn)
    try:
        while True:
            now = int(time.time())
            batches = collector.run_due(sources, now=now)
            for batch in batches:
                if batch.status != "ok" or not batch.observations:
                    continue
                _post(
                    args.runtime_url,
                    token,
                    batch.observations,
                    ssl_context=tls,
                )
            print(json.dumps({
                "collector": list(collector.status()),
                "processed_batches": len(batches),
            }, sort_keys=True), flush=True)
            if args.once:
                return
            time.sleep(max(0.1, args.sleep_seconds))
    finally:
        state.conn.close()


if __name__ == "__main__":
    main()
