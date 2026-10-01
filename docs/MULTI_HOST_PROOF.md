# Multi-host proof

This is the next acceptance test. It must use independently administered enrolled hosts. Do not scan for nodes and do not copy a coordinator private key to workers.

## Trust setup

Generate one coordinator identity and one identity per worker. Exchange only public keys. Keep each private key on the machine that owns it.

## Transport

Run the existing event transport on an explicitly reachable controlled-network address. For any untrusted network, put it behind TLS before testing.

## Worker

On each enrolled worker install the package and run:

```bash
python3 scripts/host_worker.py \
  --node-id worker-a \
  --network rsqs-proof \
  --authority-id coordinator \
  --authority-public '<COORDINATOR_PUBLIC_KEY>' \
  --private-key ./worker-a.key \
  --state ./state/worker-a.db \
  --transport http://COORDINATOR_HOST:PORT \
  --token '<TRANSPORT_TOKEN>' \
  --capability math.scale \
  --multiplier 2
```

Use a different node identity and multiplier on worker-b.

## Acceptance criteria

The proof is complete only when logs/evidence show all of the following:

1. coordinator and workers are different physical hosts;
2. workers verify coordinator-signed tasks;
3. coordinator verifies worker-signed results;
4. local deny prevents handler execution;
5. worker A is stopped before a task is published;
6. that task has no result while A is offline;
7. A is restarted using the same persistent state;
8. A consumes the missed task and returns the correct signed result;
9. coordinator restart preserves accepted results;
10. provenance verification succeeds;
11. no worker has the coordinator private key;
12. no arbitrary shell capability is exposed.

A repository commit is not evidence that this proof passed. Preserve terminal output or CI/runner logs from the actual hosts as the acceptance artifact.
