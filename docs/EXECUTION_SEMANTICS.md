# Execution semantics

The fabric does not claim universal exactly-once physical execution.

For durable side effects every operation has a stable operation ID and a capability-specific status query.

| External status | Fabric decision |
| --- | --- |
| COMPLETE | Commit observed output; do not execute again |
| NOT_APPLIED | Retry eligible under current authority/policy |
| RUNNING | Wait and query again |
| FAILED | Record failure; do not blindly retry |
| UNKNOWN | Escalate; do not retry automatically |

A worker records local intent before requesting the side effect. After restart, local PENDING state is not evidence that the effect did or did not occur. The external capability is queried using the same operation ID.

This makes the physical system, not the planner, authoritative about whether the effect occurred.

## Required capability contract

A reconciliable capability implements:

```text
execute(operation_id, args) -> output
status(operation_id) -> {state, output, evidence}
```

The external system should itself deduplicate the stable operation ID where possible.

## Safety invariant

UNKNOWN != NOT_APPLIED.

Loss of connectivity, process death, missing acknowledgement or timeout must never be interpreted as proof that an operation is safe to repeat.
