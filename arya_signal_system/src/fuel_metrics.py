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


def compute_signal_persistence(store: MarketStore, current: MarketSnapshot, *, lookback_sec: int = 1800) -> Dict[str, Any]:
    snapshots = store.snapshots_since(current.exchange, current.symbol, current.ts - lookback_sec, before_ts=current.ts)
    series = [*snapshots, current]
    if len(series) < 2:
        return {
            'signal_persistence_count': 0,
            'signal_persistence_score': 0,
            'funding_negative_persistent': False,
            'oi_up_persistent': False,
            'volume_up_persistent': False,
            'price_resilient_persistent': False,
        }

    confirmed = 0
    negative_funding_count = 0
    oi_up_count = 0
    volume_up_count = 0
    price_resilient_count = 0
    for prev, cur in zip(series, series[1:]):
        oi_up = cur.open_interest_usd > prev.open_interest_usd
        vol_up = cur.volume_1h >= prev.volume_1h
        price_resilient = cur.price >= prev.price * 0.985
        neg_funding = cur.funding_rate_pct < -0.01
        if neg_funding:
            negative_funding_count += 1
        if oi_up:
            oi_up_count += 1
        if vol_up:
            volume_up_count += 1
        if price_resilient:
            price_resilient_count += 1
        if neg_funding and oi_up and vol_up and price_resilient:
            confirmed += 1

    score = min(20, confirmed * 5)
    return {
        'signal_persistence_count': confirmed,
        'signal_persistence_score': score,
        'funding_negative_persistent': negative_funding_count >= 2,
        'oi_up_persistent': oi_up_count >= 2,
        'volume_up_persistent': volume_up_count >= 2,
        'price_resilient_persistent': price_resilient_count >= 2,
    }


def enrich_candidate_with_local_history(candidate: Dict[str, Any], *, store: MarketStore, now_ts: int, exchange: str = 'okx', window_sec: int = 3600) -> Dict[str, Any]:
    enriched = dict(candidate)
    current = candidate_to_snapshot(enriched, ts=now_ts, exchange=exchange)
    previous = store.nearest_before(exchange, current.symbol, now_ts - window_sec)
    enriched.update(compute_fuel_metrics(current, previous))
    enriched.update(compute_signal_persistence(store, current))
    store.record_snapshot(current)
    enriched['local_store_symbol'] = current.symbol
    return enriched
