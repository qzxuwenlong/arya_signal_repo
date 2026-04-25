from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

ACTIONABLE_STATES = {'SQUEEZE_ACTIVE', 'TREND_ALERT'}
SEVERE_EXIT_RISK_KEYWORDS = ('资金费率极端', '收网风险', '熔断', '退出')


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == '':
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _has_severe_exit_risk(candidate: Dict[str, Any]) -> bool:
    if candidate.get('state') != 'EXIT_RISK':
        return False
    if abs(_num(candidate.get('funding_rate_pct'))) >= 0.10:
        return True
    risks = ' '.join(str(x) for x in candidate.get('risks') or [])
    return any(k in risks for k in SEVERE_EXIT_RISK_KEYWORDS)


def select_alert_candidates(candidates: Iterable[Dict[str, Any]], *, min_score: int = 50, include_severe_exit: bool = True) -> List[Dict[str, Any]]:
    selected: List[Dict[str, Any]] = []
    for c in candidates:
        state = c.get('state')
        score = _num(c.get('score'))
        history_ready = c.get('local_history_ready', True)
        if state in ACTIONABLE_STATES and score >= min_score and history_ready:
            selected.append(dict(c))
        elif include_severe_exit and _has_severe_exit_risk(c):
            selected.append(dict(c))
    return sorted(selected, key=lambda x: (_num(x.get('score')), abs(_num(x.get('funding_rate_pct')))), reverse=True)


def build_advisory_message(candidates: Iterable[Dict[str, Any]], *, source_status: Dict[str, str] | None = None, title: str = 'Arya 交易建议提醒') -> str:
    source_status = source_status or {}
    rows = list(candidates)
    lines: List[str] = []
    lines.append(f'## {title}')
    lines.append(f'时间：{datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")}')
    lines.append('原则：只做提醒和建议，**不自动下单**；任何交易必须**人工确认**。')
    lines.append(f'ORDER_EXECUTION: {source_status.get("order_execution", "unknown")}')
    lines.append('')
    if not rows:
        lines.append('当前无需要推送的高价值信号。')
        return '\n'.join(lines)

    for i, c in enumerate(rows, 1):
        lines.append(f'{i}. {c.get("symbol", "UNKNOWN")}｜{c.get("state", "WATCH_ONLY")}｜{int(_num(c.get("score")))}分')
        lines.append(f'- 方向：{c.get("direction", "待确认")}')
        lines.append(f'- 策略：{c.get("strategy", "只观察")}')
        lines.append(
            f'- 燃料：OI 1h {_num(c.get("oi_change_1h_pct")):.2f}%｜量 1h {_num(c.get("volume_change_1h_pct")):.2f}%｜价 1h {_num(c.get("price_change_1h_pct")):.2f}%'
        )
        reasons = c.get('reasons') or []
        risks = c.get('risks') or []
        if reasons:
            lines.append('- 证据：' + '；'.join(str(x) for x in reasons[:3]))
        if risks:
            lines.append('- 风险：' + '；'.join(str(x) for x in risks[:3]))
        lines.append('- 执行：等待人工确认，不自动下单。')
        lines.append('')
    return '\n'.join(lines).strip()


def load_scan(path: str | Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding='utf-8'))


def build_from_scan(scan: Dict[str, Any], *, min_score: int = 50, include_severe_exit: bool = True) -> Dict[str, Any]:
    selected = select_alert_candidates(scan.get('candidates') or [], min_score=min_score, include_severe_exit=include_severe_exit)
    message = build_advisory_message(selected, source_status=scan.get('source_status') or {})
    return {'selected': selected, 'message': message, 'should_notify': bool(selected)}


def main() -> None:
    ap = argparse.ArgumentParser(description='Build safe Telegram advisory from Arya scan JSON. No order execution.')
    ap.add_argument('--scan-json', default='runs/latest.json')
    ap.add_argument('--out', default='runs/latest_advisory.md')
    ap.add_argument('--min-score', type=int, default=50)
    ap.add_argument('--include-severe-exit', action='store_true')
    ap.add_argument('--print-empty', action='store_true')
    args = ap.parse_args()

    scan = load_scan(args.scan_json)
    result = build_from_scan(scan, min_score=args.min_score, include_severe_exit=args.include_severe_exit)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(result['message'], encoding='utf-8')
    if result['should_notify'] or args.print_empty:
        print(result['message'])


if __name__ == '__main__':
    main()
