# RSQS Distributed State, Cognition and Action Fabric v0.5.0

v0.5 adds the first hard multi-process distributed proof.

## Demonstrated path

```text
COORDINATOR PROCESS
  -> Ed25519 signed TASK
  -> HTTP event transport
  -> INDEPENDENT WORKER PROCESS
  -> authority signature verification
  -> target-node check
  -> local capability policy
  -> registered handler execution
  -> worker-signed RESULT
  -> HTTP event transport
  -> coordinator worker-trust lookup
  -> worker signature verification
  -> persistent result + provenance
```

`scripts/distributed_process_demo.py` starts an HTTP event service plus two independent worker OS processes. Worker A doubles a value; Worker B triples it. The coordinator dispatches separately targeted tasks and asserts returned values.

The proof then terminates Worker A, publishes work while it is unavailable, starts a new Worker A process against the same SQLite state, and verifies that its persisted event cursor causes the missed task to be consumed and a signed result returned. Finally the coordinator is reopened from disk and the previously verified results and provenance chain are checked again.

A successful run ends with:

```text
DISTRIBUTED_PROCESS_PROOF=PASS
```

## Security properties in this proof

- task origin is Ed25519 verified by workers;
- results are independently Ed25519 signed by workers;
- coordinator accepts results only from explicitly trusted worker public keys;
- tasks can target a specific node;
- local capability policy remains authoritative;
- unavailable/denied capability requests do not execute;
- worker event cursors persist across restart;
- coordinator results persist across restart;
- provenance remains hash-chain verified;
- no arbitrary remote shell is exposed.

## Run the full proof

```bash
./run_all.sh
```

This runs all historical demos, the integrated single-runtime recovery proof, the new multi-process distributed proof and all unit/integration tests.

## Current boundary

v0.5 proves multiple independent processes communicating over a real HTTP socket on one host. It does **not** yet prove operation across separate physical machines. The same HTTP boundary is network-addressable, but a genuine multi-machine proof still requires deploying enrolled workers on separate hosts and running the same signed task/result/failure-recovery assertions across that boundary.

Production hardening also still requires TLS termination, a durable network event service, key storage/rotation/revocation, rate limiting, explicit enrolment tooling and operational monitoring.
