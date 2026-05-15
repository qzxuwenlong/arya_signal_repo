from src.advisory import build_advisory_message, build_from_scan, select_alert_candidates


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


def test_build_from_scan_can_emit_observation_tier_alerts_separately_from_entries():
    scan = {
        'source_status': {'order_execution': 'disabled', 'okx': 'ok'},
        'candidates': [
            {
                'symbol': 'AXS',
                'state': 'SMART_SHORT_PROBE',
                'model': '空头试探观察',
                'direction': '偏空观察',
                'strategy': '观察/等待破位与反抽失败确认',
                'score': 58,
                'paper_observation_tier': 'observe',
                'local_history_ready': True,
                'funding_rate_pct': -0.08,
                'oi_change_1h_pct': 1.85,
                'volume_change_1h_pct': 5556.56,
                'price_change_1h_pct': 2.99,
            }
        ],
    }

    result = build_from_scan(scan, min_score=50, include_observations=True)

    assert result['should_notify'] is True
    assert result['selected'][0]['symbol'] == 'AXS'
    assert result['selected'][0]['alert_tier'] == 'observation'
    assert 'Arya 观察提醒' in result['message']
    assert 'AXS｜SMART_SHORT_PROBE｜58分' in result['message']
    assert '观察层' in result['message']
    assert '不是开仓信号' in result['message']
    assert '不自动下单' in result['message']


def test_build_from_scan_keeps_observation_alerts_off_by_default():
    scan = {
        'source_status': {'order_execution': 'disabled'},
        'candidates': [
            {
                'symbol': 'AXS',
                'state': 'SHORT_CONFIRMING',
                'score': 66,
                'paper_observation_tier': 'observe',
                'local_history_ready': True,
            }
        ],
    }

    result = build_from_scan(scan, min_score=50)

    assert result['should_notify'] is False
    assert result['selected'] == []


def test_build_from_scan_can_emit_c_tier_onchain_observation_alerts_separately():
    scan = {
        'source_status': {'order_execution': 'disabled', 'onchainos': 'ok'},
        'candidates': [],
        'onchain_observation_pool': {
            'source': 'okx_onchainos',
            'candidates': [
                {
                    'symbol': 'BONK',
                    'state': 'ONCHAIN_OBSERVE',
                    'score': 41,
                    'chain': 'solana',
                    'source': ['trending', 'smart_money'],
                    'tier': 'C_ONCHAIN_OBSERVE',
                    'allow_trade': False,
                    'paper_observation_tier': 'observe',
                    'smart_money_signal_count': 3,
                    'smart_money_amount_usd': 12000,
                    'onchain_trending_rank': 2,
                    'reasons': ['链上趋势榜第 2 名', '聪明钱信号出现'],
                    'risks': ['链上观察，不是开仓信号；OKX 合约结构确认前不进主交易'],
                }
            ],
        },
    }

    result = build_from_scan(scan, min_score=50, include_onchain_observations=True, min_onchain_score=20)

    assert result['should_notify'] is True
    assert result['selected'][0]['symbol'] == 'BONK'
    assert result['selected'][0]['alert_tier'] == 'onchain_observation'
    assert result['selected'][0]['allow_trade'] is False
    assert 'Arya 链上观察提醒' in result['message']
    assert 'BONK｜ONCHAIN_OBSERVE｜41分' in result['message']
    assert 'C档链上观察' in result['message']
    assert '不是开仓信号' in result['message']
    assert '不自动下单' in result['message']


def test_build_from_scan_keeps_onchain_observation_alerts_off_by_default():
    scan = {
        'source_status': {'order_execution': 'disabled'},
        'onchain_observation_pool': {
            'candidates': [
                {'symbol': 'BONK', 'state': 'ONCHAIN_OBSERVE', 'score': 49, 'tier': 'C_ONCHAIN_OBSERVE', 'allow_trade': False, 'paper_observation_tier': 'observe'}
            ],
        },
    }

    result = build_from_scan(scan, min_score=50)

    assert result['should_notify'] is False
    assert result['selected'] == []
