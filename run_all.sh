#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 -m pip install -e .
python3 scripts/demo.py
python3 scripts/demo_v02.py
python3 -m unittest discover -s tests -v
