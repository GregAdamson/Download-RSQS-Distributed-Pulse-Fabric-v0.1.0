# Multi-host proof

The canonical physical multi-host procedure is now:

```text
docs/V09_MULTI_HOST_RUNBOOK.md
```

The v0.9 repository includes:

- durable pulse transport;
- optional TLS transport contexts;
- signed node grants with expiry/revocation/key rotation;
- signed capability advertisements;
- trust-bound coordinator dispatch;
- hardened worker process;
- signed multi-host evidence generation and verification;
- CI-level multi-host harness tests.

## Acceptance boundary

`MULTI_HOST_HARNESS_PROOF=PASS` proves the verifier and simulated evidence workflow, not physical machine independence.

The physical proof is complete only after the steps in `V09_MULTI_HOST_RUNBOOK.md` are performed on three distinct enrolled hosts and the resulting signed host evidence passes the verifier. Preserve those host logs and the signed evidence JSONL as the acceptance artifact.

No Internet scanning, self-enrolment, credential copying or arbitrary shell capability is part of this proof.
