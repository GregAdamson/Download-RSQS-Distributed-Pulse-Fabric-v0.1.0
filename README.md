# RSQS Distributed Reality Intelligence Fabric v0.10.0

RSQS is an executable deterministic fabric for authorised distributed action, temporal reasoning, resource resilience, bounded strategy search, trusted real-world observation and auditable reality reconciliation.

## v0.10 operational reality layer

### External observation adapters

The fabric can ingest observations from:

- JSON HTTP endpoints;
- JSON files;
- CSV files;
- generic telemetry mappings;
- weather mappings;
- satellite mappings;
- logistics mappings;
- market mappings.

The named domain adapters share the same canonical `PhysicalObservation` interface. Adapter configuration can be supplied as JSON rather than hard-coded Python. HTTP credentials can be supplied through environment variables.

### Evidence fusion

`EvidenceFusionEngine` combines multiple measurements of the same asset/state while preserving:

- per-source confidence;
- source reliability;
- evidence staleness;
- independence groups;
- disagreement;
- contradiction status;
- contributor provenance.

Correlated derived feeds share an evidence budget so duplicated downstream feeds do not masquerade as independent confirmation.

### Persistent physical evidence

`RealityStore` persists:

- raw physical observations;
- fused observations;
- expected-vs-observed variances.

The state survives restart.

### Digital twins

`DigitalTwinStore` persists:

- asset identity and type;
- parent/child hierarchy;
- asset relationships;
- time-versioned physical state;
- observation confidence;
- source references.

Hierarchy updates are transactional and reject cycles.

### Active information requirements

`InformationRequirementEngine` identifies state that is:

- missing;
- stale;
- below required confidence;
- supported by contradictory evidence.

Open information requirements are persistent and close when acceptable evidence arrives.

### Active observation acquisition

`AcquisitionPlanner` selects bounded observation sources for open information needs. Selection considers:

- source reliability;
- expected cost;
- latency;
- source independence;
- supported observation types;
- optional asset scope.

`AcquisitionExecutor` invokes only the selected adapters. The resulting evidence flows back through fusion, the twin and world state.

### Reality runtime

`RealityEngine` connects:

```text
external feed
 -> PhysicalObservation
 -> persistent raw evidence
 -> evidence fusion
 -> persistent fused state
 -> digital twin
 -> authoritative RSQS world state
 -> information requirements
 -> bounded source acquisition
 -> expected-vs-observed variance
 -> provenance ledger
```

The authoritative runtime state uses keys such as:

```text
physical.<asset_id>.<observation_type>
physical.<asset_id>.<observation_type>:confidence
physical.<asset_id>.<observation_type>:unit
physical.<asset_id>.<observation_type>:contradictory
```

### Operational Reality API

The runtime daemon can expose the reality layer with `--reality`.

Read endpoints:

```text
GET /reality/status
GET /reality/needs
GET /reality/twin?asset_id=<id>
```

Write endpoint:

```text
POST /reality/observations
```

Writes require a bearer token supplied by environment variable. Optional TLS certificate/key support is available for the runtime daemon.

### Configuration-driven ingestion

`scripts/reality_ingest.py` loads one or more adapter definitions, fetches the external feeds and posts canonical observations to the running reality API.

Supported source configuration types:

```text
http_json
json_file
csv_file
```

## Existing operational substrate

v0.10 retains the v0.9 capabilities:

- signed scoped node enrolment;
- expiry, revocation and key rotation;
- signed capability advertisements;
- durable/TLS-capable pulse transport;
- local deny overriding remote allow;
- idempotent/reconciled distributed execution;
- physical-effect reconciliation;
- authoritative temporal state;
- resource inventories and substitution;
- recursive dependency/resilience planning;
- multi-period allocation;
- Monte Carlo resilience;
- resilience oracle;
- beam and exhaustive bounded trajectory search;
- operational observability;
- signed multi-host acceptance evidence.

## Complete proof chain

Run:

```bash
bash run_all.sh
```

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
REALITY_OPERATIONAL_PROOF=PASS
```

The reality tests additionally exercise:

- a live localhost JSON HTTP feed;
- authenticated observation writes;
- config-driven HTTP headers;
- persistent restart recovery;
- correlation-aware evidence fusion;
- staleness weighting;
- contradiction detection;
- transactional twin hierarchy rollback;
- information-need creation and resolution;
- active acquisition from independent sources;
- RSQS state projection;
- reality variance persistence.

## Operator tooling

```text
scripts/pulse_transport_server.py
scripts/host_coordinator.py
scripts/host_worker.py
scripts/trust_admin.py
scripts/multi_host_evidence.py
scripts/reality_ingest.py
```

## Design invariants

- prediction is not observation;
- observation confidence and provenance are retained;
- correlated sources do not count as independent confirmation;
- stale evidence loses influence;
- contradictory evidence remains visible;
- missing or uncertain state creates an explicit information need;
- acquisition is bounded and source-selective;
- local deny overrides remote allow;
- unknown physical execution outcome is not proof of non-execution;
- invalid trajectories cannot win optimisation;
- truncated search is not called globally optimal;
- no Internet scanning, self-propagation or arbitrary remote shell is part of the fabric.

## Operational boundary

The software is operational as a tested local/distributed reality-intelligence fabric: it can ingest configured feeds, persist and fuse evidence, maintain twins, detect information gaps, acquire bounded additional observations and expose the state through an authenticated API.

This does **not** by itself prove that any specific external production sensor, satellite service, SCADA system or institutional feed has been connected. Those integrations require source-specific URLs, credentials, schemas and acceptance evidence.

Physical three-host acceptance remains separate and is documented in `docs/V09_MULTI_HOST_RUNBOOK.md`.
