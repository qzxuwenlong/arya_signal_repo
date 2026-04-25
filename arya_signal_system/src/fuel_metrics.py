from __future__ import annotations

from typing import Any, Dict, Optional

from .market_store import MarketSnapshot, MarketStore
from .scoring import normalize_symbol


def _pct_change(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0
    return (current - previous) / previous * 100


def compute_fuel_metrics(current: MarketSnapshot, previous: Optional[MarketSnapshot]) -> Dict[str, Any]:
    metrics: Dict[str, Any] = {
        'local_history_ready': previous is not None,
        'local_history_window_sec': (current.ts - previous.ts) if previous else 0,
        'price_change_1h_pct': 0.0,
        'volume_change_1h_pct': 0.0,
        'oi_change_1h_pct': 0.0,
        'oi_volume_ratio': 0.0,
    }
    if previous is None:
        return metrics

    price_change = _pct_change(current.price, previous.price)
    volume_change = _pct_change(current.volume_1h, previous.volume_1h)
    oi_change = _pct_change(current.open_interest_usd, previous.open_interest_usd)
    metrics.update(
        {
            'price_change_1h_pct': round(price_change, 6),
            'volume_change_1h_pct': round(volume_change, 6),
            'oi_change_1h_pct': round(oi_change, 6),
            'oi_volume_ratio': round(current.open_interest_usd / current.volume_1h, 6) if current.volume_1h else 0.0,
        }
    )
    return metrics


def candidate_to_snapshot(candidate: Dict[str, Any], *, ts: int, exchange: str = 'okx') -> MarketSnapshot:
    symbol = normalize_symbol(str(candidate.get('symbol') or candidate.get('inst_id') or 'UNKNOWN'))
    return MarketSnapshot(
        ts=ts,
        exchange=exchange,
        symbol=symbol,
        price=float(candidate.get('price') or 0.0),
        volume_1h=float(candidate.get('volume_1h') or candidate.get('volume_usd_1h') or 0.0),
        open_interest_usd=float(candidate.get('open_interest_usd') or 0.0),
        funding_rate_pct=float(candidate.get('funding_rate_pct') or 0.0),
        depth_usd=float(candidate.get('depth_usd') or 0.0),
        spread_pct=float(candidate.get('spread_pct') or 0.0),
    )


def enrich_candidate_with_local_history(candidate: Dict[str, Any], *, store: MarketStore, now_ts: int, exchange: str = 'okx', window_sec: int = 3600) -> Dict[str, Any]:
    enriched = dict(candidate)
    current = candidate_to_snapshot(enriched, ts=now_ts, exchange=exchange)
    previous = store.nearest_before(exchange, current.symbol, now_ts - window_sec)
    enriched.update(compute_fuel_metrics(current, previous))
    store.record_snapshot(current)
    enriched['local_store_symbol'] = current.symbol
    return enriched
