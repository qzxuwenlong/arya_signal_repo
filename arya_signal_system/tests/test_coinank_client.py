import os

from src.coinank_client import (
    coinank_enabled,
    enrich_candidate_with_coinank,
    extract_liquidation_metrics,
    extract_longshort_metrics,
    extract_open_interest_metrics,
    extract_top_longshort_metrics,
)
from src.scoring import score_candidate


def test_coinank_enabled_false_without_key(monkeypatch):
    monkeypatch.delenv('COINANK_API_KEY', raising=False)
    monkeypatch.delenv('COINANK_APIKEY', raising=False)
    assert coinank_enabled() is False
    c = enrich_candidate_with_coinank({'symbol': 'BTC-USDT-SWAP', 'sources': ['okx']})
    assert c['coinank_status'] == 'missing_key'
    assert c['sources'] == ['okx']


def test_extract_liquidation_metrics_from_coinank_payload():
    data = {
        '1h': {'longTurnover': 260000, 'shortTurnover': 30000, 'totalTurnover': 290000},
        '24h': {'longTurnover': 900000, 'shortTurnover': 120000, 'totalTurnover': 1020000},
        'topOrder': {'posSide': 'long', 'tradeTurnover': 88000},
        'total': 77,
    }
    m = extract_liquidation_metrics(data)
    assert m['long_liq_1h_usd'] == 260000
    assert m['short_liq_1h_usd'] == 30000
    assert m['long_liq_24h_usd'] == 900000
    assert m['coinank_top_liq_side'] == 'long'


def test_extract_longshort_metrics_prefers_aggregate_and_okx_ratio():
    rows = [
        {'exchangeName': 'OKX', 'buyTradeTurnover': 150, 'sellTradeTurnover': 100},
        {'exchangeName': 'Binance', 'buyTradeTurnover': 50, 'sellTradeTurnover': 100},
    ]
    m = extract_longshort_metrics(rows)
    assert m['buy_sell_ratio_1h'] == 1.0
    assert m['okx_buy_sell_ratio_1h'] == 1.5


def test_extract_top_longshort_and_oi_metrics():
    top = {'account': {'longShortRatio': [0.9, 1.4]}, 'position': {'longShortRatio': [1.2, 2.2]}}
    assert extract_top_longshort_metrics(top) == {
        'top_account_long_short_ratio': 1.4,
        'top_position_long_short_ratio': 2.2,
    }
    oi = [
        {'exchangeName': 'OKX', 'coinValue': 1000, 'change5M': 1.1, 'change15M': 2.2, 'change1H': 3.3, 'change4H': 4.4, 'change24H': 5.5, 'rate': 40},
        {'exchangeName': 'Binance', 'coinValue': 2000, 'rate': 55},
    ]
    m = extract_open_interest_metrics(oi)
    assert m['coinank_open_interest_usd'] == 3000
    assert m['coinank_oi_change_1h_pct'] == 3.3
    assert m['okx_oi_share_pct'] == 40
    assert m['binance_oi_share_pct'] == 55


def test_coinank_derivative_metrics_strengthen_short_breakdown_evidence():
    candidate = {
        'symbol': 'SHORTME',
        'price_change_1h_pct': -6.0,
        'volume_change_1h_pct': 120.0,
        'oi_change_1h_pct': 18.3,
        'funding_rate_pct': 0.022,
        'long_liq_1h_usd': 260000,
        'short_liq_1h_usd': 30000,
        'depth_usd': 320000,
        'spread_pct': 0.04,
        'buy_sell_ratio_1h': 0.55,
        'top_account_long_short_ratio': 2.4,
        'binance_oi_share_pct': 55,
        'okx_oi_share_pct': 40,
    }
    scored = score_candidate(candidate)
    assert scored['state'] == 'SHORT_BREAKDOWN'
    assert scored['score'] >= 70
    assert any('主动卖盘' in r for r in scored['reasons'])
    assert any('OI 占比' in r for r in scored['reasons'])
