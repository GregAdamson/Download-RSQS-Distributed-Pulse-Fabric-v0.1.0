# RSQS Distributed State, Cognition and Action Fabric v0.6.0

v0.6 extends the executable fabric from distributed action into a causal-learning substrate.

## New executable primitives

### Sovereign cells

A `SovereignCell` is a recursively composable unit with explicit identity, type, authority scope, capabilities, resources, constraints and relationships. Discovery can filter both capability and authority scope.

### Causal transition memory

`CausalMemory` persists observations of:

```text
CAUSE + ACTION + CONTEXT + BEFORE STATE -> AFTER STATE
```

Supporting and opposing observations remain separate. The causal assessment reports both rather than collapsing disagreement.

### Competing world models

Multiple `WorldModel` implementations can predict the same transition. Actual observed state is compared with every prediction. Prediction error is accumulated and model score changes from evidence rather than textual plausibility.

### Deterministic experiment loop

`LearningRuntime` joins experiments, competing models, causal evidence and hash-chained provenance:

```text
BEFORE STATE
 -> competing predictions
 -> authorised/controlled experiment
 -> observed AFTER STATE
 -> prediction error
 -> model evidence update
 -> causal transition evidence
 -> provenance
 -> next experiment
```

The test suite includes repeated observations that falsify a persistently bad model in favour of the model with lower prediction error.

### Resource substitution

`SubstitutionGraph` represents explicit resource alternatives, conversion ratios and constraints. This is a basis for later scarcity/bottleneck and resilience reasoning without assuming that similarly named resources are interchangeable.

## Proof marker

`scripts/cognitive_substrate_demo.py` runs repeated controlled state transitions and requires the better predictive model to emerge while causal observations and provenance accumulate.

A successful execution ends with:

```text
COGNITIVE_SUBSTRATE_PROOF=PASS
```

## Complete local proof

```bash
./run_all.sh
```

This now includes historical pulse/network demonstrations, persistent runtime recovery, multi-process distributed task/result proof, causal-learning proof and the complete unit/integration test suite.

## Boundaries

The repository now contains executable mechanisms for distributed execution and deterministic causal/model learning. It does not yet establish general causal truth: causal evidence is observational/experimental evidence and must retain provenance, context and counterevidence.

The physical multi-host acceptance test in `docs/MULTI_HOST_PROOF.md` remains unexecuted from this environment. Production deployment still requires durable network infrastructure, TLS, key lifecycle/revocation, explicit enrolment and operational monitoring.
