from __future__ import annotations
import base64
import os
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from .identity import NodeIdentity

def load_or_create_identity(node_id: str, path: str) -> NodeIdentity:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raw = base64.b64decode(target.read_text(encoding="ascii").strip())
        return NodeIdentity(node_id, Ed25519PrivateKey.from_private_bytes(raw))
    identity = NodeIdentity(node_id)
    raw = identity._private.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(str(target), flags, 0o600)
    try:
        os.write(fd, base64.b64encode(raw) + b"\n")
    finally:
        os.close(fd)
    return identity
