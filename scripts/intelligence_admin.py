#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from rsqs_pulse.digital_twin import DigitalTwinStore
from rsqs_pulse.identity import PublicIdentity
from rsqs_pulse.intelligence_export import (
    IntelligenceDirectory,
    IntelligenceExportPolicy,
    IntelligenceExporter,
)
from rsqs_pulse.intelligence_federation import FederatedIntelligenceStore
from rsqs_pulse.persistent import SQLiteState
from rsqs_pulse.persistent_identity import load_identity


def main():
    parser = argparse.ArgumentParser(
        description="RSQS intelligence identity and federation administration"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    trust = sub.add_parser("trust-issuer")
    trust.add_argument("--state", required=True)
    trust.add_argument("--node-id", required=True)
    trust.add_argument("--public-key", required=True)

    register = sub.add_parser("register")
    register.add_argument("--state", required=True)
    register.add_argument("--owner-node", required=True)
    register.add_argument("--kind", required=True)
    register.add_argument("--local-ref", required=True)
    register.add_argument("--display-name", required=True)
    register.add_argument("--metadata-json", default="{}")

    export = sub.add_parser("export-asset")
    export.add_argument("--state", required=True)
    export.add_argument("--node-id", required=True)
    export.add_argument("--private-key", required=True)
    export.add_argument("--asset-id", required=True)
    export.add_argument("--minimum-confidence", type=float, default=0.0)
    export.add_argument("--ttl", type=int, default=300)

    args = parser.parse_args()
    state = SQLiteState(args.state)
    try:
        if args.command == "trust-issuer":
            federation = FederatedIntelligenceStore(state.conn)
            federation.trust_issuer(
                PublicIdentity(args.node_id, args.public_key)
            )
            print(json.dumps({"trusted": args.node_id}, sort_keys=True))
            return

        if args.command == "register":
            directory = IntelligenceDirectory(state.conn)
            identity = directory.register(
                kind=args.kind,
                local_ref=args.local_ref,
                display_name=args.display_name,
                owner_node=args.owner_node,
                metadata=json.loads(args.metadata_json),
            )
            print(json.dumps({
                "identity_id": identity.identity_id,
                "uri": identity.uri,
            }, sort_keys=True))
            return

        if args.command == "export-asset":
            identity = load_identity(args.node_id, args.private_key)
            directory = IntelligenceDirectory(state.conn)
            twin = DigitalTwinStore(state.conn)
            exporter = IntelligenceExporter(identity, directory, twin)
            intel_id = exporter.ensure_asset_identity(args.asset_id)
            envelope = exporter.export(
                intel_id.identity_id,
                policy=IntelligenceExportPolicy(
                    minimum_confidence=args.minimum_confidence,
                ),
                ttl_seconds=args.ttl,
            )
            from dataclasses import asdict
            print(json.dumps(asdict(envelope), sort_keys=True))
            return
    finally:
        state.conn.close()


if __name__ == "__main__":
    main()
