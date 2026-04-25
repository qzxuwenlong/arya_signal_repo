from __future__ import annotations

from typing import Any, Dict, Iterable, List


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ''):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _pct(new: float, old: float) -> float:
    if old == 0:
        return 0.0
    return (new - old) / old * 100.0


def _close(candle: List[Any]) -> float:
    return _f(candle[4]) if len(candle) > 4 else 0.0


def _open(candle: List[Any]) -> float:
    return _f(candle[1]) if len(candle) > 1 else 0.0


def _high(candle: List[Any]) -> float:
    return _f(candle[2]) if len(candle) > 2 else 0.0


def _low(candle: List[Any]) -> float:
    return _f(candle[3]) if len(candle) > 3 else 0.0


def _quote_volume(candle: List[Any]) -> float:
    if len(candle) > 7:
        return _f(candle[7])
    if len(candle) > 6:
        return _f(candle[6])
    if len(candle) > 5:
        return _f(candle[5])
    return 0.0


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _range_position(close: float, highs: Iterable[float], lows: Iterable[float]) -> float:
    hi = max([x for x in highs if x > 0], default=0.0)
    lo = min([x for x in lows if x > 0], default=0.0)
    if hi <= lo or close <= 0:
        return 0.0
    return _clamp((close - lo) / (hi - lo) * 100.0)


def _atr_pct(candles: List[List[Any]], close: float) -> float:
    if not candles or close <= 0:
        return 0.0
    ranges = [max(0.0, _high(c) - _low(c)) for c in candles if _high(c) > 0 and _low(c) > 0]
    if not ranges:
        return 0.0
    return sum(ranges) / len(ranges) / close * 100.0


def compute_candle_metrics(
    candles_1h: List[List[Any]],
    candles_4h: List[List[Any]] | None = None,
    candles_1d: List[List[Any]] | None = None,
) -> Dict[str, float]:
    candles_4h = candles_4h or []
    candles_1d = candles_1d or []
    metrics = {
        'return_1h_pct': 0.0,
        'return_4h_pct': 0.0,
        'return_24h_pct': 0.0,
        'volume_usd_1h': 0.0,
        'volume_1h_vs_24h_avg_pct': 0.0,
        'range_position_24h_pct': 0.0,
        'atr_1h_pct': 0.0,
        'trend_strength': 0.0,
        'breakout_score': 0.0,
        'grid_suitability': 0.0,
    }
    if not candles_1h:
        return metrics

    latest = candles_1h[0]
    latest_close = _close(latest)
    if latest_close <= 0:
        return metrics

    latest_open = _open(latest)
    metrics['return_1h_pct'] = _pct(latest_close, latest_open)
    metrics['volume_usd_1h'] = _quote_volume(latest)

    if candles_4h:
        metrics['return_4h_pct'] = _pct(latest_close, _open(candles_4h[0]))
    if candles_1d:
        metrics['return_24h_pct'] = _pct(latest_close, _open(candles_1d[0]))

    hist_1h = candles_1h[1:25] if len(candles_1h) > 1 else []
    if hist_1h:
        previous_volume = _quote_volume(hist_1h[0])
        if previous_volume > 0:
            metrics['volume_1h_vs_24h_avg_pct'] = _pct(metrics['volume_usd_1h'], previous_volume)

    range_source = candles_1h[:24] or candles_4h[:6] or candles_1d[:1]
    metrics['range_position_24h_pct'] = _range_position(
        latest_close,
        [_high(c) for c in range_source],
        [_low(c) for c in range_source],
    )
    metrics['atr_1h_pct'] = _atr_pct(candles_1h[:14], latest_close)

    trend = (
        abs(metrics['return_1h_pct']) * 0.45
        + abs(metrics['return_4h_pct']) * 0.35
        + abs(metrics['return_24h_pct']) * 0.20
    )
    metrics['trend_strength'] = round(trend, 6)

    volume_boost = _clamp(metrics['volume_1h_vs_24h_avg_pct'] / 3.0, -30.0, 40.0)
    position = metrics['range_position_24h_pct']
    if latest_close >= latest_open:
        breakout = position * 0.65 + _clamp(metrics['return_1h_pct'] * 4.0, 0.0, 35.0) + volume_boost
    else:
        breakout = (100.0 - position) * 0.45 + _clamp(abs(metrics['return_1h_pct']) * 3.0, 0.0, 35.0) + volume_boost
    metrics['breakout_score'] = round(_clamp(breakout), 6)

    # Grid suitability prefers moderate ATR, mid-range positioning, and non-explosive 1H trend.
    atr = metrics['atr_1h_pct']
    atr_score = 100.0 - abs(atr - 2.5) * 18.0
    midrange_score = 100.0 - abs(position - 50.0) * 2.0
    trend_penalty = abs(metrics['return_1h_pct']) * 6.0
    metrics['grid_suitability'] = round(_clamp((atr_score * 0.45 + midrange_score * 0.35 + 50.0 * 0.20) - trend_penalty), 6)

    return metrics
