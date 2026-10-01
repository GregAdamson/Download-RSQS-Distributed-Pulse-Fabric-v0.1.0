#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 -m pip install -e .
python3 scripts/demo.py
python3 scripts/demo_v02.py
python3 scripts/http_transport_demo.py
python3 scripts/runtime_demo.py
python3 scripts/distributed_process_demo.py
python3 scripts/cognitive_substrate_demo.py
python3 scripts/hardening_demo.py
python3 scripts/reconciliation_demo.py
python3 -m unittest discover -s tests -v
