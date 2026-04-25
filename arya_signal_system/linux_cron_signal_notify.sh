#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/home/hpp/xm/arya_signal_system"
cd "$PROJECT_DIR"

export HTTP_PROXY="${HTTP_PROXY:-http://127.0.0.1:7897}"
export HTTPS_PROXY="${HTTPS_PROXY:-http://127.0.0.1:7897}"
export ARYA_ALERT_MIN_SCORE="${ARYA_ALERT_MIN_SCORE:-50}"

mkdir -p runs logs

LOCK_FILE="/tmp/arya_signal_scan_notify.lock"
LOG_FILE="$PROJECT_DIR/logs/linux_cron_signal_notify.log"
SCAN_STDOUT="$PROJECT_DIR/logs/latest_linux_cron_scan.out"
ADVISORY_STDOUT="$PROJECT_DIR/logs/latest_linux_cron_advisory.out"
PAPER_STDOUT="$PROJECT_DIR/logs/latest_linux_cron_paper.out"
ADVISORY_FILE="$PROJECT_DIR/runs/latest_advisory.md"
PAPER_LEDGER="$PROJECT_DIR/runs/paper_trades.jsonl"
LAST_SENT_HASH_FILE="$PROJECT_DIR/runs/.last_sent_advisory.sha256"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  printf '%s SKIP already running\n' "$(date -Is)" >> "$LOG_FILE"
  exit 0
fi

printf '%s START scan limit=%s min_score=%s\n' "$(date -Is)" "${1:-8}" "$ARYA_ALERT_MIN_SCORE" >> "$LOG_FILE"

python3 -m src.scanner --limit "${1:-8}" >"$SCAN_STDOUT" 2>&1
python3 -m src.paper_trade \
  --scan-json runs/latest.json \
  --ledger "$PAPER_LEDGER" \
  --min-score "$ARYA_ALERT_MIN_SCORE" \
  >"$PAPER_STDOUT" 2>&1
python3 -m src.advisory \
  --scan-json runs/latest.json \
  --out "$ADVISORY_FILE" \
  --min-score "$ARYA_ALERT_MIN_SCORE" \
  --include-severe-exit \
  >"$ADVISORY_STDOUT" 2>&1

if [[ ! -s "$ADVISORY_STDOUT" ]]; then
  printf '%s OK no_signal\n' "$(date -Is)" >> "$LOG_FILE"
  exit 0
fi

CURRENT_HASH="$(sha256sum "$ADVISORY_STDOUT" | awk '{print $1}')"
LAST_HASH=""
if [[ -f "$LAST_SENT_HASH_FILE" ]]; then
  LAST_HASH="$(cat "$LAST_SENT_HASH_FILE" 2>/dev/null || true)"
fi

if [[ "$CURRENT_HASH" == "$LAST_HASH" ]]; then
  printf '%s OK duplicate_signal hash=%s\n' "$(date -Is)" "$CURRENT_HASH" >> "$LOG_FILE"
  exit 0
fi

PROMPT_FILE="$(mktemp /tmp/arya_hermes_signal_prompt.XXXXXX.md)"
cleanup() {
  rm -f "$PROMPT_FILE"
}
trap cleanup EXIT

cat >"$PROMPT_FILE" <<'PROMPT_HEADER'
你是 Arya Signal System 的 Telegram 安全提醒器。

下面是本机 Linux cron/shell 已经完成扫描后生成的高价值信号文本。请不要重新扫描、不要调用交易接口、不要下单，只做两件事：
1. 用中文把信号压缩成适合 Telegram 的短提醒；
2. 明确写出“仅供分析，不自动下单，任何交易必须人工确认”。

原始信号如下：
PROMPT_HEADER
cat "$ADVISORY_STDOUT" >> "$PROMPT_FILE"

if /home/hpp/.local/bin/hermes chat -Q --source tool --max-turns 3 --ignore-rules -t telegram -q "$(cat "$PROMPT_FILE")" >> "$LOG_FILE" 2>&1; then
  printf '%s' "$CURRENT_HASH" > "$LAST_SENT_HASH_FILE"
  printf '%s OK notified hash=%s\n' "$(date -Is)" "$CURRENT_HASH" >> "$LOG_FILE"
else
  printf '%s ERROR hermes_notify_failed hash=%s\n' "$(date -Is)" "$CURRENT_HASH" >> "$LOG_FILE"
  exit 1
fi
