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
    fetch_okx_tickers,
    load_knowledge_summary,
    select_okx_opportunity_pool,
)
from .coinank_client import coinank_enabled, enrich_candidate_with_coinank
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
    source_status['coinank_enrichment'] = 'enabled' if use_live and coinank_enabled() else ('missing_key' if use_live else 'disabled')
    source_status['local_market_db'] = str(MARKET_STATE_DB)
    now_ts = int(time())
    market_store = MarketStore(MARKET_STATE_DB) if use_live else None
    binance = fetch_binance_rank(size=50) if use_live else SourceResult('disabled', [])
    source_status['binance_web3'] = binance.status
    rank_lookup = binance_rank_map(binance.data if isinstance(binance.data, list) else [])

    inst_result = fetch_okx_instruments(limit=1000) if use_live else SourceResult('disabled', [])
    source_status['okx'] = inst_result.status
    ticker_result = fetch_okx_tickers() if use_live else SourceResult('disabled', [])
    source_status['okx_tickers'] = ticker_result.status

    if use_live and ticker_result.data:
        opportunity_pool = select_okx_opportunity_pool(
            inst_result.data if isinstance(inst_result.data, list) else [],
            ticker_result.data,
            rank_lookup=rank_lookup,
            limit=limit,
        )
        watchlist = [x['inst_id'] for x in opportunity_pool]
        source_status['okx_selection'] = f'dynamic_top_{len(watchlist)}'
    else:
        opportunity_pool = []
        watchlist = list(DEFAULT_WATCHLIST)[:limit]
        source_status['okx_selection'] = 'offline_default_watchlist' if not use_live else 'fallback_default_watchlist'

    selection_by_id = {x['inst_id']: x for x in opportunity_pool}

    raw_candidates: List[Dict[str, Any]] = []
    for inst_id in watchlist:
        try:
            c = build_okx_candidate(inst_id) if use_live else {'symbol': inst_id}
            if inst_id in selection_by_id:
                c.update({k: v for k, v in selection_by_id[inst_id].items() if k not in {'symbol'}})
            c = merge_binance_signal(c, rank_lookup)
            if use_live and coinank_enabled() and 'error' not in c:
                c = enrich_candidate_with_coinank(c)
            if market_store is not None and 'error' not in c:
                exchange_metrics = {
                    'price_change_1h_pct': c.get('price_change_1h_pct', 0.0),
                    'volume_change_1h_pct': c.get('volume_change_1h_pct', 0.0),
                }
                c = enrich_candidate_with_local_history(c, store=market_store, now_ts=now_ts, exchange='okx')
                if not c.get('local_history_ready'):
                    c.update(exchange_metrics)
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
