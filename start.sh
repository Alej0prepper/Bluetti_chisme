#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -d .venv ]]; then python3 -m venv .venv; fi
.venv/bin/python -m pip install -e .
if [[ "${1:-}" == "--demo" ]]; then export BLUETTI_DEMO=1; else export BLUETTI_DEMO=0; fi
exec .venv/bin/python -m uvicorn explorer.app:app --host 127.0.0.1 --port 8765
