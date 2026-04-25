from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import time
from typing import Any, Dict, List

from .data_sources import (
    SourceResult,
    binance_rank_map,
    build_okx_candidate,
    coinank_status,
    fetch_binance_rank,
    fetch_okx_instruments,
    load_knowledge_summary,
)
from .report import render_markdown_report
from .scoring import normalize_symbol, score_candidate
from .fuel_metrics import enrich_candidate_with_local_history
from .market_store import MarketStore
from .config import MARKET_STATE_DB, ORDER_EXECUTION_ENABLED, PROXY_URL

DEFAULT_WATCHLIST = ['BTC-USDT-SWAP', 'ETH-USDT-SWAP', 'SOL-USDT-SWAP', 'DOGE-USDT-SWAP', 'WIF-USDT-SWAP', 'PEPE-USDT-SWAP', 'BOME-USDT-SWAP', 'ORDI-USDT-SWAP']


def ensure_proxy_env() -> None:
    if PROXY_URL:
        import os
        os.environ.setdefault('HTTP_PROXY', PROXY_URL)
        os.environ.setdefault('HTTPS_PROXY', PROXY_URL)
        os.environ.setdefault('http_proxy', PROXY_URL)
        os.environ.setdefault('https_proxy', PROXY_URL)


def merge_binance_signal(candidate: Dict[str, Any], rank_lookup: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    sym = normalize_symbol(candidate.get('symbol', ''))
    if sym in rank_lookup:
        candidate.update({k: v for k, v in rank_lookup[sym].items() if k != 'binance_raw'})
        candidate.setdefault('sources', []).append('binance_web3')
    return candidate


def run_scan(limit: int = 8, use_live: bool = True) -> Dict[str, Any]:
    if use_live:
        ensure_proxy_env()
    source_status: Dict[str, str] = {}
    source_status['order_execution'] = 'disabled' if not ORDER_EXECUTION_ENABLED else 'enabled'
    knowledge = load_knowledge_summary()
    source_status['knowledge_base'] = 'ok' if knowledge.get('available') else 'missing'

    coinank = coinank_status()
    source_status['coinank'] = coinank.status
    source_status['local_market_db'] = str(MARKET_STATE_DB)
    now_ts = int(time())
    market_store = MarketStore(MARKET_STATE_DB) if use_live else None
    binance = fetch_binance_rank(size=50) if use_live else SourceResult('disabled', [])
    source_status['binance_web3'] = binance.status
    rank_lookup = binance_rank_map(binance.data if isinstance(binance.data, list) else [])

    inst_result = fetch_okx_instruments(limit=120) if use_live else SourceResult('disabled', [])
    source_status['okx'] = inst_result.status

    watchlist = list(DEFAULT_WATCHLIST)
    if inst_result.data:
        live_ids = {r.get('instId') for r in inst_result.data}
        watchlist = [x for x in watchlist if x in live_ids]
        for r in inst_result.data:
            inst_id = r.get('instId')
            if inst_id and inst_id not in watchlist and len(watchlist) < limit:
                watchlist.append(inst_id)
    watchlist = watchlist[:limit]

    raw_candidates: List[Dict[str, Any]] = []
    for inst_id in watchlist:
        try:
            c = build_okx_candidate(inst_id) if use_live else {'symbol': inst_id}
            c = merge_binance_signal(c, rank_lookup)
            if market_store is not None and 'error' not in c:
                c = enrich_candidate_with_local_history(c, store=market_store, now_ts=now_ts, exchange='okx')
                c.setdefault('sources', []).append('local_market_db')
            raw_candidates.append(c)
        except Exception as e:
            raw_candidates.append({'symbol': inst_id, 'error': f'{type(e).__name__}: {e}'})

    scored = [score_candidate(c) for c in raw_candidates]
    report = render_markdown_report(scored, source_status=source_status)
    return {'source_status': source_status, 'knowledge': knowledge, 'candidates': scored, 'report': report}


def main() -> None:
    ap = argparse.ArgumentParser(description='Arya knowledge-base driven hot coin scanner V1. No order execution.')
    ap.add_argument('--limit', type=int, default=8)
    ap.add_argument('--offline', action='store_true', help='disable network calls')
    ap.add_argument('--json-out', default='runs/latest.json')
    ap.add_argument('--md-out', default='runs/latest.md')
    args = ap.parse_args()

    result = run_scan(limit=args.limit, use_live=not args.offline)
    json_path = Path(args.json_out)
    md_path = Path(args.md_out)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    md_path.write_text(result['report'], encoding='utf-8')
    print(result['report'])
    print(f'\nJSON: {json_path}')
    print(f'MD: {md_path}')
    print('ORDER_EXECUTION: DISABLED')


if __name__ == '__main__':
    main()
