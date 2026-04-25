#!/usr/bin/env bash
set -euo pipefail

export HTTP_PROXY="${HTTP_PROXY:-http://127.0.0.1:7897}"
export HTTPS_PROXY="${HTTPS_PROXY:-http://127.0.0.1:7897}"
export http_proxy="$HTTP_PROXY"
export https_proxy="$HTTPS_PROXY"

mkdir -p /home/hpp/logs
python3 /home/hpp/okx_extreme_funding_radar.py \
  --min-abs-funding-pct "${FUNDING_MIN_ABS_PCT:-0.05}" \
  --top-n "${FUNDING_ALERT_TOP_N:-12}" \
  --max-prefetch "${FUNDING_MAX_PREFETCH:-80}" \
  --json-out /home/hpp/extreme_funding_latest.json \
  --md-out /home/hpp/extreme_funding_latest.md
