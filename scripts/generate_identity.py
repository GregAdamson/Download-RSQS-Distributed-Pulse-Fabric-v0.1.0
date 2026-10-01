#!/usr/bin/env python3
import argparse
import base64
from cryptography.hazmat.primitives import serialization
from rsqs_pulse.identity import NodeIdentity

p = argparse.ArgumentParser()
p.add_argument("--node-id", required=True)
p.add_argument("--private-out", required=True)
args = p.parse_args()
identity = NodeIdentity(args.node_id)
raw = identity._private.private_bytes(
    encoding=serialization.Encoding.Raw,
    format=serialization.PrivateFormat.Raw,
    encryption_algorithm=serialization.NoEncryption(),
)
with open(args.private_out, "wt", encoding="ascii") as handle:
    handle.write(base64.b64encode(raw).decode("ascii") + "\n")
print(identity.public.public_key_b64)
