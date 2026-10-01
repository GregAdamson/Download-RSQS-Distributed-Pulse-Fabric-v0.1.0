from __future__ import annotations
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, Tuple
from .identity import NodeIdentity, PublicIdentity


@dataclass(frozen=True)
class AgentManifest:
    agent_id: str
    version: str
    artifact_hash: str
    required_capabilities: tuple[str, ...]
    permissions: tuple[str, ...]
    metadata: Dict[str, Any]

    def canonical_bytes(self) -> bytes:
        body = {
            "agent_id": self.agent_id,
            "version": self.version,
            "artifact_hash": self.artifact_hash,
            "required_capabilities": list(self.required_capabilities),
            "permissions": list(self.permissions),
            "metadata": self.metadata,
        }
        return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")

    def content_address(self) -> str:
        return "agent://sha256/" + hashlib.sha256(self.canonical_bytes()).hexdigest()


def sign_manifest(manifest: AgentManifest, identity: NodeIdentity) -> str:
    return identity.sign(manifest.canonical_bytes())


def verify_manifest(manifest: AgentManifest, signature: str, authority: PublicIdentity) -> bool:
    return NodeIdentity.verify(authority, manifest.canonical_bytes(), signature)
