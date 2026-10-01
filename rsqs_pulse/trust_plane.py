from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass, replace
from typing import Iterable

from .identity import NodeIdentity, PublicIdentity


def _canonical(value: dict) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")


@dataclass(frozen=True)
class AuthorityGrant:
    grant_id: str
    node_id: str
    public_key_b64: str
    scopes: tuple[str, ...]
    issued_at: int
    expires_at: int
    issuer_id: str
    signature: str = ""

    def unsigned(self) -> dict:
        value = asdict(self)
        value.pop("signature", None)
        value["scopes"] = list(self.scopes)
        return value


def issue_grant(
    issuer: NodeIdentity,
    subject: PublicIdentity,
    scopes: Iterable[str],
    ttl_seconds: int,
    *,
    now: int | None = None,
) -> AuthorityGrant:
    if ttl_seconds <= 0:
        raise ValueError("ttl_seconds must be positive")
    now = int(time.time()) if now is None else int(now)
    grant = AuthorityGrant(
        grant_id=str(uuid.uuid4()),
        node_id=subject.node_id,
        public_key_b64=subject.public_key_b64,
        scopes=tuple(sorted(set(scopes))),
        issued_at=now,
        expires_at=now + int(ttl_seconds),
        issuer_id=issuer.node_id,
        signature="",
    )
    return replace(grant, signature=issuer.sign(_canonical(grant.unsigned())))


def verify_grant(
    issuer: PublicIdentity,
    grant: AuthorityGrant,
    *,
    now: int | None = None,
    clock_skew_seconds: int = 30,
) -> bool:
    now = int(time.time()) if now is None else int(now)
    if grant.issuer_id != issuer.node_id:
        return False
    if grant.issued_at > now + clock_skew_seconds:
        return False
    if grant.expires_at < now:
        return False
    return NodeIdentity.verify(issuer, _canonical(grant.unsigned()), grant.signature)


class TrustRegistry:
    def __init__(self, conn: sqlite3.Connection, issuer: PublicIdentity) -> None:
        self.conn = conn
        self.issuer = issuer
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS authority_grants(
          grant_id TEXT PRIMARY KEY,
          node_id TEXT NOT NULL,
          public_key_b64 TEXT NOT NULL,
          scopes_json TEXT NOT NULL,
          issued_at INTEGER NOT NULL,
          expires_at INTEGER NOT NULL,
          issuer_id TEXT NOT NULL,
          signature TEXT NOT NULL,
          revoked_at INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_authority_grants_node
          ON authority_grants(node_id,issued_at);
        """)
        self.conn.commit()

    def accept(self, grant: AuthorityGrant, *, now: int | None = None) -> None:
        if not verify_grant(self.issuer, grant, now=now):
            raise PermissionError("invalid, future-dated or expired authority grant")
        self.conn.execute(
            """INSERT OR REPLACE INTO authority_grants(
               grant_id,node_id,public_key_b64,scopes_json,issued_at,expires_at,
               issuer_id,signature,revoked_at)
               VALUES(?,?,?,?,?,?,?,?,COALESCE(
                 (SELECT revoked_at FROM authority_grants WHERE grant_id=?),NULL
               ))""",
            (
                grant.grant_id,
                grant.node_id,
                grant.public_key_b64,
                json.dumps(grant.scopes),
                grant.issued_at,
                grant.expires_at,
                grant.issuer_id,
                grant.signature,
                grant.grant_id,
            ),
        )
        self.conn.commit()

    def replace_for_node(
        self,
        grant: AuthorityGrant,
        *,
        now: int | None = None,
    ) -> None:
        now = int(time.time()) if now is None else int(now)
        if not verify_grant(self.issuer, grant, now=now):
            raise PermissionError("invalid replacement authority grant")
        self.conn.execute(
            """UPDATE authority_grants SET revoked_at=?
               WHERE node_id=? AND revoked_at IS NULL""",
            (now, grant.node_id),
        )
        self.conn.commit()
        self.accept(grant, now=now)

    def revoke(self, grant_id: str, *, now: int | None = None) -> None:
        now = int(time.time()) if now is None else int(now)
        self.conn.execute(
            "UPDATE authority_grants SET revoked_at=? WHERE grant_id=?",
            (now, grant_id),
        )
        self.conn.commit()

    def active_grant(
        self,
        node_id: str,
        *,
        now: int | None = None,
    ) -> AuthorityGrant | None:
        now = int(time.time()) if now is None else int(now)
        row = self.conn.execute(
            """SELECT grant_id,node_id,public_key_b64,scopes_json,issued_at,
                      expires_at,issuer_id,signature
               FROM authority_grants
               WHERE node_id=? AND (revoked_at IS NULL OR revoked_at>?)
                 AND issued_at<=? AND expires_at>=?
               ORDER BY issued_at DESC,rowid DESC LIMIT 1""",
            (node_id, now, now, now),
        ).fetchone()
        if row is None:
            return None
        return AuthorityGrant(
            row[0], row[1], row[2], tuple(json.loads(row[3])),
            int(row[4]), int(row[5]), row[6], row[7],
        )

    def identity(self, node_id: str, *, now: int | None = None) -> PublicIdentity | None:
        grant = self.active_grant(node_id, now=now)
        if grant is None:
            return None
        return PublicIdentity(grant.node_id, grant.public_key_b64)

    def authorise(
        self,
        node_id: str,
        capability: str,
        *,
        now: int | None = None,
    ) -> bool:
        grant = self.active_grant(node_id, now=now)
        if grant is None:
            return False
        scopes = set(grant.scopes)
        return (
            "*" in scopes
            or capability in scopes
            or f"capability:{capability}" in scopes
        )

    def active_nodes(self, *, now: int | None = None) -> list[str]:
        now = int(time.time()) if now is None else int(now)
        rows = self.conn.execute(
            """SELECT DISTINCT node_id FROM authority_grants
               WHERE revoked_at IS NULL AND issued_at<=? AND expires_at>=?
               ORDER BY node_id""",
            (now, now),
        ).fetchall()
        return [row[0] for row in rows]

    def summary(self, *, now: int | None = None) -> dict:
        now = int(time.time()) if now is None else int(now)
        active_node_ids = self.active_nodes(now=now)
        active = len(active_node_ids)
        revoked = int(self.conn.execute(
            "SELECT COUNT(*) FROM authority_grants WHERE revoked_at IS NOT NULL"
        ).fetchone()[0])
        expired = int(self.conn.execute(
            "SELECT COUNT(*) FROM authority_grants WHERE revoked_at IS NULL AND expires_at<?",
            (now,),
        ).fetchone()[0])
        return {
            "active_nodes": active,
            "active_node_ids": active_node_ids,
            "revoked_grants": revoked,
            "expired_grants": expired,
        }
