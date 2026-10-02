# v0.10 Reality Operations

The v0.10 reality layer operates only on explicitly configured sources. It does not discover hosts or scan networks.

## 1. Start the runtime

Set a write token in the environment:

```bash
export RSQS_REALITY_WRITE_TOKEN='replace-with-a-long-random-value'
```

Start a local runtime:

```bash
rsqs-fabricd \
  --node-id reality-node \
  --state ./state/reality.db \
  --host 127.0.0.1 \
  --port 8787 \
  --reality
```

For network exposure, configure `--cert` and `--key` and use a CA-validated client.

## 2. Configure sources

Copy:

```text
examples/reality_sources.example.json
```

to a local configuration file. Replace example URLs, schemas and environment-variable names with the actual authorised data sources.

Credentials should be supplied through `header_env`, not committed to the configuration file.

## 3. One-shot ingestion

```bash
python3 scripts/reality_ingest.py \
  --config ./reality-sources.json \
  --runtime-url http://127.0.0.1:8787
```

Use `--dry-run` to validate fetching and normalization without posting observations.

## 4. Continuous collector

```bash
python3 scripts/reality_collector.py \
  --config ./reality-sources.json \
  --collector-state ./state/collector.db \
  --runtime-url http://127.0.0.1:8787
```

The collector persists source scheduling state. Failed sources use bounded exponential backoff and successful sources return to their configured interval.

Use `--once` for cron, launchd, systemd timers or manual acceptance tests.

## 5. Inspect state

```bash
curl http://127.0.0.1:8787/reality/status
curl http://127.0.0.1:8787/reality/needs
curl 'http://127.0.0.1:8787/reality/twin?asset_id=<asset-id>'
curl http://127.0.0.1:8787/state
curl http://127.0.0.1:8787/observability
```

## Acceptance boundary

A feed is operational only after its actual endpoint/schema/credentials have been configured and an observation from that source is visible in the reality store/twin.

The repository CI verifies the adapter, fusion, persistence, API, collector scheduling, information-need and active-acquisition mechanisms using local test feeds. It does not claim connectivity to any unconfigured external service.
