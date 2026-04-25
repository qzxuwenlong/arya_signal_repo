from src.historical_metrics import compute_candle_metrics


def _c(ts, o, h, l, close, quote_vol):
    # OKX candle: ts,o,h,l,c,vol,volCcy,volCcyQuote,confirm
    return [str(ts), str(o), str(h), str(l), str(close), '0', '0', str(quote_vol), '1']


def test_compute_candle_metrics_returns_multi_timeframe_price_volume_and_breakout_context():
    candles_1h = [
        _c(3000, 110, 116, 109, 115, 3000),
        _c(2000, 100, 112, 99, 110, 2000),
        _c(1000, 95, 101, 94, 100, 1000),
    ]
    candles_4h = [
        _c(3000, 90, 116, 88, 115, 12000),
        _c(2000, 85, 92, 80, 90, 8000),
    ]
    candles_1d = [
        _c(3000, 80, 116, 75, 115, 50000),
        _c(2000, 70, 82, 69, 80, 40000),
    ]

    metrics = compute_candle_metrics(candles_1h, candles_4h, candles_1d)

    assert round(metrics['return_1h_pct'], 4) == 4.5455
    assert round(metrics['return_4h_pct'], 4) == 27.7778
    assert round(metrics['return_24h_pct'], 4) == 43.75
    assert metrics['volume_usd_1h'] == 3000.0
    assert round(metrics['volume_1h_vs_24h_avg_pct'], 4) == 50.0
    assert round(metrics['range_position_24h_pct'], 4) == 95.4545
    assert metrics['breakout_score'] > 70
    assert metrics['trend_strength'] > 0
    assert 0 <= metrics['grid_suitability'] <= 100


def test_compute_candle_metrics_handles_empty_or_invalid_history():
    metrics = compute_candle_metrics([], [], [])

    assert metrics['return_1h_pct'] == 0.0
    assert metrics['volume_usd_1h'] == 0.0
    assert metrics['breakout_score'] == 0.0
    assert metrics['grid_suitability'] == 0.0
