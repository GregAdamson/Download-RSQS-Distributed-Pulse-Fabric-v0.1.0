#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from rsqs_pulse.identity import PublicIdentity
from rsqs_pulse.multi_host_acceptance import (
    HostEvidence,
    MultiHostAcceptanceVerifier,
    issue_host_evidence,
)
from rsqs_pulse.persistent import SQLiteState
from rsqs_pulse.persistent_identity import load_identity
from rsqs_pulse.trust_plane import TrustRegistry


def main() -> None:
    parser = argparse.ArgumentParser(description="RSQS multi-host proof evidence utility")
    sub = parser.add_subparsers(dest="command", required=True)

    emit = sub.add_parser("emit")
    emit.add_argument("--node-id", required=True)
    emit.add_argument("--private-key", required=True)
    emit.add_argument("--host-instance", required=True)
    emit.add_argument("--event", required=True)
    emit.add_argument("--details-json", default="{}")

    verify = sub.add_parser("verify")
    verify.add_argument("--trust-db", required=True)
    verify.add_argument("--authority-id", required=True)
    verify.add_argument("--authority-public", required=True)
    verify.add_argument("--evidence-jsonl", required=True)

    args = parser.parse_args()

    if args.command == "emit":
        identity = load_identity(args.node_id, args.private_key)
        evidence = issue_host_evidence(
            identity,
            args.host_instance,
            args.event,
            json.loads(args.details_json),
        )
        print(json.dumps(asdict(evidence), sort_keys=True))
        return

    state = SQLiteState(args.trust_db)
    try:
        trust = TrustRegistry(
            state.conn,
            PublicIdentity(args.authority_id, args.authority_public),
        )
        items = []
        with open(args.evidence_jsonl, "r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    items.append(HostEvidence(**json.loads(line)))
        report = MultiHostAcceptanceVerifier(trust).assess(items)
        print(json.dumps({
            "passed": report.passed,
            "enrolled_nodes": list(report.enrolled_nodes),
            "host_instances": list(report.host_instances),
            "criteria": [
                {
                    "name": item.name,
                    "passed": item.passed,
                    "evidence_ids": list(item.evidence_ids),
                    "operator_attested": item.operator_attested,
                }
                for item in report.criteria
            ],
        }, sort_keys=True, indent=2))
        raise SystemExit(0 if report.passed else 2)
    finally:
        state.conn.close()


if __name__ == "__main__":
    main()
