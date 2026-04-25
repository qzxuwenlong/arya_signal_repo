#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export HTTP_PROXY="${HTTP_PROXY:-http://127.0.0.1:7897}"
export HTTPS_PROXY="${HTTPS_PROXY:-http://127.0.0.1:7897}"
python3 -m src.scanner --limit "${1:-8}" >/tmp/arya_scan_notify_latest.out
python3 -m src.advisory --scan-json runs/latest.json --out runs/latest_advisory.md --min-score "${ARYA_ALERT_MIN_SCORE:-50}" --include-severe-exit
