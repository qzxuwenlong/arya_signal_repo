from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .historical_metrics import compute_candle_metrics
from .config import use_coinank_enrichment
from .pool_selection import extract_social_tickers, select_okx_opportunity_pool

USER_AGENT = 'arya-signal-system/1.0 (Hermes)'


@dataclass
class SourceResult:
    status: str
    data: Any


def _request_json(url: str, *, method: str = 'GET', body: Optional[dict] = None, headers: Optional[dict] = None, timeout: int = 10) -> Any:
    h = {'User-Agent': USER_AGENT, 'Accept-Encoding': 'identity'}
    if headers:
        h.update(headers)
    data = None
    if body is not None:
        data = json.dumps(body).encode('utf-8')
        h['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode('utf-8', errors='replace')
    return json.loads(raw)


def fetch_okx_instruments(limit: int = 80) -> SourceResult:
    try:
        payload = _request_json('https://www.okx.com/api/v5/public/instruments?instType=SWAP', timeout=12)
        rows = payload.get('data') or []
        usdt = [r for r in rows if str(r.get('instId', '')).endswith('-USDT-SWAP') and r.get('state') == 'live']
        return SourceResult('ok', usdt[:limit])
    except Exception as e:
        return SourceResult(f'error:{type(e).__name__}', [])


def fetch_okx_tickers(inst_type: str = 'SWAP') -> SourceResult:
    try:
        payload = _request_json(f'https://www.okx.com/api/v5/market/tickers?instType={urllib.parse.quote(inst_type)}', timeout=12)
        rows = payload.get('data') or []
        usdt = [r for r in rows if str(r.get('instId', '')).endswith('-USDT-SWAP')]
        return SourceResult('ok', usdt)
    except Exception as e:
        return SourceResult(f'error:{type(e).__name__}', [])


def fetch_okx_ticker(inst_id: str) -> Dict[str, Any]:
    payload = _request_json(f'https://www.okx.com/api/v5/market/ticker?instId={urllib.parse.quote(inst_id)}', timeout=8)
    rows = payload.get('data') or []
    return rows[0] if rows else {}


def fetch_okx_candles(inst_id: str, bar: str = '1H', limit: int = 2) -> List[list]:
    payload = _request_json(f'https://www.okx.com/api/v5/market/candles?instId={urllib.parse.quote(inst_id)}&bar={bar}&limit={limit}', timeout=8)
    return payload.get('data') or []


def fetch_okx_books(inst_id: str, sz: int = 20) -> Dict[str, Any]:
    payload = _request_json(f'https://www.okx.com/api/v5/market/books?instId={urllib.parse.quote(inst_id)}&sz={sz}', timeout=8)
    rows = payload.get('data') or []
    return rows[0] if rows else {}


def fetch_okx_open_interest(inst_id: str) -> Dict[str, Any]:
    payload = _request_json(f'https://www.okx.com/api/v5/public/open-interest?instType=SWAP&instId={urllib.parse.quote(inst_id)}', timeout=8)
    rows = payload.get('data') or []
    return rows[0] if rows else {}


def fetch_okx_funding(inst_id: str) -> Dict[str, Any]:
    payload = _request_json(f'https://www.okx.com/api/v5/public/funding-rate?instId={urllib.parse.quote(inst_id)}', timeout=8)
    rows = payload.get('data') or []
    return rows[0] if rows else {}


def _f(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _depth_and_spread(book: Dict[str, Any]) -> Tuple[float, float]:
    bids = book.get('bids') or []
    asks = book.get('asks') or []
    if not bids or not asks:
        return 0.0, 999.0
    best_bid = _f(bids[0][0])
    best_ask = _f(asks[0][0])
    mid = (best_bid + best_ask) / 2 if best_bid and best_ask else 0
    spread_pct = ((best_ask - best_bid) / mid * 100) if mid else 999.0
    depth = 0.0
    for side in (bids, asks):
        for px, sz, *_ in side[:20]:
            depth += _f(px) * _f(sz)
    return depth, spread_pct


def build_okx_candidate_from_payloads(
    inst_id: str,
    ticker: Dict[str, Any],
    candles: List[list],
    book: Dict[str, Any],
    oi: Dict[str, Any],
    funding: Dict[str, Any],
    candles_4h: Optional[List[list]] = None,
    candles_1d: Optional[List[list]] = None,
) -> Dict[str, Any]:
    depth, spread = _depth_and_spread(book)

    price_change = _f(ticker.get('sodUtc8'))
    if _f(ticker.get('last')) and _f(ticker.get('open24h')):
        price_change = (_f(ticker.get('last')) - _f(ticker.get('open24h'))) / _f(ticker.get('open24h')) * 100

    volume_1h = 0.0
    volume_change = 0.0
    if candles:
        cur = candles[0]
        # OKX candle fields: ts,o,h,l,c,vol,volCcy,volCcyQuote,confirm.
        volume_1h = _f(cur[7] if len(cur) > 7 else (cur[6] if len(cur) > 6 else cur[5]))
    if len(candles) >= 2:
        cur_vol = volume_1h
        # Compare the latest hour with the average of the next few complete hours.
        prev_vals = []
        for prev in candles[1:7]:
            prev_vals.append(_f(prev[7] if len(prev) > 7 else (prev[6] if len(prev) > 6 else prev[5])))
        prev_vals = [v for v in prev_vals if v > 0]
        prev_vol = sum(prev_vals) / len(prev_vals) if prev_vals else 0.0
        if prev_vol:
            volume_change = (cur_vol - prev_vol) / prev_vol * 100

    candidate = {
        'symbol': inst_id,
        'inst_id': inst_id,
        'price': _f(ticker.get('last')),
        'price_change_1h_pct': price_change,
        'volume_1h': volume_1h,
        'volume_change_1h_pct': volume_change,
        'oi_change_1h_pct': 0.0,
        'funding_rate_pct': _f(funding.get('fundingRate')) * 100,
        'long_liq_1h_usd': 0.0,
        'short_liq_1h_usd': 0.0,
        'depth_usd': depth,
        'spread_pct': spread,
        'open_interest_usd': _f(oi.get('oiUsd')),
        'sources': ['okx'],
    }
    hist_metrics = compute_candle_metrics(candles, candles_4h or [], candles_1d or [])
    if hist_metrics:
        candidate.update(hist_metrics)
        candidate['price_change_1h_pct'] = hist_metrics.get('return_1h_pct', candidate['price_change_1h_pct'])
        candidate['volume_1h'] = hist_metrics.get('volume_usd_1h', candidate['volume_1h'])
        candidate['volume_change_1h_pct'] = hist_metrics.get('volume_1h_vs_24h_avg_pct', candidate['volume_change_1h_pct'])
        candidate['sources'].append('okx_historical_candles')
    return candidate


def build_okx_candidate(inst_id: str) -> Dict[str, Any]:
    ticker = fetch_okx_ticker(inst_id)
    candles = fetch_okx_candles(inst_id, bar='1H', limit=24)
    candles_4h = fetch_okx_candles(inst_id, bar='4H', limit=12)
    candles_1d = fetch_okx_candles(inst_id, bar='1D', limit=7)
    book = fetch_okx_books(inst_id)
    oi = fetch_okx_open_interest(inst_id)
    funding = fetch_okx_funding(inst_id)
    return build_okx_candidate_from_payloads(inst_id, ticker, candles, book, oi, funding, candles_4h, candles_1d)


def fetch_binance_rank(chain_id: str = '56', size: int = 30) -> SourceResult:
    try:
        body = {'rankType': 10, 'chainId': chain_id, 'period': 50, 'sortBy': 70, 'orderAsc': False, 'page': 1, 'size': size}
        payload = _request_json('https://web3.binance.com/bapi/defi/v1/public/wallet-direct/buw/wallet/market/token/pulse/unified/rank/list/ai', method='POST', body=body, timeout=12)
        data = payload.get('data') or []
        if isinstance(data, dict):
            data = data.get('list') or data.get('data') or []
        return SourceResult('ok', data)
    except Exception as e:
        return SourceResult(f'error:{type(e).__name__}', [])


def binance_rank_map(rows: List[dict]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for idx, r in enumerate(rows, 1):
        sym = str(r.get('symbol') or r.get('tokenSymbol') or r.get('baseAsset') or '').upper()
        if sym:
            out[sym] = {'binance_hype_rank': idx, 'binance_raw': r}
    return out


def coinank_status() -> SourceResult:
    if not use_coinank_enrichment():
        return SourceResult('disabled_by_config', {})
    if not os.getenv('COINANK_API_KEY') and not os.getenv('COINANK_APIKEY'):
        return SourceResult('missing_key', {})
    return SourceResult('configured_not_called_v1', {})


from .config import VAULT_PATH


def load_knowledge_summary(vault_path: str = VAULT_PATH) -> Dict[str, Any]:
    base = os.path.join(vault_path, 'traders', 'Arya_web3')
    files = ['theory.md', 'framework.md', 'sources.md']
    summary: Dict[str, Any] = {'path': base, 'available': False, 'files': []}
    if os.path.isdir(base):
        summary['available'] = True
        for fn in files:
            p = os.path.join(base, fn)
            if os.path.exists(p):
                summary['files'].append(p)
    return summary
