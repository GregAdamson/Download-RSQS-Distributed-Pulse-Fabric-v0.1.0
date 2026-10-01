# RSQS Distributed State, Cognition and Action Fabric v0.3.0

This repository has evolved beyond a pulse transport. It is an opt-in, recursively composable fabric for distributed state, cognition, institutional coordination and authorised action.

It combines signed events, deterministic task graphs, DAL semantic state, trajectory planning, capability discovery, temporary institutions, distributed evidence assessment, resource matching, world-state versioning and independently governed execution nodes.

See `ARCHITECTURE.md` for the complete model.

## v0.3 architecture

```text
OBSERVATION / HUMAN INTENT
          |
          v
DAL SEMANTIC GRAPH
          |
          v
CURRENT STATE + DESIRED STATE
          |
          v
CONSTRAINTS + COUNTERFACTUALS
          |
          v
TRAJECTORY SEARCH
          |
          +------> DISTRIBUTED ORACLE / EVIDENCE
          |
          +------> SIMULATION / QUORUM
          |
          v
CAPABILITY + RESOURCE DISCOVERY
          |
          v
TEMPORARY SWARM / INSTITUTION
          |
          v
LOCAL AUTHORISATION AT EVERY NODE
          |
          v
SIGNED DISTRIBUTED TASKS
          |
          v
ACTION + OUTCOME + EVIDENCE
          |
          v
PROVENANCE + VERSIONED WORLD STATE
          |
          v
LESSON / NEXT STATE
```

## Recursive composition

A fabric node can represent a program, computer, sensor network, institutional gateway, local fabric, regional fabric, research institution or another compatible fabric. Higher layers see declared capability and authority scope rather than silently inheriting control of lower layers.

## Implemented systems

- Ed25519 signed pulse authority and node verification.
- HTTP network transport and local deterministic broker.
- Persistent SQLite state and ordered offline reconciliation.
- Hash-chained provenance.
- DAL semantic graph with state, observation, desired state, constraint, trajectory, action, evidence, counterfactual, lesson and provenance nodes.
- State-transition and trajectory search under deterministic constraints.
- Per-trajectory local authorisation.
- Distributed Oracle retaining supporting and opposing evidence.
- Capability discovery and health/resource-aware routing.
- Resource offer/need matching for real-world allocation modelling.
- Temporary swarms.
- Temporary institutional role assembly.
- Institutional capability gateway with explicit write authority.
- Recursive/fractal fabric descriptors.
- Task DAGs and deterministic intent compilation.
- Simulation and fail-closed quorum gates.
- Signed content-addressed agent manifests.
- Event subscriptions.
- Versioned world state.

## Governance invariant

```text
pulse != permission
signature != permission
network reachability != permission
task request != permission
```

Execution occurs only when local policy authorises a registered local capability.

## Run

```bash
python3 -m pip install -e .
./run_all.sh
```

## Production boundary

The built-in HTTP transport is suitable for development and controlled-network experimentation. Internet-facing production requires TLS, durable event infrastructure, deployment-specific key storage, rotation/revocation, authentication, rate limiting, monitoring and explicit node enrolment.

The fabric intentionally contains no self-propagation, Internet scanning, credential bypass or arbitrary remote shell mechanism.
