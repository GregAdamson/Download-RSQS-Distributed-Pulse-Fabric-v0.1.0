# RSQS Distributed Pulse Fabric v0.2.0

An opt-in distributed cognitive execution fabric built around authenticated global pulses, local policy, capability discovery, task graphs, temporary swarms, persistent state, provenance and offline reconciliation.

The repository does not implement Internet scanning, self-propagation, credential bypass, arbitrary remote shell execution, or installation on non-enrolled machines.

## Architecture

```text
human or machine intent
        |
        v
semantic/task graph
        |
        v
simulation / admission
        |
        v
Ed25519 signed pulse authority
        |
        v
federated transport namespace
        |
   +----+----+----------------+
   |         |                |
 node A    node B           node C
   |         |                |
local      local            local
policy     policy           policy
   |         |                |
capability capability       capability
execution  execution        execution
   |         |                |
   +---------+----------------+
             |
             v
results + evidence + provenance
             |
             v
persistent epoch / world-state inputs
```

## v0.2 capabilities

- Ed25519 authority and node identity primitives.
- Persistent SQLite epoch, capability, result and offline-event state.
- Hash-chained provenance ledger with verification.
- Distributed capability advertisement and deterministic provider selection.
- Dependency-checked task DAGs and topological execution.
- Temporary capability swarms.
- Fail-closed quorum rules.
- Pre-execution simulation/admission mode.
- Federated topic scopes for institution/region/global namespaces.
- Ordered offline journaling and reconciliation.
- Existing local policy precedence: local deny always wins.
- Backward-compatible v0.1 HMAC demo retained for comparison.

## Components

- `rsqs_pulse/identity.py` - Ed25519 identity and signature verification.
- `rsqs_pulse/secure.py` - signed coordinator and secure node runtime.
- `rsqs_pulse/persistent.py` - SQLite state.
- `rsqs_pulse/provenance.py` - append-only hash-chain audit ledger.
- `rsqs_pulse/capabilities.py` - capability registry.
- `rsqs_pulse/taskgraph.py` - deterministic task graphs.
- `rsqs_pulse/swarm.py` - temporary swarm assembly.
- `rsqs_pulse/quorum.py` - quorum admission.
- `rsqs_pulse/simulation.py` - dry-run policy/admission analysis.
- `rsqs_pulse/federation.py` - hierarchical namespace boundaries.
- `rsqs_pulse/offline.py` - store-and-forward reconciliation.
- `scripts/demo_v02.py` - integrated v0.2 demonstration.
- `tests/test_v02.py` - v0.2 security and systems tests.

## Security invariants

- Unsigned or incorrectly signed secure pulses are rejected.
- Epochs cannot move backwards at a node.
- Expired pulses are rejected.
- Local policy can veto any distributed request.
- Only registered capability handlers can execute.
- Task graph cycles fail before execution.
- Quorum mode fails closed when minimum participation is absent.
- Provenance is tamper-evident.
- Offline events reconcile in sequence.
- No arbitrary shell execution is exposed by the fabric.

## Run

```bash
python3 -m pip install -e .
python3 scripts/demo.py
python3 scripts/demo_v02.py
python3 -m unittest discover -s tests -v
```

Or:

```bash
./run_all.sh
```

## Production transport boundary

The coordination semantics are transport-independent. The included broker remains deterministic and local for tests. A production deployment can implement the same publish/subscribe contract over NATS, MQTT, HTTPS/SSE, Redis Streams or Kafka while retaining signature verification and local policy at every node.

## Next production hardening

The v0.2 fabric establishes the distributed control plane. Production deployment should add certificate rotation/revocation, persistent transport adapters, encrypted node-to-node channels, resource/health telemetry, schema-version negotiation, rate limiting, multi-authority trust policy, and deployment-specific secret/key storage.
