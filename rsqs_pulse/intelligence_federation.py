from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import asdict
from typing import Any

from .identity import PublicIdentity
from .intelligence_export import IntelligenceEnvelope, IntelligenceExporter


class FederatedIntelligenceStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS trusted_intelligence_issuers(
          node_id TEXT PRIMARY KEY,
          public_key_b64 TEXT NOT NULL,
          added_at INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS federated_intelligence(
          envelope_id TEXT PRIMARY KEY,
          identity_uri TEXT NOT NULL,
          issuer_node TEXT NOT NULL,
          issued_at INTEGER NOT NULL,
          expires_at INTEGER,
          envelope_json TEXT NOT NULL,
          imported_at INTEGER NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_federated_intelligence_identity
          ON federated_intelligence(identity_uri,issued_at);
        """)
        self.conn.commit()

    def trust_issuer(self, identity: PublicIdentity) -> None:
        self.conn.execute(
            """INSERT INTO trusted_intelligence_issuers(
               node_id,public_key_b64,added_at)
               VALUES(?,?,?)
               ON CONFLICT(node_id) DO UPDATE SET
                 public_key_b64=excluded.public_key_b64,
                 added_at=excluded.added_at""",
            (
                identity.node_id,
                identity.public_key_b64,
                int(time.time()),
            ),
        )
        self.conn.commit()

    def revoke_issuer(self, node_id: str) -> None:
        self.conn.execute(
            "DELETE FROM trusted_intelligence_issuers WHERE node_id=?",
            (node_id,),
        )
        self.conn.commit()

    def trusted_identity(self, node_id: str) -> PublicIdentity | None:
        row = self.conn.execute(
            """SELECT node_id,public_key_b64
               FROM trusted_intelligence_issuers WHERE node_id=?""",
            (node_id,),
        ).fetchone()
        if row is None:
            return None
        return PublicIdentity(row[0], row[1])

    def import_envelope(
        self,
        envelope: IntelligenceEnvelope,
        *,
        now: int | None = None,
    ) -> None:
        public = self.trusted_identity(envelope.issuer_node)
        if public is None:
            raise PermissionError(
                f"untrusted intelligence issuer: {envelope.issuer_node}"
            )
        if not IntelligenceExporter.verify(
            envelope,
            public,
            now=now,
        ):
            raise PermissionError("invalid or expired intelligence envelope")
        self.conn.execute(
            """INSERT OR IGNORE INTO federated_intelligence(
               envelope_id,identity_uri,issuer_node,issued_at,expires_at,
               envelope_json,imported_at)
               VALUES(?,?,?,?,?,?,?)""",
            (
                envelope.envelope_id,
                envelope.identity_uri,
                envelope.issuer_node,
                envelope.issued_at,
                envelope.expires_at,
                json.dumps(asdict(envelope), sort_keys=True),
                int(time.time()),
            ),
        )
        self.conn.commit()

    def latest(
        self,
        identity_uri: str,
        *,
        now: int | None = None,
    ) -> IntelligenceEnvelope | None:
        now = int(time.time()) if now is None else int(now)
        rows = self.conn.execute(
            """SELECT envelope_json
               FROM federated_intelligence
               WHERE identity_uri=?
                 AND (expires_at IS NULL OR expires_at>=?)
               ORDER BY issued_at DESC,rowid DESC""",
            (identity_uri, now),
        ).fetchall()
        for row in rows:
            raw = json.loads(row[0])
            raw["relations"] = tuple(raw.get("relations", ()))
            raw["provenance_refs"] = tuple(raw.get("provenance_refs", ()))
            envelope = IntelligenceEnvelope(**raw)
            public = self.trusted_identity(envelope.issuer_node)
            if (
                public is not None
                and IntelligenceExporter.verify(
                    envelope,
                    public,
                    now=now,
                )
            ):
                return envelope
        return None

    def identities(self, *, now: int | None = None) -> tuple[str, ...]:
        now = int(time.time()) if now is None else int(now)
        rows = self.conn.execute(
            """SELECT DISTINCT identity_uri
               FROM federated_intelligence
               WHERE expires_at IS NULL OR expires_at>=?
               ORDER BY identity_uri""",
            (now,),
        ).fetchall()
        return tuple(row[0] for row in rows)

    def call(
        self,
        identity_uri: str,
        operation: str = "state",
        *,
        now: int | None = None,
    ) -> dict[str, Any]:
        envelope = self.latest(identity_uri, now=now)
        if envelope is None:
            raise KeyError(identity_uri)
        if operation == "state":
            return dict(envelope.state)
        if operation == "relations":
            return {"relations": list(envelope.relations)}
        if operation == "describe":
            return {
                "identity_uri": envelope.identity_uri,
                "issuer_node": envelope.issuer_node,
                "issued_at": envelope.issued_at,
                "expires_at": envelope.expires_at,
                "confidence_floor": envelope.confidence_floor,
                "provenance_refs": list(envelope.provenance_refs),
                "operations": ["describe", "state", "relations"],
            }
        raise ValueError(
            f"unsupported federated intelligence operation: {operation}"
        )

    def status(self, *, now: int | None = None) -> dict[str, int]:
        now = int(time.time()) if now is None else int(now)
        return {
            "trusted_issuers": int(self.conn.execute(
                "SELECT COUNT(*) FROM trusted_intelligence_issuers"
            ).fetchone()[0]),
            "active_identities": int(self.conn.execute(
                """SELECT COUNT(DISTINCT identity_uri)
                   FROM federated_intelligence
                   WHERE expires_at IS NULL OR expires_at>=?""",
                (now,),
            ).fetchone()[0]),
            "envelopes": int(self.conn.execute(
                "SELECT COUNT(*) FROM federated_intelligence"
            ).fetchone()[0]),
        }
