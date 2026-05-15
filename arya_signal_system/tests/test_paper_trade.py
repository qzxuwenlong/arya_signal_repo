from __future__ import annotations

import json
from pathlib import Path

from src.paper_trade import build_paper_trade_rows, append_paper_trades_from_scan


def _scan(candidates):
    return {
        'source_status': {'order_execution': 'disabled', 'okx': 'ok'},
        'candidates': candidates,
    }


def test_build_paper_trade_rows_records_only_actionable_entries_with_risk_plan():
    scan = _scan([
        {
            'symbol': 'BOME',
            'state': 'LONG_SQUEEZE',
            'model': '做多模型A-爆空顺势多',
            'direction': '偏多',
            'strategy': '顺势做多',
            'score': 72,
            'last_price': 0.01,
            'atr_1h_pct': 6.0,
            'funding_rate_pct': 0.01,
            'local_history_ready': True,
        },
        {
            'symbol': 'RISK',
            'state': 'EXIT_RISK',
            'model': '尾部风险',
            'direction': '不做',
            'score': 0,
            'last_price': 1.0,
        },
    ])

    rows = build_paper_trade_rows(scan, now_ts=1700000000, min_score=50)

    assert len(rows) == 1
    row = rows[0]
    assert row['trade_id'] == '1700000000-BOME-LONG_SQUEEZE'
    assert row['mode'] == 'paper'
    assert row['symbol'] == 'BOME'
    assert row['side'] == 'long'
    assert row['entry_ref_price'] == 0.01
    assert row['status'] == 'open'
    assert row['result_1h_pct'] is None
    assert row['result_4h_pct'] is None
    assert row['result_24h_pct'] is None
    assert row['stop_price'] < row['entry_ref_price']
    assert row['take_profit_1_price'] > row['entry_ref_price']
    assert row['order_execution'] == 'disabled'


def test_build_paper_trade_rows_supports_short_breakdown_plan():
    scan = _scan([
        {
            'symbol': 'SHORTME',
            'state': 'SHORT_BREAKDOWN',
            'model': '做空模型A-庄撤仓/收网做空',
            'direction': '偏空',
            'strategy': '做空/瀑布',
            'score': 81,
            'last_price': 2.0,
            'atr_1h_pct': 4.0,
            'local_history_ready': True,
        },
    ])

    row = build_paper_trade_rows(scan, now_ts=1700000100, min_score=50)[0]

    assert row['side'] == 'short'
    assert row['stop_price'] > row['entry_ref_price']
    assert row['take_profit_1_price'] < row['entry_ref_price']
    assert row['take_profit_2_price'] < row['take_profit_1_price']

def test_build_paper_trade_rows_records_flash_crash_short_context():
    scan = _scan([
        {
            'symbol': 'DUMP',
            'state': 'FLASH_CRASH_SHORT',
            'model': '妖币高位破位闪崩空',
            'direction': '偏空',
            'strategy': '做空/闪崩',
            'score': 78,
            'last_price': 1.5,
            'atr_1h_pct': 5.0,
            'local_history_ready': True,
            'counterparty_fuel_score': 82,
            'counterparty_fuel_direction': 'longs_as_fuel',
            'fair_game': True,
            'fair_game_score': 10,
        },
    ])

    row = build_paper_trade_rows(scan, now_ts=1700000200, min_score=50)[0]

    assert row['side'] == 'short'
    assert row['state'] == 'FLASH_CRASH_SHORT'
    assert row['counterparty_fuel_score'] == 82
    assert row['counterparty_fuel_direction'] == 'longs_as_fuel'
    assert row['fair_game'] is True
    assert row['take_profit_1_price'] < row['entry_ref_price']

def test_append_paper_trades_from_scan_dedupes_existing_open_trade(tmp_path):
    ledger = tmp_path / 'paper_trades.jsonl'
    scan_path = tmp_path / 'scan.json'
    scan = _scan([
        {
            'symbol': 'BOME',
            'state': 'LONG_SQUEEZE',
            'model': '做多模型A-爆空顺势多',
            'direction': '偏多',
            'strategy': '顺势做多',
            'score': 72,
            'last_price': 0.01,
            'local_history_ready': True,
        },
    ])
    scan_path.write_text(json.dumps(scan), encoding='utf-8')

    first = append_paper_trades_from_scan(scan_path, ledger, now_ts=1700000000, min_score=50)
    second = append_paper_trades_from_scan(scan_path, ledger, now_ts=1700000300, min_score=50)

    assert first['appended'] == 1
    assert second['appended'] == 0
    lines = ledger.read_text(encoding='utf-8').splitlines()
    assert len(lines) == 1
    saved = json.loads(lines[0])
    assert saved['symbol'] == 'BOME'
    assert saved['status'] == 'open'



def test_build_paper_trade_rows_records_observation_tier_without_main_entry_pollution():
    scan = _scan([
        {
            'symbol': 'EARLY',
            'state': 'EARLY_DEMON_TREND',
            'model': '第一性原理-早期妖币观察',
            'direction': '偏多观察',
            'strategy': '观察级paper/等待二次确认',
            'score': 62,
            'last_price': 0.25,
            'atr_1h_pct': 3.0,
            'local_history_ready': True,
            'paper_observation_tier': 'observe',
            'anti_consensus_score': 45,
            'early_demon_trend_score': 78,
            'sector_filter': 'leader',
            'thesis_invalidation': ['1h 跌破启动价 4% 且成交继续放大'],
        },
        {
            'symbol': 'BLOCKED',
            'state': 'NO_TRADE_UNFAIR_GAME',
            'score': 80,
            'last_price': 1.0,
            'paper_observation_tier': 'none',
        },
    ])

    rows = build_paper_trade_rows(scan, now_ts=1700000400, min_score=50)

    assert len(rows) == 1
    row = rows[0]
    assert row['trade_id'] == '1700000400-EARLY-EARLY_DEMON_TREND-observe'
    assert row['mode'] == 'paper_observation'
    assert row['paper_observation_tier'] == 'observe'
    assert row['side'] == 'long'
    assert row['early_demon_trend_score'] == 78
    assert row['thesis_invalidation'] == ['1h 跌破启动价 4% 且成交继续放大']


def test_build_paper_trade_rows_keeps_smart_short_observation_out_of_main_paper_entries():
    scan = _scan([
        {
            'symbol': 'AXS',
            'state': 'SMART_SHORT_PROBE',
            'model': '空头试探观察',
            'direction': '偏空观察',
            'strategy': '观察/等待破位与反抽失败确认',
            'score': 62,
            'last_price': 1.60,
            'atr_1h_pct': 4.0,
            'local_history_ready': True,
            'paper_observation_tier': 'observe',
        },
        {
            'symbol': 'AXS2',
            'state': 'SHORT_CONFIRMING',
            'model': '空头确认中',
            'direction': '偏空观察',
            'strategy': '高优先级观察/等待反抽失败',
            'score': 66,
            'last_price': 1.55,
            'atr_1h_pct': 4.0,
            'local_history_ready': True,
            'paper_observation_tier': 'observe',
        },
    ])

    rows = build_paper_trade_rows(scan, now_ts=1700000500, min_score=50)

    assert len(rows) == 2
    assert {row['mode'] for row in rows} == {'paper_observation'}
    assert {row['state'] for row in rows} == {'SMART_SHORT_PROBE', 'SHORT_CONFIRMING'}
    assert all(row['trade_id'].endswith('-observe') for row in rows)
    assert all(row['side'] == 'short' for row in rows)
    assert all(row['order_execution'] == 'disabled' for row in rows)
