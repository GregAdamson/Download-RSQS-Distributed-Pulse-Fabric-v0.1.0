# RSQS Distributed State, Cognition and Action Fabric v0.4.0

v0.4 is the vertical-integration release. The repository now contains a persistent runtime that actually joins the earlier architectural components into a state-to-action cycle rather than leaving them only as independent primitives.

## Executable runtime loop

```text
OBSERVATION
  -> PERSISTED WORLD STATE
  -> TRAJECTORY SEARCH
  -> CONSTRAINT CHECKING
  -> CAPABILITY AVAILABILITY
  -> LOCAL POLICY AUTHORISATION
  -> REGISTERED CAPABILITY EXECUTION
  -> ACTION RECEIPT
  -> WORLD-STATE UPDATE
  -> HASH-CHAINED PROVENANCE
  -> PERSISTED CYCLE RESULT
  -> RESTART / RECOVERY
```

`FabricRuntime` is the integrated process. It owns persistent SQLite state, world state, capability registration, DAL observations, trajectory reasoning, local authorisation, action execution, cycle/action records and provenance.

## Daemon

Installation exposes:

```bash
rsqs-fabricd --node-id node-a --state ./state/node-a.db --port 8787
```

The daemon exposes read-only operational endpoints:

```text
GET /health
GET /state
GET /capabilities
```

No arbitrary shell or generic remote execution endpoint is provided.

## Proof paths

`scripts/runtime_demo.py` executes a complete multi-step trajectory, persists the resulting world state, closes the process, opens a fresh runtime against the same database and demonstrates recovered state.

`tests/test_runtime_integration.py` verifies:

- a complete observation-to-action cycle;
- multiple actions in a trajectory;
- world-state persistence;
- restart recovery;
- provenance-chain validity;
- local policy denial;
- unavailable-capability denial.

The earlier distributed layers remain present: Ed25519 pulse identities, HTTP pulse transport, capability registry, task DAGs, resource routing, swarms, temporary institutions, Oracle evidence aggregation, resource exchange, signed agent manifests, federation scopes, subscriptions, offline reconciliation and recursive fabric descriptors.

## Run everything

```bash
./run_all.sh
```

That command installs the package, runs the legacy demonstrations, network transport demonstration, integrated runtime demonstration and the complete unit-test suite.

## Current boundary

v0.4 is an integrated single-runtime build plus network transport primitives. The next proof milestone is a multi-process/multi-machine integration harness in which separately running enrolled nodes receive signed tasks, execute locally authorised capabilities, return signed results, survive node failure and reconcile after restart.

Production Internet deployment additionally requires TLS termination, durable broker infrastructure, deployment-specific key storage and rotation/revocation, rate limiting, explicit enrolment and operational monitoring.
