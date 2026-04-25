from __future__ import annotations

import os
import time
import urllib.parse
from typing import Any, Dict, List, Optional

from .data_sources import SourceResult, _f, _request_json
from .scoring import normalize_symbol

COINANK_BASE_URL = 'https://open-api.coinank.com'
COINANK_TIMEOUT_SEC = 10


def _api_key() -> str:
    return os.getenv('COINANK_API_KEY') or os.getenv('COINANK_APIKEY') or ''


def coinank_enabled() -> bool:
    return bool(_api_key())


def _now_ms() -> int:
    return int(time.time() * 1000)


def _get(path: str, params: Optional[Dict[str, Any]] = None, timeout: int = COINANK_TIMEOUT_SEC) -> Any:
    key = _api_key()
    if not key:
        raise RuntimeError('missing_coinank_api_key')
    qs = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None})
    url = f'{COINANK_BASE_URL}{path}' + (f'?{qs}' if qs else '')
    payload = _request_json(url, headers={'apikey': key}, timeout=timeout)
    if isinstance(payload, dict):
        code = payload.get('code')
        if payload.get('success') is False or (code is not None and str(code) != '1'):
            raise RuntimeError(f'coinank_error:{code or "unknown"}')
        data = payload.get('data')
        if isinstance(data, dict) and data.get('code') is not None and str(data.get('code')) == '1' and 'data' in data:
            return data.get('data')
        return data if 'data' in payload else payload
    return payload


def _symbol(inst_or_symbol: str) -> str:
    return normalize_symbol(inst_or_symbol)


def fetch_coinank_liquidation(base_coin: str) -> SourceResult:
    """VIP1: 24h/1h aggregate liquidation by base coin."""
    try:
        data = _get('/api/liquidation/allExchange/intervals', {'baseCoin': _symbol(base_coin)})
        return SourceResult('ok', data or {})
    except Exception as e:
        return SourceResult(f'error:{type(e).__name__}', {})


def fetch_coinank_longshort_realtime(base_coin: str, interval: str = '1h') -> SourceResult:
    """VIP1: exchange realtime buy/sell turnover ratio."""
    try:
        data = _get('/api/longshort/realtimeAll', {'baseCoin': _symbol(base_coin), 'interval': interval})
        return SourceResult('ok', data or [])
    except Exception as e:
        return SourceResult(f'error:{type(e).__name__}', [])


def fetch_coinank_top_longshort(base_coin: str, exchange: str = 'OKX', symbol: Optional[str] = None, interval: str = '1h', size: int = 2) -> SourceResult:
    """VIP1: top trader account/position long-short ratios."""
    base = _symbol(base_coin)
    pair = symbol or f'{base}USDT'
    end_time = _now_ms()
    try:
        account = _get('/api/longshort/account', {'exchange': exchange, 'symbol': pair, 'interval': interval, 'endTime': end_time, 'size': size})
        position = _get('/api/longshort/position', {'exchange': exchange, 'symbol': pair, 'interval': interval, 'endTime': end_time, 'size': size})
        return SourceResult('ok', {'account': account or {}, 'position': position or {}})
    except Exception as e:
        return SourceResult(f'error:{type(e).__name__}', {})


def fetch_coinank_open_interest_all(base_coin: str) -> SourceResult:
    """VIP1: OI by exchange with 5m/15m/1h/4h/24h changes and exchange shares."""
    try:
        data = _get('/api/openInterest/all', {'baseCoin': _symbol(base_coin)})
        return SourceResult('ok', data or [])
    except Exception as e:
        return SourceResult(f'error:{type(e).__name__}', [])


def extract_liquidation_metrics(data: Dict[str, Any]) -> Dict[str, Any]:
    h1 = data.get('1h') if isinstance(data, dict) else {}
    h24 = data.get('24h') if isinstance(data, dict) else {}
    top = data.get('topOrder') if isinstance(data, dict) else {}
    return {
        'long_liq_1h_usd': _f((h1 or {}).get('longTurnover')),
        'short_liq_1h_usd': _f((h1 or {}).get('shortTurnover')),
        'liq_total_1h_usd': _f((h1 or {}).get('totalTurnover')),
        'long_liq_24h_usd': _f((h24 or {}).get('longTurnover')),
        'short_liq_24h_usd': _f((h24 or {}).get('shortTurnover')),
        'liq_total_24h_usd': _f((h24 or {}).get('totalTurnover')),
        'coinank_top_liq_side': str((top or {}).get('posSide') or ''),
        'coinank_top_liq_usd': _f((top or {}).get('tradeTurnover')),
        'coinank_liq_total_count_24h': int(_f(data.get('total') if isinstance(data, dict) else 0)),
    }


def extract_longshort_metrics(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    total_buy = sum(_f(r.get('buyTradeTurnover')) for r in rows if isinstance(r, dict))
    total_sell = sum(_f(r.get('sellTradeTurnover')) for r in rows if isinstance(r, dict))
    okx = next((r for r in rows if str(r.get('exchangeName', '')).lower() in {'okx', 'okex'}), {})
    return {
        'buy_turnover_1h_usd': total_buy,
        'sell_turnover_1h_usd': total_sell,
        'buy_sell_ratio_1h': round(total_buy / total_sell, 6) if total_sell else 0.0,
        'okx_buy_sell_ratio_1h': round(_f(okx.get('buyTradeTurnover')) / _f(okx.get('sellTradeTurnover')), 6) if okx and _f(okx.get('sellTradeTurnover')) else 0.0,
    }


def _latest_ratio(obj: Dict[str, Any]) -> float:
    vals = obj.get('longShortRatio') if isinstance(obj, dict) else []
    if not vals:
        return 0.0
    return _f(vals[-1])


def extract_top_longshort_metrics(data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'top_account_long_short_ratio': _latest_ratio((data or {}).get('account') or {}),
        'top_position_long_short_ratio': _latest_ratio((data or {}).get('position') or {}),
    }


def extract_open_interest_metrics(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = sum(_f(r.get('coinValue')) for r in rows if isinstance(r, dict))
    by_exchange = {str(r.get('exchangeName') or ''): r for r in rows if isinstance(r, dict)}
    okx = next((r for name, r in by_exchange.items() if name.lower() in {'okx', 'okex'}), {})
    binance = next((r for name, r in by_exchange.items() if name.lower() == 'binance'), {})
    return {
        'coinank_open_interest_usd': total,
        'coinank_oi_change_5m_pct': _f(okx.get('change5M') if okx else 0),
        'coinank_oi_change_15m_pct': _f(okx.get('change15M') if okx else 0),
        'coinank_oi_change_1h_pct': _f(okx.get('change1H') if okx else 0),
        'coinank_oi_change_4h_pct': _f(okx.get('change4H') if okx else 0),
        'coinank_oi_change_24h_pct': _f(okx.get('change24H') if okx else 0),
        'okx_oi_share_pct': _f(okx.get('rate') if okx else 0),
        'binance_oi_share_pct': _f(binance.get('rate') if binance else 0),
    }


def enrich_candidate_with_coinank(candidate: Dict[str, Any]) -> Dict[str, Any]:
    c = dict(candidate)
    if not coinank_enabled():
        c['coinank_status'] = 'missing_key'
        return c
    base = normalize_symbol(str(c.get('symbol') or c.get('inst_id') or ''))
    if not base:
        c['coinank_status'] = 'invalid_symbol'
        return c
    statuses: Dict[str, str] = {}

    liq = fetch_coinank_liquidation(base)
    statuses['liquidation'] = liq.status
    if liq.status == 'ok' and isinstance(liq.data, dict):
        c.update(extract_liquidation_metrics(liq.data))

    ls = fetch_coinank_longshort_realtime(base, interval='1h')
    statuses['longshort_realtime'] = ls.status
    if ls.status == 'ok' and isinstance(ls.data, list):
        c.update(extract_longshort_metrics(ls.data))

    top_ls = fetch_coinank_top_longshort(base, exchange='OKX', interval='1h', size=2)
    statuses['top_longshort'] = top_ls.status
    if top_ls.status == 'ok' and isinstance(top_ls.data, dict):
        c.update(extract_top_longshort_metrics(top_ls.data))

    oi = fetch_coinank_open_interest_all(base)
    statuses['open_interest'] = oi.status
    if oi.status == 'ok' and isinstance(oi.data, list):
        oi_metrics = extract_open_interest_metrics(oi.data)
        c.update(oi_metrics)
        # Prefer OKX exchange-level short-window OI change when CoinAnk has it.
        if oi_metrics.get('coinank_oi_change_1h_pct'):
            c['oi_change_1h_pct'] = oi_metrics['coinank_oi_change_1h_pct']

    c['coinank_status'] = 'ok' if any(v == 'ok' for v in statuses.values()) else ';'.join(statuses.values())
    c['coinank_detail_status'] = statuses
    c.setdefault('sources', []).append('coinank')
    return c
