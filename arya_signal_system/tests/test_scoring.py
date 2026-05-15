import json
from pathlib import Path

from src.scoring import (
    classify_signal,
    score_candidate,
    normalize_symbol,
    assess_funding_quality,
    detect_guillotine_candle_risk,
    compute_counterparty_fuel_score,
    assess_fair_game_filter,
    detect_flash_crash_short_model,
    compute_anti_consensus_score,
    compute_early_demon_trend_score,
    assess_sector_leader_filter,
)
from src.report import render_markdown_report


def test_normalize_symbol_accepts_okx_swap_and_plain_symbols():
    assert normalize_symbol('BTC-USDT-SWAP') == 'BTC'
    assert normalize_symbol('wif') == 'WIF'
    assert normalize_symbol('BOMEUSDT') == 'BOME'


def test_squeeze_active_scores_high_when_oi_liquidation_and_hype_align():
    candidate = {
        'symbol': 'TEST',
        'price_change_1h_pct': 8.0,
        'volume_change_1h_pct': 150.0,
        'oi_change_1h_pct': 35.0,
        'funding_rate_pct': 0.018,
        'long_liq_1h_usd': 10000,
        'short_liq_1h_usd': 280000,
        'depth_usd': 250000,
        'spread_pct': 0.04,
        'binance_hype_rank': 8,
        'smart_money_count': 4,
        'top10_holder_pct': 18,
    }
    scored = score_candidate(candidate)
    assert scored['score'] >= 70
    assert scored['state'] == 'LONG_SQUEEZE'
    assert scored['model'] == '做多模型A-爆空顺势多'
    assert scored['direction'] == '偏多'
    assert any('爆空' in r or '空头爆仓' in r for r in scored['reasons'])


def test_short_alert_when_downtrend_oi_volume_and_long_liquidation_align():
    candidate = {
        'symbol': 'SHORTME',
        'price_change_1h_pct': -6.0,
        'volume_change_1h_pct': 120.0,
        'oi_change_1h_pct': 28.0,
        'funding_rate_pct': 0.022,
        'long_liq_1h_usd': 260000,
        'short_liq_1h_usd': 30000,
        'depth_usd': 320000,
        'spread_pct': 0.04,
        'binance_hype_rank': 12,
    }

    scored = score_candidate(candidate)

    assert scored['score'] >= 70
    assert scored['state'] == 'SHORT_BREAKDOWN'
    assert scored['model'] == '做空模型A-庄撤仓收网'
    assert scored['direction'] == '偏空'
    assert scored['strategy'] == '做空/瀑布'
    assert any('做空' in r or '多头爆仓' in r for r in scored['reasons'])


def test_long_pullback_when_strong_coin_reclaims_after_deep_pullback():
    candidate = {
        'symbol': 'PULLBACK',
        'price_change_1h_pct': 4.2,
        'return_4h_pct': -11.0,
        'return_24h_pct': 38.0,
        'volume_change_1h_pct': 85.0,
        'oi_change_1h_pct': 12.0,
        'funding_rate_pct': 0.012,
        'long_liq_1h_usd': 22000,
        'short_liq_1h_usd': 56000,
        'depth_usd': 260000,
        'spread_pct': 0.05,
        'range_position_24h_pct': 42.0,
        'trend_strength': 1.3,
        'binance_hype_rank': 15,
    }

    scored = score_candidate(candidate)

    assert scored['state'] == 'LONG_PULLBACK'
    assert scored['model'] == '做多模型B-强庄回调抄底'
    assert scored['direction'] == '偏多'
    assert scored['strategy'] == '回调试多'
    assert scored['score'] >= 55


def test_short_tail_risk_when_funding_extreme_after_tail_squeeze():
    candidate = {
        'symbol': 'TAIL',
        'price_change_1h_pct': 0.5,
        'return_24h_pct': 70.0,
        'volume_change_1h_pct': 20.0,
        'oi_change_1h_pct': 42.0,
        'funding_rate_pct': 0.135,
        'long_liq_1h_usd': 18000,
        'short_liq_1h_usd': 35000,
        'depth_usd': 200000,
        'spread_pct': 0.06,
        'range_position_24h_pct': 94.0,
    }

    scored = score_candidate(candidate)

    assert scored['state'] == 'SHORT_TAIL_RISK'
    assert scored['model'] == '做空模型B-尾部高危反手观察'
    assert scored['direction'] == '不追多'
    assert scored['strategy'] == '减多/观察反手'
    assert scored['allow_trade'] is False


def test_no_trade_fake_oi_when_oi_expands_without_volume_or_liquidation():
    candidate = {
        'symbol': 'FAKEOI',
        'price_change_1h_pct': 0.4,
        'volume_change_1h_pct': 8.0,
        'oi_change_1h_pct': 36.0,
        'funding_rate_pct': 0.006,
        'long_liq_1h_usd': 1200,
        'short_liq_1h_usd': 1600,
        'depth_usd': 180000,
        'spread_pct': 0.05,
    }

    scored = score_candidate(candidate)

    assert scored['state'] == 'NO_TRADE_FAKE_OI'
    assert scored['model'] == '无效模型-OI未验证'
    assert scored['direction'] == '不做'
    assert scored['strategy'] == '只观察'
    assert scored['score'] <= 45


def test_grid_allowed_when_volatility_and_depth_ok_but_no_squeeze():
    candidate = {
        'symbol': 'RANGE',
        'price_change_1h_pct': 1.2,
        'volume_change_1h_pct': 35.0,
        'oi_change_1h_pct': 5.0,
        'funding_rate_pct': 0.004,
        'long_liq_1h_usd': 20000,
        'short_liq_1h_usd': 25000,
        'depth_usd': 180000,
        'spread_pct': 0.05,
        'binance_hype_rank': 28,
    }
    scored = score_candidate(candidate)
    assert scored['state'] == 'GRID_ALLOWED'
    assert scored['strategy'] == '网格/震荡'


def test_exit_risk_when_funding_extreme_and_oi_fake_suspected():
    candidate = {
        'symbol': 'DANGER',
        'price_change_1h_pct': 0.3,
        'volume_change_1h_pct': 5.0,
        'oi_change_1h_pct': 45.0,
        'funding_rate_pct': 0.16,
        'long_liq_1h_usd': 1000,
        'short_liq_1h_usd': 1200,
        'depth_usd': 30000,
        'spread_pct': 0.5,
        'top10_holder_pct': 62,
    }
    scored = score_candidate(candidate)
    assert scored['state'] in {'EXIT_RISK', 'OI_FAKE_SUSPECT'}
    assert scored['allow_trade'] is False



def test_funding_quality_requires_negative_funding_oi_growth_and_price_resilience():
    good = assess_funding_quality({
        'funding_rate_pct': -0.045,
        'oi_change_1h_pct': 24.0,
        'price_change_1h_pct': 1.8,
        'volume_change_1h_pct': 90.0,
        'signal_persistence_count': 3,
    })
    assert good['funding_quality'] == 'negative_confirmed_long_fuel'
    assert good['funding_quality_score'] >= 20
    assert any('负费率' in r and 'OI' in r for r in good['reasons'])

    trap = assess_funding_quality({
        'funding_rate_pct': -0.05,
        'oi_change_1h_pct': -12.0,
        'price_change_1h_pct': -8.0,
        'volume_change_1h_pct': 20.0,
        'signal_persistence_count': 1,
    })
    assert trap['funding_quality'] == 'negative_funding_trap'
    assert trap['funding_quality_score'] <= -20
    assert any('诱多' in r or '猎杀' in r for r in trap['risks'])


def test_score_candidate_downgrades_negative_funding_without_oi_confirmation():
    candidate = {
        'symbol': 'CHIP',
        'price_change_1h_pct': -7.5,
        'volume_change_1h_pct': 15.0,
        'oi_change_1h_pct': -10.0,
        'funding_rate_pct': -0.05,
        'long_liq_1h_usd': 6000,
        'short_liq_1h_usd': 9000,
        'depth_usd': 220000,
        'spread_pct': 0.04,
        'signal_persistence_count': 1,
    }

    scored = score_candidate(candidate)

    assert scored['funding_quality'] == 'negative_funding_trap'
    assert scored['state'] == 'NO_CHASE_NEGATIVE_FUNDING'
    assert scored['score'] <= 45
    assert any('负费率' in r for r in scored['risks'])


def test_signal_persistence_rewards_repeated_confirmed_monitor_hits():
    scored = score_candidate({
        'symbol': 'KAT',
        'price_change_1h_pct': 2.4,
        'volume_change_1h_pct': 80.0,
        'oi_change_1h_pct': 22.0,
        'funding_rate_pct': -0.035,
        'long_liq_1h_usd': 20000,
        'short_liq_1h_usd': 45000,
        'depth_usd': 300000,
        'spread_pct': 0.04,
        'signal_persistence_count': 4,
    })

    assert scored['funding_quality'] == 'negative_confirmed_long_fuel'
    assert scored['signal_persistence_score'] > 0
    assert any('持续' in r for r in scored['reasons'])
    assert scored['state'] != 'NO_CHASE_NEGATIVE_FUNDING'


def test_detect_guillotine_candle_risk_flags_fast_pump_then_dump():
    risk = detect_guillotine_candle_risk({
        'return_24h_pct': 42.0,
        'return_1h_pct': -16.0,
        'range_position_24h_pct': 92.0,
        'volume_1h_vs_24h_avg_pct': 260.0,
        'atr_1h_pct': 5.0,
    })
    assert risk['guillotine_candle_risk'] is True
    assert risk['guillotine_risk_score'] <= -20
    assert any('断头线' in r for r in risk['risks'])


def test_score_candidate_marks_guillotine_as_no_chase():
    scored = score_candidate({
        'symbol': 'KNIFE',
        'price_change_1h_pct': -15.0,
        'return_1h_pct': -15.0,
        'return_24h_pct': 55.0,
        'volume_change_1h_pct': 210.0,
        'volume_1h_vs_24h_avg_pct': 260.0,
        'oi_change_1h_pct': 18.0,
        'funding_rate_pct': 0.02,
        'long_liq_1h_usd': 110000,
        'short_liq_1h_usd': 12000,
        'depth_usd': 240000,
        'spread_pct': 0.05,
        'range_position_24h_pct': 88.0,
        'atr_1h_pct': 6.0,
    })
    assert scored['guillotine_candle_risk'] is True
    assert scored['state'] == 'NO_CHASE_GUILLOTINE'
    assert scored['allow_trade'] is False
    assert scored['score'] <= 45



def test_counterparty_fuel_score_identifies_short_fuel_for_long_squeeze():
    fuel = compute_counterparty_fuel_score({
        'symbol': 'FUEL',
        'price_change_1h_pct': 4.5,
        'volume_change_1h_pct': 95.0,
        'oi_change_1h_pct': 26.0,
        'funding_rate_pct': -0.032,
        'short_liq_1h_usd': 260000,
        'long_liq_1h_usd': 22000,
        'buy_sell_ratio_1h': 1.7,
        'signal_persistence_count': 3,
    })

    assert fuel['counterparty_fuel_direction'] == 'shorts_as_fuel'
    assert fuel['counterparty_fuel_score'] >= 70
    assert any('空头燃料' in r for r in fuel['reasons'])


def test_fair_game_filter_blocks_unfair_thin_spiky_venues():
    fair = assess_fair_game_filter({
        'symbol': 'UNFAIR',
        'depth_usd': 42000,
        'spread_pct': 0.32,
        'atr_1h_pct': 12.0,
        'top10_holder_pct': 66,
        'guillotine_candle_risk': False,
    })

    assert fair['fair_game'] is False
    assert fair['fair_game_score'] <= -30
    assert any('公平场' in r or '庄控' in r for r in fair['risks'])


def test_flash_crash_short_model_detects_overheated_breakdown():
    crash = detect_flash_crash_short_model({
        'symbol': 'CRASH',
        'price_change_1h_pct': -11.0,
        'return_24h_pct': 64.0,
        'range_position_24h_pct': 91.0,
        'volume_change_1h_pct': 190.0,
        'oi_change_1h_pct': 24.0,
        'long_liq_1h_usd': 310000,
        'short_liq_1h_usd': 18000,
        'depth_usd': 260000,
        'spread_pct': 0.05,
    })

    assert crash['flash_crash_short'] is True
    assert crash['state'] == 'FLASH_CRASH_SHORT'
    assert crash['score_bonus'] >= 20
    assert any('闪崩' in r or '破位' in r for r in crash['reasons'])


def test_score_candidate_blocks_unfair_game_and_reports_note():
    scored = score_candidate({
        'symbol': 'CASINO',
        'price_change_1h_pct': 9.0,
        'volume_change_1h_pct': 180.0,
        'oi_change_1h_pct': 32.0,
        'funding_rate_pct': 0.018,
        'long_liq_1h_usd': 12000,
        'short_liq_1h_usd': 180000,
        'depth_usd': 35000,
        'spread_pct': 0.36,
        'atr_1h_pct': 15.0,
        'top10_holder_pct': 72,
    })
    report = render_markdown_report([scored])

    assert scored['state'] == 'NO_TRADE_UNFAIR_GAME'
    assert scored['fair_game'] is False
    assert scored['score'] <= 40
    assert 'NO_TRADE_UNFAIR_GAME' in report
    assert '公平场不足' in report


def test_score_candidate_promotes_flash_crash_short_when_fair_and_breaking_down():
    scored = score_candidate({
        'symbol': 'DUMP',
        'price_change_1h_pct': -12.0,
        'return_1h_pct': -12.0,
        'return_24h_pct': 58.0,
        'range_position_24h_pct': 86.0,
        'volume_change_1h_pct': 220.0,
        'volume_1h_vs_24h_avg_pct': 120.0,
        'oi_change_1h_pct': 30.0,
        'funding_rate_pct': 0.035,
        'long_liq_1h_usd': 360000,
        'short_liq_1h_usd': 25000,
        'depth_usd': 380000,
        'spread_pct': 0.04,
        'atr_1h_pct': 4.0,
        'binance_hype_rank': 16,
        'local_history_ready': True,
    })

    assert scored['state'] == 'FLASH_CRASH_SHORT'
    assert scored['direction'] == '偏空'
    assert scored['strategy'] == '做空/闪崩'
    assert scored['counterparty_fuel_score'] >= 60
    assert scored['fair_game'] is True
    assert scored['score'] >= 70



def test_anti_consensus_score_identifies_crowded_shorts_as_long_fuel():
    anti = compute_anti_consensus_score({
        'symbol': 'REVERSAL',
        'funding_rate_pct': -0.045,
        'oi_change_1h_pct': 28.0,
        'price_change_1h_pct': 1.6,
        'volume_change_1h_pct': 95.0,
        'buy_sell_ratio_1h': 1.35,
        'signal_persistence_count': 3,
    })

    assert anti['anti_consensus_direction'] == 'fade_crowded_shorts'
    assert anti['anti_consensus_score'] >= 70
    assert any('反共识' in r or '空头拥挤' in r for r in anti['reasons'])


def test_early_demon_trend_detects_attention_inflow_before_tail_risk():
    demon = compute_early_demon_trend_score({
        'symbol': 'EARLY',
        'return_24h_pct': 18.0,
        'price_change_1h_pct': 4.2,
        'volume_change_1h_pct': 130.0,
        'oi_change_1h_pct': 18.0,
        'range_position_24h_pct': 58.0,
        'atr_1h_pct': 3.4,
        'binance_hype_rank': 18,
        'depth_usd': 240000,
        'spread_pct': 0.05,
    })

    assert demon['early_demon_trend'] is True
    assert demon['early_demon_trend_score'] >= 70
    assert any('早期妖币' in r or '注意力' in r for r in demon['reasons'])


def test_sector_leader_filter_downgrades_lagging_same_sector_names():
    leader = assess_sector_leader_filter({'symbol': 'LEAD', 'sector_rank': 1, 'sector': 'ai-meme'})
    laggard = assess_sector_leader_filter({'symbol': 'LAG', 'sector_rank': 5, 'sector': 'ai-meme'})

    assert leader['sector_leader'] is True
    assert leader['sector_filter'] == 'leader'
    assert laggard['sector_leader'] is False
    assert laggard['sector_filter'] == 'laggard_observe_only'
    assert laggard['score_adjustment'] < 0


def test_score_candidate_marks_early_demon_as_observation_not_main_entry():
    scored = score_candidate({
        'symbol': 'EARLY',
        'price_change_1h_pct': 4.2,
        'return_24h_pct': 18.0,
        'volume_change_1h_pct': 135.0,
        'oi_change_1h_pct': 18.0,
        'funding_rate_pct': 0.006,
        'long_liq_1h_usd': 22000,
        'short_liq_1h_usd': 35000,
        'depth_usd': 260000,
        'spread_pct': 0.05,
        'range_position_24h_pct': 56.0,
        'atr_1h_pct': 3.0,
        'binance_hype_rank': 14,
        'sector_rank': 1,
        'local_history_ready': True,
    })

    assert scored['state'] == 'EARLY_DEMON_TREND'
    assert scored['paper_observation_tier'] == 'observe'
    assert scored['allow_trade'] is False
    assert scored['early_demon_trend'] is True
    assert scored['thesis_invalidation']


def test_sector_laggard_is_downgraded_to_observe_only_even_when_hot():
    scored = score_candidate({
        'symbol': 'LAG',
        'price_change_1h_pct': 5.0,
        'return_24h_pct': 22.0,
        'volume_change_1h_pct': 150.0,
        'oi_change_1h_pct': 20.0,
        'funding_rate_pct': 0.008,
        'long_liq_1h_usd': 20000,
        'short_liq_1h_usd': 30000,
        'depth_usd': 250000,
        'spread_pct': 0.05,
        'range_position_24h_pct': 52.0,
        'atr_1h_pct': 3.0,
        'binance_hype_rank': 12,
        'sector': 'ai-meme',
        'sector_rank': 4,
    })

    assert scored['sector_filter'] == 'laggard_observe_only'
    assert scored['paper_observation_tier'] == 'observe'
    assert scored['state'] in {'SECTOR_LAGGARD_OBSERVE', 'EARLY_DEMON_TREND'}
    assert scored['score'] <= 65


def test_report_renders_observation_tier_and_thesis_invalidation():
    scored = score_candidate({
        'symbol': 'OBS',
        'price_change_1h_pct': 4.0,
        'return_24h_pct': 16.0,
        'volume_change_1h_pct': 120.0,
        'oi_change_1h_pct': 17.0,
        'funding_rate_pct': 0.005,
        'long_liq_1h_usd': 20000,
        'short_liq_1h_usd': 30000,
        'depth_usd': 260000,
        'spread_pct': 0.05,
        'range_position_24h_pct': 50.0,
        'atr_1h_pct': 3.0,
        'binance_hype_rank': 11,
    })
    report = render_markdown_report([scored])

    assert '观察层' in report
    assert '失效条件' in report
    assert 'EARLY_DEMON_TREND' in report

def test_report_renders_state_with_chinese_note():
    scored = score_candidate({
        'symbol': 'TRAP',
        'price_change_1h_pct': -5.0,
        'volume_change_1h_pct': 10.0,
        'oi_change_1h_pct': -3.0,
        'funding_rate_pct': -0.025,
        'long_liq_1h_usd': 1000,
        'short_liq_1h_usd': 1000,
        'depth_usd': 200000,
        'spread_pct': 0.05,
    })
    report = render_markdown_report([scored])

    assert 'NO_CHASE_NEGATIVE_FUNDING' in report
    assert '负费率诱多，不追多' in report


def test_smart_short_probe_marks_negative_funding_oi_price_resilience_as_observation():
    scored = score_candidate({
        'symbol': 'AXS',
        'price_change_1h_pct': 2.99,
        'volume_change_1h_pct': 5556.56,
        'oi_change_1h_pct': 1.85,
        'funding_rate_pct': -0.0806,
        'long_liq_1h_usd': 0,
        'short_liq_1h_usd': 0,
        'depth_usd': 422352,
        'spread_pct': 0.0062,
        'signal_persistence_count': 2,
        'local_history_ready': True,
    })

    assert scored['state'] == 'SMART_SHORT_PROBE'
    assert scored['model'] == '空头试探观察'
    assert scored['direction'] == '偏空观察'
    assert scored['strategy'] == '观察/等待破位与反抽失败确认'
    assert scored['paper_observation_tier'] == 'observe'
    assert scored['allow_trade'] is False
    assert scored['score'] >= 50
    assert any('空头试探' in r or '负费率' in r for r in scored['reasons'])


def test_short_confirming_requires_prior_probe_breakdown_without_oi_collapse():
    scored = score_candidate({
        'symbol': 'AXS',
        'previous_state': 'SMART_SHORT_PROBE',
        'price_change_1h_pct': -2.8,
        'volume_change_1h_pct': 320.0,
        'oi_change_1h_pct': -1.2,
        'funding_rate_pct': -0.092,
        'long_liq_1h_usd': 0,
        'short_liq_1h_usd': 0,
        'depth_usd': 430000,
        'spread_pct': 0.006,
        'signal_persistence_count': 3,
        'local_history_ready': True,
    })

    assert scored['state'] == 'SHORT_CONFIRMING'
    assert scored['model'] == '空头确认中'
    assert scored['direction'] == '偏空观察'
    assert scored['strategy'] == '高优先级观察/等待反抽失败'
    assert scored['paper_observation_tier'] == 'observe'
    assert scored['allow_trade'] is False
    assert scored['score'] >= 55


def test_probe_turns_to_shorts_as_fuel_when_price_keeps_holding_up():
    scored = score_candidate({
        'symbol': 'AXS',
        'previous_state': 'SMART_SHORT_PROBE',
        'price_change_1h_pct': 4.1,
        'volume_change_1h_pct': 240.0,
        'oi_change_1h_pct': 3.4,
        'funding_rate_pct': -0.09,
        'long_liq_1h_usd': 0,
        'short_liq_1h_usd': 0,
        'depth_usd': 470000,
        'spread_pct': 0.006,
        'signal_persistence_count': 3,
        'local_history_ready': True,
    })

    assert scored['state'] == 'SHORTS_AS_FUEL'
    assert scored['direction'] == '偏多观察'
    assert scored['paper_observation_tier'] == 'observe'
    assert scored['allow_trade'] is False


def test_late_negative_funding_oi_collapse_stays_exit_risk_not_short_confirming():
    scored = score_candidate({
        'symbol': 'AXS',
        'previous_state': 'SMART_SHORT_PROBE',
        'price_change_1h_pct': -7.8,
        'volume_change_1h_pct': 255.0,
        'oi_change_1h_pct': -16.5,
        'funding_rate_pct': -0.1807,
        'long_liq_1h_usd': 0,
        'short_liq_1h_usd': 0,
        'depth_usd': 460000,
        'spread_pct': 0.006,
        'local_history_ready': True,
    })

    assert scored['state'] == 'EXIT_RISK'
    assert scored['allow_trade'] is False
    assert scored['paper_observation_tier'] == 'none'


def test_report_renders_smart_short_probe_chinese_note():
    scored = score_candidate({
        'symbol': 'AXS',
        'price_change_1h_pct': 2.8,
        'volume_change_1h_pct': 600.0,
        'oi_change_1h_pct': 1.2,
        'funding_rate_pct': -0.07,
        'depth_usd': 300000,
        'spread_pct': 0.01,
        'signal_persistence_count': 2,
    })
    report = render_markdown_report([scored])

    assert 'SMART_SHORT_PROBE' in report
    assert '空头试探观察' in report
    assert '观察层 observe' in report


def test_report_contains_manual_confirmation_and_no_auto_order():
    scored = score_candidate({'symbol':'TEST','score':80,'depth_usd':200000,'spread_pct':0.03,'oi_change_1h_pct':20,'short_liq_1h_usd':100000,'long_liq_1h_usd':1000})
    report = render_markdown_report([scored], source_status={'okx':'ok','binance_web3':'ok','coinank':'missing_key'})
    assert '不自动下单' in report
    assert '人工确认' in report
    assert 'TEST' in report
    assert 'CoinAnk' in report
