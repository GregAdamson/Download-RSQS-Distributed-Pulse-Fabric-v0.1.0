# RSQS v0.9 Physical Multi-Host Acceptance Runbook

This runbook is for explicitly enrolled, operator-controlled hosts only. It does not scan networks, self-enrol machines, copy private keys between nodes, or expose an arbitrary shell.

The CI marker `MULTI_HOST_HARNESS_PROOF=PASS` verifies the evidence machinery only. **It is not evidence that the physical-host acceptance test has passed.** Physical acceptance requires signed evidence generated on three distinct enrolled machines.

## Roles

Use three independently running hosts:

- coordinator
- worker-a
- worker-b

Generate each private key on the machine that owns it. Exchange public keys only.

## 1. Transport

Set the bearer token in the environment rather than the command line:

```bash
export RSQS_TRANSPORT_TOKEN='...'
```

Start the durable transport on the controlled coordinator network:

```bash
python3 scripts/pulse_transport_server.py \
  --host 0.0.0.0 \
  --port 8790 \
  --store ./state/pulse-events.db \
  --cert ./tls/server.crt \
  --key ./tls/server.key
```

Use TLS for any network that is not already a trusted isolated transport.

## 2. Enrol workers

On the coordinator, issue a short-lived signed grant for each worker public key:

```bash
python3 scripts/trust_admin.py issue-grant \
  --authority-id coordinator \
  --authority-key ./keys/coordinator.key \
  --subject-id worker-a \
  --subject-public '<WORKER_A_PUBLIC>' \
  --scope capability:math.scale \
  --scope proof:multi_host \
  --ttl 3600 > worker-a.grant.json
```

Accept the grant into the coordinator trust database:

```bash
python3 scripts/trust_admin.py accept-grant \
  --trust-db ./state/trust.db \
  --authority-id coordinator \
  --authority-public '<COORDINATOR_PUBLIC>' \
  --grant-json worker-a.grant.json
```

Repeat for worker-b.

## 3. Signed capability advertisement

On each worker:

```bash
python3 scripts/trust_admin.py sign-capability \
  --node-id worker-a \
  --private-key ./keys/worker-a.key \
  --name math.scale \
  --ttl 600 > worker-a.capability.json
```

Transfer only the signed JSON to the coordinator and accept it:

```bash
python3 scripts/trust_admin.py accept-capability \
  --trust-db ./state/trust.db \
  --authority-id coordinator \
  --authority-public '<COORDINATOR_PUBLIC>' \
  --advertisement-json worker-a.capability.json
```

## 4. Start workers

```bash
export RSQS_TRANSPORT_TOKEN='...'

python3 scripts/host_worker.py \
  --node-id worker-a \
  --network rsqs-proof \
  --authority-id coordinator \
  --authority-public '<COORDINATOR_PUBLIC>' \
  --private-key ./keys/worker-a.key \
  --state ./state/worker-a.db \
  --transport https://COORDINATOR_HOST:8790 \
  --ca-cert ./tls/ca.crt \
  --capability math.scale \
  --multiplier 2
```

Run worker-b with its own identity, state file and multiplier.

## 5. Dispatch

From the coordinator:

```bash
python3 scripts/host_coordinator.py \
  --node-id coordinator \
  --private-key ./keys/coordinator.key \
  --network rsqs-proof \
  --state ./state/coordinator.db \
  --trust-db ./state/trust.db \
  --transport https://COORDINATOR_HOST:8790 \
  --ca-cert ./tls/ca.crt \
  --target worker-a \
  --capability math.scale \
  --args-json '{"value":4}'
```

The coordinator refuses dispatch if either the grant or the signed capability advertisement is absent/expired/revoked.

## 6. Fault sequence

Perform the existing acceptance sequence deliberately:

1. verify signed task acceptance;
2. verify signed result acceptance;
3. run a locally denied capability and preserve the denial evidence;
4. stop worker-a before dispatch;
5. dispatch while it is offline and verify there is no result;
6. restart worker-a using the same state database and identity;
7. verify the missed task is consumed and reconciled;
8. restart the coordinator using the same state database;
9. verify accepted results remain present;
10. verify provenance;
11. confirm no worker contains the coordinator private key;
12. confirm no arbitrary shell capability is registered.

## 7. Signed evidence

Each host emits evidence locally:

```bash
python3 scripts/multi_host_evidence.py emit \
  --node-id worker-a \
  --private-key ./keys/worker-a.key \
  --host-instance '<stable-host-instance-id>' \
  --event task_signature_verified \
  --details-json '{}'
```

Append each JSON line to the final evidence file. Use distinct host-instance identifiers for coordinator, worker-a and worker-b.

Verify on the coordinator:

```bash
python3 scripts/multi_host_evidence.py verify \
  --trust-db ./state/trust.db \
  --authority-id coordinator \
  --authority-public '<COORDINATOR_PUBLIC>' \
  --evidence-jsonl ./multi-host-evidence.jsonl
```

A zero exit status means all required signed evidence is present. Some criteria are explicitly operator-attested because software cannot prove physical machine independence or absence of a copied secret by itself.

## Acceptance boundary

Do not label the physical proof passed from CI or simulated host IDs. Preserve the actual host logs and signed evidence JSONL as the acceptance artifact.
