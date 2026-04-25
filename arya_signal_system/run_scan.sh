#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export HTTP_PROXY="${HTTP_PROXY:-http://127.0.0.1:7897}"
export HTTPS_PROXY="${HTTPS_PROXY:-http://127.0.0.1:7897}"
python3 -m src.scanner "$@"
