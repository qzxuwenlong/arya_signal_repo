from pathlib import Path

from src.market_store import MarketSnapshot, MarketStore
from src.fuel_metrics import compute_fuel_metrics, enrich_candidate_with_local_history


def test_market_store_persists_and_returns_window_snapshots(tmp_path):
    db_path = tmp_path / 'market.sqlite'
    store = MarketStore(db_path)
    store.record_snapshot(MarketSnapshot(ts=1000, exchange='okx', symbol='BTC', price=100, volume_1h=1000, open_interest_usd=1_000_000, funding_rate_pct=0.01, depth_usd=200_000, spread_pct=0.02))
    store.record_snapshot(MarketSnapshot(ts=1300, exchange='okx', symbol='BTC', price=105, volume_1h=1600, open_interest_usd=1_250_000, funding_rate_pct=0.02, depth_usd=220_000, spread_pct=0.03))

    latest = store.latest('okx', 'BTC')
    assert latest is not None
    assert latest.price == 105

    prior = store.nearest_before('okx', 'BTC', target_ts=1300 - 300)
    assert prior is not None
    assert prior.open_interest_usd == 1_000_000


def test_compute_fuel_metrics_from_two_snapshots():
    previous = MarketSnapshot(ts=1000, exchange='okx', symbol='BOME', price=0.001, volume_1h=100_000, open_interest_usd=1_000_000, funding_rate_pct=0.005, depth_usd=120_000, spread_pct=0.04)
    current = MarketSnapshot(ts=4600, exchange='okx', symbol='BOME', price=0.0012, volume_1h=250_000, open_interest_usd=1_400_000, funding_rate_pct=0.02, depth_usd=150_000, spread_pct=0.03)

    metrics = compute_fuel_metrics(current, previous)

    assert round(metrics['price_change_1h_pct'], 2) == 20.0
    assert round(metrics['volume_change_1h_pct'], 2) == 150.0
    assert round(metrics['oi_change_1h_pct'], 2) == 40.0
    assert round(metrics['oi_volume_ratio'], 4) == 5.6
    assert metrics['local_history_ready'] is True


def test_enrich_candidate_uses_local_history_when_available(tmp_path):
    store = MarketStore(tmp_path / 'market.sqlite')
    store.record_snapshot(MarketSnapshot(ts=1000, exchange='okx', symbol='SOL', price=80, volume_1h=1000, open_interest_usd=100_000_000, funding_rate_pct=0.001, depth_usd=1_000_000, spread_pct=0.02))
    candidate = {'symbol': 'SOL-USDT-SWAP', 'price': 88, 'volume_1h': 1800, 'open_interest_usd': 130_000_000, 'funding_rate_pct': 0.01, 'depth_usd': 2_000_000, 'spread_pct': 0.01}

    enriched = enrich_candidate_with_local_history(candidate, store=store, now_ts=4600, exchange='okx')

    assert enriched['oi_change_1h_pct'] == 30.0
    assert enriched['price_change_1h_pct'] == 10.0
    assert enriched['volume_change_1h_pct'] == 80.0
    assert enriched['local_history_ready'] is True
