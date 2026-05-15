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
)
from .pool_selection import extract_social_tickers, select_okx_opportunity_pool
from .coinank_client import coinank_enabled, enrich_candidate_with_coinank
from .report import render_markdown_report
from .scoring import normalize_symbol, score_candidate
from .fuel_metrics import enrich_candidate_with_local_history
from .market_store import MarketStore
from .config import MARKET_STATE_DB, ORDER_EXECUTION_ENABLED, PROXY_URL, use_coinank_enrichment
from .onchainos_source import collect_onchain_candidates, onchain_lookup_from_pool, write_onchain_candidates

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


def run_scan(limit: int = 8, use_live: bool = True, include_onchain: bool = False, onchain_pool: Dict[str, Any] | None = None, onchain_out: str | Path = 'runs/onchainos_candidates.json', onchain_pool_extra: int = 0, social_posts: List[Dict[str, Any]] | None = None, social_pool_extra: int = 0) -> Dict[str, Any]:
    if use_live:
        ensure_proxy_env()
    source_status: Dict[str, str] = {}
    source_status['order_execution'] = 'disabled' if not ORDER_EXECUTION_ENABLED else 'enabled'
    knowledge = load_knowledge_summary()
    source_status['knowledge_base'] = 'ok' if knowledge.get('available') else 'missing'

    coinank = coinank_status()
    source_status['coinank'] = coinank.status
    coinank_enrichment_enabled = bool(use_live and use_coinank_enrichment() and coinank_enabled())
    source_status['coinank_enrichment'] = 'enabled' if coinank_enrichment_enabled else coinank.status
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
    live_symbols = {
        str(r.get('instId', '')).replace('-USDT-SWAP', '')
        for r in (inst_result.data if isinstance(inst_result.data, list) else [])
        if str(r.get('instId', '')).endswith('-USDT-SWAP')
    }
    if include_onchain:
        try:
            onchain_pool = onchain_pool or collect_onchain_candidates()
            write_onchain_candidates(onchain_pool, onchain_out)
            source_status['onchainos'] = (onchain_pool.get('source_status') or {}).get('onchainos', 'ok')
        except Exception as e:
            onchain_pool = {
                'source': 'okx_onchainos',
                'source_status': {'onchainos': f'error:{type(e).__name__}'},
                'order_execution_enabled': False,
                'candidates': [],
                'errors': [f'{type(e).__name__}: {e}'],
            }
            source_status['onchainos'] = onchain_pool['source_status']['onchainos']
    else:
        onchain_pool = None
    onchain_lookup = onchain_lookup_from_pool(onchain_pool, allowed_symbols=live_symbols or None) if onchain_pool else {}
    if onchain_lookup:
        source_status['onchain_okx_boost'] = f'{len(onchain_lookup)}_listed_symbols'
    social_lookup = extract_social_tickers(
        social_posts or [],
        symbol_aliases={'HYPER': 'HYPE'},
        allowed_symbols=live_symbols or None,
    )
    if social_posts is not None:
        source_status['social_x'] = f'provided_{len(social_posts)}_posts_{len(social_lookup)}_symbols'

    if use_live and ticker_result.data:
        opportunity_pool = select_okx_opportunity_pool(
            inst_result.data if isinstance(inst_result.data, list) else [],
            ticker_result.data,
            rank_lookup=rank_lookup,
            social_lookup=social_lookup,
            onchain_lookup=onchain_lookup,
            limit=limit + max(0, int(social_pool_extra or 0)) + max(0, int(onchain_pool_extra or 0)),
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
            sym = normalize_symbol(c.get('symbol', inst_id))
            if sym in social_lookup:
                c.update({k: v for k, v in social_lookup[sym].items() if k.startswith('social_')})
                c.setdefault('sources', []).append('social_x')
            if sym in onchain_lookup:
                c.update({k: v for k, v in onchain_lookup[sym].items() if k.startswith('onchain_')})
                c.setdefault('sources', []).append('okx_onchainos')
            if coinank_enrichment_enabled and 'error' not in c:
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
    report = render_markdown_report(scored, source_status=source_status, onchain_observation_pool=onchain_pool)
    result = {'source_status': source_status, 'knowledge': knowledge, 'candidates': scored, 'report': report}
    if onchain_pool is not None:
        result['onchain_observation_pool'] = onchain_pool
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description='Arya knowledge-base driven hot coin scanner V1. No order execution.')
    ap.add_argument('--limit', type=int, default=8)
    ap.add_argument('--offline', action='store_true', help='disable network calls')
    ap.add_argument('--include-onchain', action='store_true', help='attach OKX OnchainOS C-tier observation pool; never enables trading')
    ap.add_argument('--onchain-pool-extra', type=int, default=0, help='reserve extra OKX deep-scan slots for OnchainOS-listed candidates; observation only')
    ap.add_argument('--social-pool-extra', type=int, default=0, help='reserve extra OKX deep-scan slots for externally supplied social/KOL candidates')
    ap.add_argument('--onchain-out', default='runs/onchainos_candidates.json')
    ap.add_argument('--json-out', default='runs/latest.json')
    ap.add_argument('--md-out', default='runs/latest.md')
    args = ap.parse_args()

    result = run_scan(limit=args.limit, use_live=not args.offline, include_onchain=args.include_onchain, onchain_out=args.onchain_out, onchain_pool_extra=args.onchain_pool_extra, social_pool_extra=args.social_pool_extra)
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
