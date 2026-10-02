from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass, replace
from typing import Any, Iterable, Mapping

from .digital_twin import DigitalTwinStore
from .identity import NodeIdentity, PublicIdentity


def _canonical(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")


@dataclass(frozen=True)
class IntelligenceIdentity:
    identity_id: str
    kind: str
    local_ref: str
    display_name: str
    owner_node: str
    metadata: dict[str, Any]

    @property
    def uri(self) -> str:
        return f"rsqs://{self.kind}/{self.identity_id}"


@dataclass(frozen=True)
class IntelligenceExportPolicy:
    minimum_confidence: float = 0.0
    include_keys: tuple[str, ...] = ()
    exclude_keys: tuple[str, ...] = ()
    include_provenance_refs: bool = True
    include_relations: bool = True

    def __post_init__(self) -> None:
        if not 0.0 <= self.minimum_confidence <= 1.0:
            raise ValueError("minimum_confidence must be in [0,1]")


@dataclass(frozen=True)
class IntelligenceEnvelope:
    envelope_id: str
    identity_uri: str
    issuer_node: str
    issued_at: int
    expires_at: int | None
    state: dict[str, Any]
    relations: tuple[dict[str, str], ...]
    confidence_floor: float
    provenance_refs: tuple[str, ...]
    signature: str = ""

    def unsigned(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("signature", None)
        value["relations"] = list(self.relations)
        value["provenance_refs"] = list(self.provenance_refs)
        return value


class IntelligenceDirectory:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS intelligence_identities(
          identity_id TEXT PRIMARY KEY,
          kind TEXT NOT NULL,
          local_ref TEXT NOT NULL,
          display_name TEXT NOT NULL,
          owner_node TEXT NOT NULL,
          metadata_json TEXT NOT NULL,
          created_at INTEGER NOT NULL,
          UNIQUE(kind,local_ref,owner_node)
        )
        """)
        self.conn.commit()

    def register(
        self,
        *,
        kind: str,
        local_ref: str,
        display_name: str,
        owner_node: str,
        metadata: Mapping[str, Any] | None = None,
        identity_id: str | None = None,
    ) -> IntelligenceIdentity:
        existing = self.by_local_ref(kind, local_ref, owner_node)
        if existing is not None:
            return existing
        deterministic_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"rsqs:{owner_node}:{kind}:{local_ref}",
            )
        )
        identity = IntelligenceIdentity(
            identity_id or deterministic_id,
            kind,
            local_ref,
            display_name,
            owner_node,
            dict(metadata or {}),
        )
        self.conn.execute(
            """INSERT INTO intelligence_identities(
               identity_id,kind,local_ref,display_name,owner_node,metadata_json,created_at)
               VALUES(?,?,?,?,?,?,?)""",
            (
                identity.identity_id,
                identity.kind,
                identity.local_ref,
                identity.display_name,
                identity.owner_node,
                json.dumps(identity.metadata, sort_keys=True),
                int(time.time()),
            ),
        )
        self.conn.commit()
        return identity

    def by_local_ref(
        self,
        kind: str,
        local_ref: str,
        owner_node: str,
    ) -> IntelligenceIdentity | None:
        row = self.conn.execute(
            """SELECT identity_id,kind,local_ref,display_name,owner_node,metadata_json
               FROM intelligence_identities
               WHERE kind=? AND local_ref=? AND owner_node=?""",
            (kind, local_ref, owner_node),
        ).fetchone()
        return None if row is None else IntelligenceIdentity(
            row[0], row[1], row[2], row[3], row[4], json.loads(row[5])
        )

    def get(self, identity_id: str) -> IntelligenceIdentity | None:
        row = self.conn.execute(
            """SELECT identity_id,kind,local_ref,display_name,owner_node,metadata_json
               FROM intelligence_identities WHERE identity_id=?""",
            (identity_id,),
        ).fetchone()
        return None if row is None else IntelligenceIdentity(
            row[0], row[1], row[2], row[3], row[4], json.loads(row[5])
        )

    def by_uri(self, uri: str) -> IntelligenceIdentity | None:
        if not uri.startswith("rsqs://"):
            return None
        remainder = uri[len("rsqs://"):]
        if "/" not in remainder:
            return None
        kind, identity_id = remainder.split("/", 1)
        identity = self.get(identity_id)
        if identity is None or identity.kind != kind:
            return None
        return identity

    def all(self) -> tuple[IntelligenceIdentity, ...]:
        rows = self.conn.execute(
            """SELECT identity_id,kind,local_ref,display_name,owner_node,metadata_json
               FROM intelligence_identities ORDER BY kind,display_name,identity_id"""
        ).fetchall()
        return tuple(
            IntelligenceIdentity(
                row[0], row[1], row[2], row[3], row[4], json.loads(row[5])
            )
            for row in rows
        )


class IntelligenceExporter:
    def __init__(
        self,
        identity: NodeIdentity,
        directory: IntelligenceDirectory,
        twin: DigitalTwinStore,
    ) -> None:
        self.identity = identity
        self.directory = directory
        self.twin = twin

    def ensure_asset_identity(self, asset_id: str) -> IntelligenceIdentity:
        asset = self.twin.asset(asset_id)
        if asset is None:
            raise KeyError(asset_id)
        return self.directory.register(
            kind="asset",
            local_ref=asset_id,
            display_name=asset.name,
            owner_node=self.identity.node_id,
            metadata={
                "asset_type": asset.asset_type,
                "parent_id": asset.parent_id,
            },
        )

    def export(
        self,
        identity_id: str,
        *,
        policy: IntelligenceExportPolicy | None = None,
        ttl_seconds: int | None = 300,
        now: int | None = None,
    ) -> IntelligenceEnvelope:
        policy = policy or IntelligenceExportPolicy()
        identity = self.directory.get(identity_id)
        if identity is None:
            raise KeyError(identity_id)
        if identity.owner_node != self.identity.node_id:
            raise PermissionError("identity is not owned by this node")
        now = int(time.time()) if now is None else int(now)
        expires_at = None if ttl_seconds is None else now + int(ttl_seconds)

        state: dict[str, Any] = {}
        relations: tuple[dict[str, str], ...] = ()
        provenance_refs: list[str] = []

        if identity.kind == "asset":
            current = self.twin.latest_state(identity.local_ref)
            include = set(policy.include_keys)
            exclude = set(policy.exclude_keys)
            for key, item in sorted(current.items()):
                if include and key not in include:
                    continue
                if key in exclude or item.confidence < policy.minimum_confidence:
                    continue
                state[key] = {
                    "value": item.value,
                    "unit": item.unit,
                    "confidence": item.confidence,
                    "observed_at": item.observed_at,
                }
                if policy.include_provenance_refs:
                    provenance_refs.append(item.source_ref)
            if policy.include_relations:
                relations = tuple(
                    {
                        "source": rel.source_asset,
                        "relation": rel.relation,
                        "target": rel.target_asset,
                    }
                    for rel in self.twin.relations(identity.local_ref)
                )
        else:
            state = dict(identity.metadata)

        confidence_floor = min(
            (float(item.get("confidence", 1.0)) for item in state.values() if isinstance(item, dict)),
            default=1.0,
        )
        envelope = IntelligenceEnvelope(
            envelope_id=str(uuid.uuid4()),
            identity_uri=identity.uri,
            issuer_node=self.identity.node_id,
            issued_at=now,
            expires_at=expires_at,
            state=state,
            relations=relations,
            confidence_floor=confidence_floor,
            provenance_refs=tuple(sorted(set(provenance_refs))),
            signature="",
        )
        return replace(
            envelope,
            signature=self.identity.sign(_canonical(envelope.unsigned())),
        )

    @staticmethod
    def verify(
        envelope: IntelligenceEnvelope,
        public_identity: PublicIdentity,
        *,
        now: int | None = None,
    ) -> bool:
        now = int(time.time()) if now is None else int(now)
        if envelope.issuer_node != public_identity.node_id:
            return False
        if envelope.expires_at is not None and envelope.expires_at < now:
            return False
        return NodeIdentity.verify(
            public_identity,
            _canonical(envelope.unsigned()),
            envelope.signature,
        )
