from src.advisory import build_advisory_message, select_alert_candidates


def test_select_alert_candidates_prefers_actionable_non_exit_states():
    candidates = [
        {'symbol': 'BTC', 'state': 'GRID_ALLOWED', 'score': 15, 'local_history_ready': True},
        {'symbol': 'BOME', 'state': 'SQUEEZE_ACTIVE', 'score': 70, 'local_history_ready': True},
        {'symbol': 'WIF', 'state': 'SHORT_ALERT', 'score': 68, 'local_history_ready': True},
        {'symbol': 'DOGE', 'state': 'EXIT_RISK', 'score': 90, 'local_history_ready': True},
        {'symbol': 'SOL', 'state': 'TREND_ALERT', 'score': 55, 'local_history_ready': False},
    ]

    selected = select_alert_candidates(candidates, min_score=50)

    assert [c['symbol'] for c in selected] == ['BOME', 'WIF']


def test_select_alert_candidates_can_report_exit_risk_when_severe():
    candidates = [
        {'symbol': 'WIF', 'state': 'EXIT_RISK', 'score': 0, 'risks': ['资金费率极端，进入尾部/收网风险区'], 'funding_rate_pct': 0.18},
        {'symbol': 'BTC', 'state': 'GRID_ALLOWED', 'score': 15},
    ]

    selected = select_alert_candidates(candidates, min_score=50, include_severe_exit=True)

    assert [c['symbol'] for c in selected] == ['WIF']


def test_build_advisory_message_is_safe_and_requires_manual_confirmation():
    candidates = [
        {
            'symbol': 'BOME',
            'state': 'SQUEEZE_ACTIVE',
            'score': 72,
            'direction': '偏多',
            'strategy': '趋势/爆空',
            'oi_change_1h_pct': 31.2,
            'volume_change_1h_pct': 120.5,
            'price_change_1h_pct': 8.4,
            'reasons': ['OI 与成交量同步放大，存在合约燃料', '空头爆仓显著，爆空结构被验证'],
            'risks': ['meme 波动大'],
        }
    ]

    msg = build_advisory_message(candidates, source_status={'order_execution': 'disabled', 'okx': 'ok'})

    assert 'Arya 交易建议提醒' in msg
    assert 'BOME｜SQUEEZE_ACTIVE｜72分' in msg
    assert '不自动下单' in msg
    assert '人工确认' in msg
    assert 'OI 1h 31.20%' in msg
    assert 'ORDER_EXECUTION: disabled' in msg
