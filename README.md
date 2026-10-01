# RSQS Distributed Pulse Fabric

A deterministic, opt-in distributed execution fabric built around signed global pulses.

## Core model

1. A Pulse Authority emits a signed event.
2. Enrolled nodes poll or subscribe to the event stream.
3. Each node verifies signature, freshness, epoch monotonicity, and local policy.
4. Nodes advertise capabilities.
5. Eligible nodes accept tasks and execute only locally permitted handlers.
6. Results are returned with provenance.
7. The coordinator advances shared state by epoch.

This prototype intentionally does not self-propagate, scan the Internet, bypass authentication, or install itself on arbitrary hosts.

## Components

- `rsqs_pulse/crypto.py` - HMAC signing/verification for prototype operation.
- `rsqs_pulse/model.py` - pulse, capability, task, and result schemas.
- `rsqs_pulse/policy.py` - deterministic local allow/deny policy.
- `rsqs_pulse/broker.py` - in-memory event broker.
- `rsqs_pulse/coordinator.py` - epoch, pulse, task routing, result aggregation.
- `rsqs_pulse/node.py` - enrolled node runtime and capability handlers.
- `scripts/demo.py` - local distributed demonstration.
- `tests/test_fabric.py` - deterministic test suite.

## Pulse types

- `WAKE`
- `STATE_CHANGED`
- `AGENT_AVAILABLE`
- `CAPABILITY_AVAILABLE`
- `POLICY_CHANGED`
- `EMERGENCY`
- `TASK`

## Security invariants

- No unsigned pulse is accepted.
- Epochs never move backwards.
- Expired pulses are rejected.
- Local deny overrides coordinator request.
- Only registered handlers may execute.
- Arbitrary shell execution is not supported.
- Every result records node, task, epoch, and status.

## Run

```bash
python3 scripts/demo.py
python3 -m unittest discover -s tests -v
```

## Scaling path

Replace the in-memory broker with NATS, MQTT, Redis Streams, Kafka, or HTTPS/SSE. Replace prototype HMAC with Ed25519 signatures and per-node certificates. Persist epochs and audit events in SQLite/PostgreSQL.
