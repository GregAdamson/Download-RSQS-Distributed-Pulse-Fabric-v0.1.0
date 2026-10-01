# RSQS Distributed State, Cognition and Action Fabric v0.8.0

RSQS is an executable deterministic fabric for authorised distributed action, temporal world-state reasoning, causal learning, resource resilience and auditable strategy selection.

## Implemented layers

### Distributed execution and recovery

The fabric includes signed task/result transport, persistent identity and epochs, local-policy enforcement, idempotency journals, recoverable workers and physical-effect reconciliation. Unknown external outcomes are not interpreted as safe retries.

### Authoritative temporal world state

Observed, believed, predicted, desired and counterfactual state are represented separately. Runtime actions are recorded in a durable operation ledger and observed outcomes override planner predictions.

### Causal and scientific learning

The repository includes competing world models, prediction-error tracking, causal evidence, deterministic experiments, intervention/observation separation, replication evidence, counterevidence and provenance.

### Resource, dependency and resilience reasoning

Persistent resource inventories model quantity, unit, location, quality, ownership, replenishment and lead time. Dependency graphs propagate capability failures, substitution graphs model conversion ratios, and resilience planners allocate shared resources without double counting.

### Whole-network and temporal allocation

The network resilience planner recursively allocates dependencies and substitutions across multiple targets. The temporal allocator carries stock across periods and models minimum service, replenishment, transport capacity, lead time, loss, quality and advance prepositioning.

### Strategy optimisation

`TrajectoryOptimizer` generates, validates, scores and deterministically ranks candidate trajectories. Invalid trajectories cannot outrank admissible ones. Resilience objective weights are explicit configuration.

### Monte Carlo resilience

`MonteCarloResilienceEngine` produces reproducible seeded resource-shock scenarios, evaluates them through a caller-supplied simulator and reports survival rate, average score and failure-period statistics.

### Dependency centrality

`DependencyCentralityAnalyzer` scores both resource and capability nodes, follows recursive downstream dependencies and accounts for explicit substitution alternatives.

### Resilience oracle

`ResilienceOracle` combines temporal viability, Monte Carlo outcomes and dependency centrality into one evidence-bearing assessment rather than treating any single model as authoritative.

### Persistent strategy evidence

`ResilienceStore` persists scenarios, candidate trajectories, outcomes and lessons. `LearningReconciliation` stores predicted versus observed state, explicit error vectors, lessons and provenance across restart.

## Executable proof chain

`run_all.sh` executes the repository demonstrations and the complete unit/integration suite.

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
```

The strategy integration proof exercises:

```text
resource state
 -> temporal allocation
 -> trajectory validation
 -> resilience scoring
 -> selected strategy
 -> seeded Monte Carlo shocks
 -> resilience oracle
 -> prediction/observation reconciliation
 -> persistent lesson
```

## Run

```bash
bash run_all.sh
```

## Design invariants

- local deny overrides remote allow;
- prediction is not observation;
- unknown physical outcome is not proof of non-execution;
- resources cannot be allocated twice;
- invalid trajectories cannot win optimisation;
- learning preserves historical evidence and provenance;
- optimisation searches among admissible trajectories but does not override the deterministic constraint layer.

## Boundaries

This repository is a tested research/software fabric, not evidence of AGI or autonomous general intelligence. The trajectory optimiser is deterministic and objective-driven rather than a proof of globally optimal allocation. Monte Carlo results are only as meaningful as the supplied scenario distributions and simulator. Real production deployment still requires operational infrastructure such as hardened transport/TLS, credential lifecycle and revocation, deployment monitoring and physical multi-host acceptance testing.
