# v0.9 Release Status

## Software-complete in repository

- signed scoped enrolment grants;
- expiry, revocation and key rotation;
- signed capability advertisements;
- trust-bound coordinator dispatch/result verification;
- durable pulse event storage;
- optional TLS transport contexts;
- hardened worker/coordinator/transport operator CLIs;
- operational observability API;
- target-agnostic observation/resource/dependency/rule adapters;
- persistent institutional rule store;
- bounded beam search;
- exhaustive bounded search with truncation/completeness reporting;
- signed multi-host evidence generation and verification;
- v0.9 operational CI proof demo.

## CI proof vs physical proof

CI may prove:

- cryptographic grant/signature verification logic;
- revocation/rotation behaviour;
- TLS round trip;
- durable event restart;
- local policy/trust interaction;
- search bounds/completeness semantics;
- adapter materialisation;
- observability endpoints;
- signed multi-host evidence verifier behaviour.

CI cannot prove that three named host instances are physically independent. The physical proof remains pending until `docs/V09_MULTI_HOST_RUNBOOK.md` is executed on real enrolled machines and their signed evidence/logs are preserved.

## Search claim boundary

`ExhaustiveTrajectorySearch` may identify the highest-scoring admissible candidate in the generated finite search tree. The result is only described as globally optimal within configured bounds when:

```text
complete_within_bounds == True
truncated_by_candidate_cap == False
```

No claim of unconstrained/global mathematical optimality is made.

## Domain claim boundary

The v0.9 adapter framework is target-agnostic. It does not encode a particular sector, institution, jurisdiction or policy corpus. Domain meaning is supplied through mapping specifications, canonical dependencies and institutional rules.
