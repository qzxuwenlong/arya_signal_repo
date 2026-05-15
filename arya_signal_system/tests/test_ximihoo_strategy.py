from src.strategies.ximihoo_strategy import evaluate_ximihoo_signal, plan_okx_contract_order


def test_btc_target_zone_blocks_alt_chasing_and_forces_risk_off():
    market = {
        "symbol": "DOGE-USDT-SWAP",
        "btc_price": 76500,
        "btc_target_low": 75000,
        "btc_target_high": 80000,
        "return_24h_pct": 18,
        "return_1h_pct": 4.5,
        "range_position_24h_pct": 91,
        "alt_vs_btc_24h_pct": -3,
        "funding_rate_pct": 0.06,
        "oi_change_1h_pct": 18,
        "long_liq_1h_usd": 220000,
        "short_liq_1h_usd": 40000,
        "depth_usd": 900000,
        "spread_pct": 0.04,
    }

    signal = evaluate_ximihoo_signal(market)

    assert signal["state"] == "NO_CHASE_EXIT_RISK"
    assert signal["direction"] == "flat"
    assert signal["allow_trade"] is False
    assert signal["risk_score"] >= 60
    assert any("BTC 已进入目标/风险区间" in r for r in signal["risks"])
    assert any("山寨弱于 BTC" in r for r in signal["risks"])


def test_failed_breakout_reclaim_gives_paper_long_only_on_major_coin():
    market = {
        "symbol": "BTC-USDT-SWAP",
        "btc_price": 73200,
        "btc_target_low": 75000,
        "btc_target_high": 80000,
        "failed_breakout_reclaim": True,
        "reclaim_strength_pct": 1.8,
        "return_1h_pct": 1.2,
        "return_24h_pct": 3.2,
        "range_position_24h_pct": 58,
        "funding_rate_pct": -0.004,
        "oi_change_1h_pct": 9,
        "depth_usd": 12000000,
        "spread_pct": 0.01,
    }

    signal = evaluate_ximihoo_signal(market)
    order = plan_okx_contract_order(signal, account_equity_usdt=10000)

    assert signal["state"] == "FAILED_BREAKOUT_RECLAIM_LONG"
    assert signal["direction"] == "long"
    assert signal["allow_trade"] is False
    assert signal["paper_trade_only"] is True
    assert order["mode"] == "paper"
    assert order["side"] == "buy"
    assert order["leverage"] <= 2
    assert 0 < order["margin_usdt"] <= 250
    assert order["requires_manual_confirmation"] is True


def test_liquidation_conflict_stays_observation_no_directional_trade():
    market = {
        "symbol": "BTC-USDT-SWAP",
        "btc_price": 78500,
        "btc_target_low": 75000,
        "btc_target_high": 80000,
        "liq_1d_bias": "shorts_as_fuel",
        "liq_30d_bias": "longs_as_fuel",
        "short_liq_1h_usd": 350000,
        "long_liq_1h_usd": 320000,
        "return_1h_pct": 0.8,
        "range_position_24h_pct": 73,
        "depth_usd": 9000000,
        "spread_pct": 0.02,
    }

    signal = evaluate_ximihoo_signal(market)

    assert signal["state"] == "LIQUIDATION_CONFLICT"
    assert signal["direction"] == "observe"
    assert signal["allow_trade"] is False
    assert signal["paper_observation_tier"] == "observe"
    assert any("1D/30D 清算方向冲突" in r for r in signal["risks"])


def test_kdj_macd_top_divergence_exits_long_not_auto_short():
    market = {
        "symbol": "ETH-USDT-SWAP",
        "btc_price": 79000,
        "btc_target_low": 75000,
        "btc_target_high": 80000,
        "kdj_top_divergence": True,
        "macd_top_divergence": True,
        "return_24h_pct": 9,
        "range_position_24h_pct": 88,
        "funding_rate_pct": 0.04,
        "oi_change_1h_pct": 11,
        "depth_usd": 8000000,
        "spread_pct": 0.02,
    }

    signal = evaluate_ximihoo_signal(market)
    order = plan_okx_contract_order(signal, account_equity_usdt=10000)

    assert signal["state"] == "TECHNICAL_DIVERGENCE_EXIT_RISK"
    assert signal["direction"] == "flat"
    assert signal["allow_trade"] is False
    assert order["action"] == "no_order"
    assert any("KDJ/MACD 顶背离" in r for r in signal["risks"])


def test_extreme_meme_contract_is_banned_even_if_momentum_is_strong():
    market = {
        "symbol": "1000PEPE-USDT-SWAP",
        "is_meme": True,
        "return_24h_pct": 55,
        "return_1h_pct": 12,
        "range_position_24h_pct": 96,
        "atr_1h_pct": 11,
        "depth_usd": 45000,
        "spread_pct": 0.35,
        "top10_holder_pct": 72,
    }

    signal = evaluate_ximihoo_signal(market)

    assert signal["state"] == "MEME_CONTRACT_BANNED"
    assert signal["direction"] == "flat"
    assert signal["allow_trade"] is False
    assert any("妖币/土狗合约禁入" in r for r in signal["risks"])
