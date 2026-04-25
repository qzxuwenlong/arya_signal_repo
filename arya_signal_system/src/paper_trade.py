from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set, Tuple

PAPER_OBSERVATION_STATES = {'EARLY_DEMON_TREND', 'SECTOR_LAGGARD_OBSERVE'}

PAPER_ACTIONABLE_STATES = {
    'LONG_SQUEEZE',
    'LONG_PULLBACK',
    'SHORT_BREAKDOWN',
    'SHORT_ALERT',
    'TREND_ALERT',
    'FLASH_CRASH_SHORT',
}
LONG_STATES = {'LONG_SQUEEZE', 'LONG_PULLBACK', 'SQUEEZE_ACTIVE', 'TREND_ALERT'}
SHORT_STATES = {'SHORT_BREAKDOWN', 'SHORT_ALERT', 'FLASH_CRASH_SHORT'}
NO_ENTRY_STATES = {'EXIT_RISK', 'NO_TRADE_FAKE_OI', 'SHORT_TAIL_RISK', 'NO_CHASE_NEGATIVE_FUNDING', 'NO_CHASE_GUILLOTINE', 'NO_TRADE_UNFAIR_GAME'}


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == '':
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _side_for_state(candidate: Dict[str, Any]) -> str | None:
    state = str(candidate.get('state') or '')
    direction = str(candidate.get('direction') or '')
    strategy = str(candidate.get('strategy') or '')
    if state in SHORT_STATES or '空' in direction or '做空' in strategy:
        return 'short'
    if state in PAPER_OBSERVATION_STATES and ('偏多' in direction or '多' in strategy or state == 'EARLY_DEMON_TREND'):
        return 'long'
    if state in LONG_STATES or '多' in direction or '做多' in strategy:
        return 'long'
    return None


def _risk_pct(candidate: Dict[str, Any]) -> float:
    atr = abs(_num(candidate.get('atr_1h_pct')))
    # Paper-mode conservative stop distance. Bound noisy ATR so small caps do not
    # create absurd paper plans. This is only for tracking, not order placement.
    if atr > 0:
        return min(max(atr * 1.2, 2.0), 12.0)
    return 4.0


def _trade_plan(entry: float, side: str, risk_pct: float) -> Dict[str, float]:
    r = risk_pct / 100.0
    if side == 'short':
        return {
            'stop_price': entry * (1 + r),
            'take_profit_1_price': entry * (1 - r),
            'take_profit_2_price': entry * (1 - 2 * r),
        }
    return {
        'stop_price': entry * (1 - r),
        'take_profit_1_price': entry * (1 + r),
        'take_profit_2_price': entry * (1 + 2 * r),
    }


def build_paper_trade_rows(scan: Dict[str, Any], *, now_ts: int | None = None, min_score: int = 50) -> List[Dict[str, Any]]:
    now_ts = int(time.time()) if now_ts is None else int(now_ts)
    source_status = scan.get('source_status') or {}
    rows: List[Dict[str, Any]] = []
    for c in scan.get('candidates') or []:
        state = str(c.get('state') or '')
        score = int(_num(c.get('score')))
        history_ready = c.get('local_history_ready', True)
        entry = _num(c.get('last_price') or c.get('price'))
        side = _side_for_state(c)
        observation_tier = str(c.get('paper_observation_tier') or 'none')
        is_observation = state in PAPER_OBSERVATION_STATES and observation_tier == 'observe'
        if state in NO_ENTRY_STATES:
            continue
        if state not in PAPER_ACTIONABLE_STATES and not is_observation:
            continue
        if score < min_score or not history_ready or entry <= 0 or side is None:
            continue
        risk_pct = _risk_pct(c)
        plan = _trade_plan(entry, side, risk_pct)
        symbol = str(c.get('symbol') or 'UNKNOWN').upper()
        row: Dict[str, Any] = {
            'trade_id': f'{now_ts}-{symbol}-{state}-observe' if is_observation else f'{now_ts}-{symbol}-{state}',
            'mode': 'paper_observation' if is_observation else 'paper',
            'status': 'open',
            'created_ts': now_ts,
            'created_at_utc': time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(now_ts)),
            'symbol': symbol,
            'side': side,
            'state': state,
            'model': c.get('model'),
            'direction': c.get('direction'),
            'strategy': c.get('strategy'),
            'score': score,
            'entry_ref_price': entry,
            'risk_pct': risk_pct,
            'stop_price': plan['stop_price'],
            'take_profit_1_price': plan['take_profit_1_price'],
            'take_profit_2_price': plan['take_profit_2_price'],
            'funding_rate_pct': _num(c.get('funding_rate_pct')),
            'price_change_1h_pct': _num(c.get('price_change_1h_pct')),
            'volume_change_1h_pct': _num(c.get('volume_change_1h_pct')),
            'oi_change_1h_pct': _num(c.get('oi_change_1h_pct')),
            'atr_1h_pct': _num(c.get('atr_1h_pct')),
            'counterparty_fuel_score': _num(c.get('counterparty_fuel_score')),
            'counterparty_fuel_direction': c.get('counterparty_fuel_direction'),
            'fair_game': c.get('fair_game'),
            'fair_game_score': _num(c.get('fair_game_score')),
            'flash_crash_short': bool(c.get('flash_crash_short')),
            'paper_observation_tier': observation_tier,
            'anti_consensus_score': _num(c.get('anti_consensus_score')),
            'anti_consensus_direction': c.get('anti_consensus_direction'),
            'early_demon_trend_score': _num(c.get('early_demon_trend_score')),
            'sector_filter': c.get('sector_filter'),
            'thesis_invalidation': c.get('thesis_invalidation') or [],
            'local_history_ready': bool(history_ready),
            'order_execution': source_status.get('order_execution', 'disabled'),
            'notes': 'paper only; no API order; manual confirmation required for any real trade',
            'result_1h_pct': None,
            'result_4h_pct': None,
            'result_24h_pct': None,
            'max_favorable_pct': None,
            'max_adverse_pct': None,
            'closed_ts': None,
            'close_reason': None,
        }
        rows.append(row)
    return rows


def _load_existing_open_keys(ledger_path: Path) -> Set[Tuple[str, str, str]]:
    keys: Set[Tuple[str, str, str]] = set()
    if not ledger_path.exists():
        return keys
    for line in ledger_path.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get('status') == 'open':
            keys.add((str(row.get('symbol')), str(row.get('side')), str(row.get('state'))))
    return keys


def append_paper_trades_from_scan(scan_path: str | Path, ledger_path: str | Path, *, now_ts: int | None = None, min_score: int = 50) -> Dict[str, Any]:
    scan_path = Path(scan_path)
    ledger_path = Path(ledger_path)
    scan = json.loads(scan_path.read_text(encoding='utf-8'))
    rows = build_paper_trade_rows(scan, now_ts=now_ts, min_score=min_score)
    existing = _load_existing_open_keys(ledger_path)
    to_append = []
    for row in rows:
        key = (str(row.get('symbol')), str(row.get('side')), str(row.get('state')))
        if key in existing:
            continue
        existing.add(key)
        to_append.append(row)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    if to_append:
        with ledger_path.open('a', encoding='utf-8') as f:
            for row in to_append:
                f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n')
    return {'appended': len(to_append), 'candidates': len(rows), 'ledger': str(ledger_path)}


def main() -> None:
    ap = argparse.ArgumentParser(description='Append Arya paper-trade records from scan JSON. No order execution.')
    ap.add_argument('--scan-json', default='runs/latest.json')
    ap.add_argument('--ledger', default='runs/paper_trades.jsonl')
    ap.add_argument('--min-score', type=int, default=50)
    args = ap.parse_args()
    result = append_paper_trades_from_scan(args.scan_json, args.ledger, min_score=args.min_score)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    print('ORDER_EXECUTION: DISABLED')


if __name__ == '__main__':
    main()
