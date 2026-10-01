from __future__ import annotations
import base64
from dataclasses import dataclass
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives import serialization


@dataclass(frozen=True)
class PublicIdentity:
    node_id: str
    public_key_b64: str

    def public_key(self) -> Ed25519PublicKey:
        raw = base64.b64decode(self.public_key_b64.encode("ascii"))
        return Ed25519PublicKey.from_public_bytes(raw)


class NodeIdentity:
    def __init__(self, node_id: str, private_key: Ed25519PrivateKey | None = None) -> None:
        self.node_id = node_id
        self._private = private_key or Ed25519PrivateKey.generate()

    @property
    def public(self) -> PublicIdentity:
        raw = self._private.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return PublicIdentity(self.node_id, base64.b64encode(raw).decode("ascii"))

    def sign(self, payload: bytes) -> str:
        return base64.b64encode(self._private.sign(payload)).decode("ascii")

    def private_bytes_raw(self) -> bytes:
        return self._private.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )

    @classmethod
    def from_private_bytes(cls, node_id: str, raw: bytes) -> "NodeIdentity":
        return cls(node_id, Ed25519PrivateKey.from_private_bytes(raw))

    @staticmethod
    def verify(public: PublicIdentity, payload: bytes, signature_b64: str) -> bool:
        try:
            public.public_key().verify(base64.b64decode(signature_b64.encode("ascii")), payload)
            return True
        except Exception:
            return False
