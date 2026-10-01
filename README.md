# RSQS Distributed State, Cognition and Action Fabric v0.9.0

RSQS is an executable deterministic fabric for authorised distributed action, temporal world-state reasoning, causal learning, resource resilience, bounded strategy search and auditable operational coordination.

## v0.9 operational layer

### Explicit trust plane

Nodes can be enrolled using authority-signed grants with:

- public-key identity;
- scoped capabilities;
- issue and expiry time;
- revocation;
- key rotation.

Distributed dispatch can require both an active authority grant and a currently valid node-signed capability advertisement. Local worker policy remains an independent deny boundary.

### Durable and TLS-capable transport

The pulse HTTP transport can use a durable SQLite event store and optional TLS server/client contexts. The deployment CLI reads bearer tokens from an environment variable instead of requiring them on the command line.

### Multi-host acceptance harness

The repository contains signed host-evidence generation and verification for the physical multi-host acceptance criteria. The verifier requires enrolled signing identities and distinct host-instance attestations.

`MULTI_HOST_HARNESS_PROOF=PASS` proves the harness in CI. It does **not** prove that three physical machines have passed acceptance. Physical acceptance remains the procedure in `docs/V09_MULTI_HOST_RUNBOOK.md`.

### Operational observability

The runtime observability surface includes:

- health and provenance validity;
- current world state;
- unresolved operations;
- registered capability status;
- active enrolled node IDs and trust counts;
- resource bottlenecks when an inventory/dependency graph is attached;
- strategy evidence counts;
- highest-scoring validated stored trajectory.

The runtime daemon exposes this through `/observability` and unresolved operations through `/operations`.

### Bounded strategy search

The strategy layer now has:

- deterministic trajectory generation/validation/scoring;
- bounded beam search;
- exhaustive bounded search.

Exhaustive search reports whether the configured finite search space was completed or truncated by the candidate cap. A result is only globally optimal **within the configured bounds and generated search tree** when the search reports complete.

### Target-agnostic institutional/data adapters

The adapter layer is intentionally domain-neutral. Caller-supplied mappings can project external records into canonical:

- observations;
- resources;
- capability/resource dependencies;
- institutional rules;
- provenance references.

Adapter batches can be applied to runtime world state, resource inventory, dependency graphs and a persistent institutional rule store without hard-coding a sector or institution.

## Existing deterministic substrate

v0.9 retains the prior executable layers:

- signed distributed task/result execution;
- persistent identity and epochs;
- idempotency and physical-effect reconciliation;
- authoritative temporal state;
- causal/scientific learning;
- resource inventories and substitution;
- recursive dependency/resilience planning;
- multi-period allocation with replenishment, quality, transport, loss and lead time;
- resilience objective scoring;
- seeded Monte Carlo shock testing;
- dependency centrality;
- resilience oracle;
- persistent scenarios, trajectories, outcomes and lessons.

## Executable proof chain

Run:

```bash
bash run_all.sh
```

The complete build compiles the package, deployment scripts and tests before running all demonstrations and unit/integration tests.

Current proof markers include:

```text
DISTRIBUTED_PROCESS_PROOF=PASS
COGNITIVE_SUBSTRATE_PROOF=PASS
HARDENING_PROOF=PASS
PHYSICAL_RECONCILIATION_PROOF=PASS
RESOURCE_RESILIENCE_PROOF=PASS
NETWORK_RESILIENCE_PROOF=PASS
TEMPORAL_ALLOCATION_PROOF=PASS
STRATEGY_ORACLE_PROOF=PASS
OPERATIONAL_FABRIC_PROOF=PASS
MULTI_HOST_HARNESS_PROOF=PASS
```

## Deployment tooling

Operator-facing scripts include:

```text
scripts/pulse_transport_server.py
scripts/host_coordinator.py
scripts/host_worker.py
scripts/trust_admin.py
scripts/multi_host_evidence.py
```

The canonical physical-host procedure is:

```text
docs/V09_MULTI_HOST_RUNBOOK.md
```

## Design invariants

- local deny overrides remote allow;
- enrolment is explicit and scoped;
- expired or revoked authority is not valid authority;
- capability discovery can require signed advertisements;
- prediction is not observation;
- unknown physical outcome is not proof of non-execution;
- resources cannot be allocated twice;
- current obligations are not silently sacrificed for future ones;
- invalid trajectories cannot win optimisation;
- truncated search is not described as globally optimal;
- learning preserves historical evidence and provenance;
- optimisation proposes; deterministic admissibility decides;
- no Internet scanning, self-propagation or arbitrary remote shell is part of the fabric.

## Boundaries

This repository is tested research/software infrastructure, not evidence of AGI or autonomous general intelligence.

CI proves the software mechanisms and simulated/signed acceptance harness. It does not establish:

- physical independence of hosts;
- absence of a copied secret without operator attestation;
- production security accreditation;
- Internet-scale operation;
- global mathematical optimality outside a fully explored bounded search space.

The remaining physical acceptance boundary is to run the v0.9 multi-host procedure on three distinct enrolled machines and preserve their signed evidence/logs.
