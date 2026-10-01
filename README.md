# RSQS Distributed Pulse Fabric v0.2.0

An opt-in distributed cognitive execution fabric built around authenticated global pulses, deterministic intent compilation, local policy, capability discovery, resource-aware routing, task graphs, temporary swarms, persistent world state, provenance, signed agent manifests, subscriptions and offline reconciliation.

The repository does not implement Internet scanning, self-propagation, credential bypass, arbitrary remote shell execution, or installation on non-enrolled machines.

## Architecture

```text
human or machine intent
        |
        v
deterministic intent compiler
        |
        v
task DAG + simulation/admission
        |
        v
capability registry + resource router
        |
        v
Ed25519 signed pulse authority
        |
        v
federated event/subscription namespace
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
versioned world state
```

## Implemented capabilities

- Ed25519 authority and node identities.
- Persistent SQLite epochs, capability advertisements, task results and offline events.
- Hash-chained tamper-evident provenance.
- Capability discovery and deterministic provider filtering.
- Resource/health profiles and resource-aware routing.
- Dependency-checked task DAGs and topological execution.
- Deterministic intent-to-task compilation.
- Temporary swarms assembled from required capabilities.
- Fail-closed quorum rules.
- Pre-execution simulation/admission mode.
- Signed content-addressed agent manifests.
- Event subscriptions with explicit pulse-kind filters.
- Versioned world-state facts with source and confidence.
- Federated institution/region/global topic scopes.
- Ordered offline store-and-forward reconciliation.
- Existing local policy precedence: local deny always wins.
- Backward-compatible v0.1 HMAC demo retained for comparison.

## Major modules

- `identity.py` - Ed25519 identity.
- `secure.py` - secure coordinator and node runtime.
- `persistent.py` - SQLite state.
- `provenance.py` - hash-chain audit ledger.
- `capabilities.py` - capability advertisements.
- `resources.py` / `routing.py` - health/resource-aware routing.
- `taskgraph.py` - deterministic task DAG.
- `intent.py` - deterministic intent compiler.
- `swarm.py` - temporary swarm assembly.
- `quorum.py` - quorum admission.
- `simulation.py` - dry-run analysis.
- `manifests.py` - signed agent manifests and content addresses.
- `subscriptions.py` - filtered event delivery.
- `world_state.py` - versioned shared state.
- `federation.py` - hierarchical namespaces.
- `offline.py` - reconciliation journal.

## Security invariants

- Incorrectly signed secure pulses are rejected.
- Epochs cannot move backwards at a node.
- Expired pulses are rejected.
- Local policy can veto any distributed request.
- Only registered capability handlers execute.
- Task-graph cycles fail before execution.
- Quorum mode fails closed when participation is insufficient.
- Provenance alteration is detectable.
- Agent manifests are verified before trust.
- Offline events reconcile in order.
- Unhealthy nodes are excluded from resource routing.
- No arbitrary shell execution is exposed by the fabric.

## Run

```bash
python3 -m pip install -e .
./run_all.sh
```

The full test command is:

```bash
python3 -m unittest discover -s tests -v
```

## Deployment boundary

The bundled transport is deliberately deterministic and local. Production adapters can map the same semantics onto NATS, MQTT, HTTPS/SSE, Redis Streams or Kafka. Signature verification, local authorization, federation scope and capability admission remain node-side regardless of transport.

## Remaining production hardening

Production deployment still requires deployment-specific key storage, certificate/key rotation and revocation, encrypted transport configuration, rate limiting, schema negotiation, durable broker adapters, multi-authority trust configuration and operational monitoring. Those are deployment concerns rather than hidden permissions in the fabric.
