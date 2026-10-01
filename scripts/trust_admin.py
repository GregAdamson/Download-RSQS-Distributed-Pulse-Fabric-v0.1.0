#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from rsqs_pulse.identity import PublicIdentity
from rsqs_pulse.persistent import SQLiteState
from rsqs_pulse.persistent_identity import load_identity
from rsqs_pulse.trust_plane import AuthorityGrant, TrustRegistry, issue_grant
from rsqs_pulse.trusted_capabilities import (
    SignedCapabilityAdvertisement,
    TrustedCapabilityRegistry,
    sign_capability_advertisement,
)


def _load_json(path: str):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _dump(value) -> None:
    print(json.dumps(value, sort_keys=True, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="RSQS trust-plane operator utility")
    sub = parser.add_subparsers(dest="command", required=True)

    issue = sub.add_parser("issue-grant")
    issue.add_argument("--authority-id", required=True)
    issue.add_argument("--authority-key", required=True)
    issue.add_argument("--subject-id", required=True)
    issue.add_argument("--subject-public", required=True)
    issue.add_argument("--scope", action="append", required=True)
    issue.add_argument("--ttl", type=int, required=True)

    accept = sub.add_parser("accept-grant")
    accept.add_argument("--trust-db", required=True)
    accept.add_argument("--authority-id", required=True)
    accept.add_argument("--authority-public", required=True)
    accept.add_argument("--grant-json", required=True)

    revoke = sub.add_parser("revoke-grant")
    revoke.add_argument("--trust-db", required=True)
    revoke.add_argument("--authority-id", required=True)
    revoke.add_argument("--authority-public", required=True)
    revoke.add_argument("--grant-id", required=True)

    sign_cap = sub.add_parser("sign-capability")
    sign_cap.add_argument("--node-id", required=True)
    sign_cap.add_argument("--private-key", required=True)
    sign_cap.add_argument("--name", required=True)
    sign_cap.add_argument("--version", default="1")
    sign_cap.add_argument("--ttl", type=int, default=300)

    accept_cap = sub.add_parser("accept-capability")
    accept_cap.add_argument("--trust-db", required=True)
    accept_cap.add_argument("--authority-id", required=True)
    accept_cap.add_argument("--authority-public", required=True)
    accept_cap.add_argument("--advertisement-json", required=True)

    summary = sub.add_parser("summary")
    summary.add_argument("--trust-db", required=True)
    summary.add_argument("--authority-id", required=True)
    summary.add_argument("--authority-public", required=True)

    args = parser.parse_args()

    if args.command == "issue-grant":
        authority = load_identity(args.authority_id, args.authority_key)
        grant = issue_grant(
            authority,
            PublicIdentity(args.subject_id, args.subject_public),
            args.scope,
            args.ttl,
        )
        _dump({
            "grant_id": grant.grant_id,
            "node_id": grant.node_id,
            "public_key_b64": grant.public_key_b64,
            "scopes": list(grant.scopes),
            "issued_at": grant.issued_at,
            "expires_at": grant.expires_at,
            "issuer_id": grant.issuer_id,
            "signature": grant.signature,
        })
        return

    if args.command == "sign-capability":
        identity = load_identity(args.node_id, args.private_key)
        ad = sign_capability_advertisement(
            identity,
            args.name,
            version=args.version,
            ttl_seconds=args.ttl,
        )
        _dump({
            "advertisement_id": ad.advertisement_id,
            "node_id": ad.node_id,
            "name": ad.name,
            "version": ad.version,
            "metadata": ad.metadata,
            "issued_at": ad.issued_at,
            "expires_at": ad.expires_at,
            "signature": ad.signature,
        })
        return

    state = SQLiteState(args.trust_db)
    issuer = PublicIdentity(args.authority_id, args.authority_public)
    trust = TrustRegistry(state.conn, issuer)

    try:
        if args.command == "accept-grant":
            raw = _load_json(args.grant_json)
            raw["scopes"] = tuple(raw["scopes"])
            trust.accept(AuthorityGrant(**raw))
            _dump({"accepted": raw["grant_id"]})
        elif args.command == "revoke-grant":
            trust.revoke(args.grant_id)
            _dump({"revoked": args.grant_id})
        elif args.command == "accept-capability":
            raw = _load_json(args.advertisement_json)
            registry = TrustedCapabilityRegistry(state.conn, trust)
            registry.accept(SignedCapabilityAdvertisement(**raw))
            _dump({"accepted": raw["advertisement_id"]})
        elif args.command == "summary":
            _dump(trust.summary())
    finally:
        state.conn.close()


if __name__ == "__main__":
    main()
