from __future__ import annotations
import hashlib
import hmac
from dataclasses import replace
from .model import Pulse, canonical_json


def sign_pulse(pulse: Pulse, secret: bytes) -> Pulse:
    body = canonical_json(pulse.unsigned_dict()).encode("ascii")
    sig = hmac.new(secret, body, hashlib.sha256).hexdigest()
    return replace(pulse, signature=sig)


def verify_pulse(pulse: Pulse, secret: bytes) -> bool:
    expected = sign_pulse(replace(pulse, signature=""), secret).signature
    return hmac.compare_digest(expected, pulse.signature)
