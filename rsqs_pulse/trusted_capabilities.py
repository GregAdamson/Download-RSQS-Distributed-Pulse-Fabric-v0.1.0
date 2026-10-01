from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass, replace
from typing import Any

from .identity import NodeIdentity
from .trust_plane import TrustRegistry


def _canonical(value: dict) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")


@dataclass(frozen=True)
class SignedCapabilityAdvertisement:
    advertisement_id: str
    node_id: str
    name: str
    version: str
    metadata: dict[str, Any]
    issued_at: int
    expires_at: int
    signature: str = ""

    def unsigned(self) -> dict:
        value = asdict(self)
        value.pop("signature", None)
        return value


def sign_capability_advertisement(
    identity: NodeIdentity,
    name: str,
    *,
    version: str = "1",
    metadata: dict[str, Any] | None = None,
    ttl_seconds: int = 300,
    now: int | None = None,
) -> SignedCapabilityAdvertisement:
    if ttl_seconds <= 0:
        raise ValueError("ttl_seconds must be positive")
    now = int(time.time()) if now is None else int(now)
    advertisement = SignedCapabilityAdvertisement(
        advertisement_id=str(uuid.uuid4()),
        node_id=identity.node_id,
        name=name,
        version=version,
        metadata=dict(metadata or {}),
        issued_at=now,
        expires_at=now + int(ttl_seconds),
        signature="",
    )
    return replace(
        advertisement,
        signature=identity.sign(_canonical(advertisement.unsigned())),
    )


class TrustedCapabilityRegistry:
    def __init__(
        self,
        conn: sqlite3.Connection,
        trust_registry: TrustRegistry,
    ) -> None:
        self.conn = conn
        self.trust_registry = trust_registry
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS signed_capability_ads(
          advertisement_id TEXT PRIMARY KEY,
          node_id TEXT NOT NULL,
          name TEXT NOT NULL,
          version TEXT NOT NULL,
          metadata_json TEXT NOT NULL,
          issued_at INTEGER NOT NULL,
          expires_at INTEGER NOT NULL,
          signature TEXT NOT NULL
        )
        """)
        self.conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_signed_capability_ads_name
        ON signed_capability_ads(name,node_id,expires_at)
        """)
        self.conn.commit()

    def accept(
        self,
        advertisement: SignedCapabilityAdvertisement,
        *,
        now: int | None = None,
    ) -> None:
        now = int(time.time()) if now is None else int(now)
        if advertisement.issued_at > now + 30:
            raise PermissionError("future-dated capability advertisement")
        if advertisement.expires_at < now:
            raise PermissionError("expired capability advertisement")
        if not self.trust_registry.authorise(
            advertisement.node_id,
            advertisement.name,
            now=now,
        ):
            raise PermissionError("node is not authorised for capability")
        public = self.trust_registry.identity(
            advertisement.node_id,
            now=now,
        )
        if public is None or not NodeIdentity.verify(
            public,
            _canonical(advertisement.unsigned()),
            advertisement.signature,
        ):
            raise PermissionError("invalid capability advertisement signature")
        self.conn.execute(
            """INSERT OR REPLACE INTO signed_capability_ads(
               advertisement_id,node_id,name,version,metadata_json,issued_at,
               expires_at,signature) VALUES(?,?,?,?,?,?,?,?)""",
            (
                advertisement.advertisement_id,
                advertisement.node_id,
                advertisement.name,
                advertisement.version,
                json.dumps(advertisement.metadata, sort_keys=True),
                advertisement.issued_at,
                advertisement.expires_at,
                advertisement.signature,
            ),
        )
        self.conn.commit()

    def providers(
        self,
        capability: str,
        *,
        now: int | None = None,
    ) -> tuple[SignedCapabilityAdvertisement, ...]:
        now = int(time.time()) if now is None else int(now)
        rows = self.conn.execute(
            """SELECT advertisement_id,node_id,name,version,metadata_json,
                      issued_at,expires_at,signature
               FROM signed_capability_ads
               WHERE name=? AND expires_at>=?
               ORDER BY node_id,issued_at DESC,rowid DESC""",
            (capability, now),
        ).fetchall()
        accepted = []
        seen_nodes = set()
        for row in rows:
            advertisement = SignedCapabilityAdvertisement(
                row[0], row[1], row[2], row[3], json.loads(row[4]),
                int(row[5]), int(row[6]), row[7],
            )
            if advertisement.node_id in seen_nodes:
                continue
            if not self.trust_registry.authorise(
                advertisement.node_id,
                advertisement.name,
                now=now,
            ):
                continue
            public = self.trust_registry.identity(
                advertisement.node_id,
                now=now,
            )
            if public is None or not NodeIdentity.verify(
                public,
                _canonical(advertisement.unsigned()),
                advertisement.signature,
            ):
                continue
            accepted.append(advertisement)
            seen_nodes.add(advertisement.node_id)
        return tuple(accepted)
