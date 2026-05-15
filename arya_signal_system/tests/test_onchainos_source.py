import json
import subprocess
from pathlib import Path

import pytest

from src.onchainos_source import (
    DEFAULT_PROXY_ENV,
    build_onchain_observation_pool,
    collect_onchain_candidates,
    normalize_memepump_token,
    normalize_signal_row,
    normalize_trending_token,
    onchain_lookup_from_pool,
    run_onchainos,
    write_onchain_candidates,
)
from src.paper_trade import build_paper_trade_rows


def test_normalize_trending_token_returns_safe_observation_candidate():
    row = {
        'symbol': 'BONK',
        'name': 'Bonk',
        'chain': 'solana',
        'chainIndex': '501',
        'tokenContractAddress': 'DezXAZ8z...',
        'price': '0.0000123',
        'volume': '1250000',
        'liquidity': '500000',
        'marketCap': '890000000',
        'holders': '920000',
        'uniqueTraders': '4200',
        'buyTxs': '700',
        'sellTxs': '350',
        'change': '22.5',
    }

    candidate = normalize_trending_token(row, rank=3, chain='solana')

    assert candidate['symbol'] == 'BONK'
    assert candidate['chain'] == 'solana'
    assert candidate['contract'] == 'DezXAZ8z...'
    assert candidate['source'] == ['trending']
    assert candidate['tier'] == 'C_ONCHAIN_OBSERVE'
    assert candidate['state'] == 'ONCHAIN_OBSERVE'
    assert candidate['allow_trade'] is False
    assert candidate['paper_observation_tier'] == 'observe'
    assert candidate['onchain_trending_rank'] == 3
    assert candidate['onchain_volume_1h_usd'] == 1250000.0
    assert candidate['onchain_unique_traders'] == 4200.0
    assert candidate['onchain_buy_sell_ratio'] == 2.0
    assert candidate['smart_money_signal_count'] == 0
    assert any('链上趋势' in r for r in candidate['reasons'])
    assert any('不是开仓信号' in r for r in candidate['risks'])


def test_normalize_signal_row_adds_smart_money_confirmation_without_trade_permission():
    row = {
        'tokenSymbol': 'MYRO',
        'tokenName': 'Myro',
        'chain': 'solana',
        'tokenContractAddress': 'HhJpBh...',
        'triggerWalletCount': '5',
        'amountUsd': '123456.78',
        'soldRatioPercent': '12.5',
        'top10HolderPercent': '34.2',
        'marketCap': '45000000',
    }

    candidate = normalize_signal_row(row, chain='solana')

    assert candidate['symbol'] == 'MYRO'
    assert candidate['source'] == ['smart_money']
    assert candidate['smart_money_signal_count'] == 5
    assert candidate['smart_money_amount_usd'] == 123456.78
    assert candidate['smart_money_sold_ratio_pct'] == 12.5
    assert candidate['top10_holder_pct'] == 34.2
    assert candidate['allow_trade'] is False
    assert candidate['manual_confirmation_required'] is True
    assert any('Smart Money' in r or '聪明钱' in r for r in candidate['reasons'])


def test_normalize_memepump_token_flags_new_token_as_high_risk_observation():
    row = {
        'symbol': 'NEWPEPE',
        'name': 'New Pepe',
        'chain': 'xlayer',
        'tokenContractAddress': '0xabc',
        'liquidity': '12000',
        'marketCap': '90000',
        'holders': '88',
        'devHoldingPercent': '18',
        'bundlersPercent': '9',
        'snipersPercent': '14',
        'devRugCount': '1',
    }

    candidate = normalize_memepump_token(row, chain='xlayer', stage='NEW')

    assert candidate['source'] == ['memepump_new']
    assert candidate['tier'] == 'C_ONCHAIN_OBSERVE'
    assert candidate['dev_holding_pct'] == 18.0
    assert candidate['bundlers_pct'] == 9.0
    assert candidate['snipers_pct'] == 14.0
    assert candidate['dev_rug_count'] == 1.0
    assert candidate['onchain_fair_game'] is False
    assert candidate['allow_trade'] is False
    assert any('风险' in r or '低流动性' in r or 'dev' in r.lower() for r in candidate['risks'])


def test_build_onchain_observation_pool_merges_sources_and_never_enters_paper_entries():
    trending = normalize_trending_token({'symbol': 'BONK', 'tokenContractAddress': 'mint1', 'volume': 1000, 'buyTxs': 4, 'sellTxs': 2}, rank=1, chain='solana')
    signal = normalize_signal_row({'tokenSymbol': 'BONK', 'tokenContractAddress': 'mint1', 'triggerWalletCount': 2, 'amountUsd': 5000}, chain='solana')
    memepump = normalize_memepump_token({'symbol': 'RUG', 'tokenContractAddress': '0xrug', 'liquidity': 3000, 'devRugCount': 2}, chain='xlayer', stage='NEW')

    pool = build_onchain_observation_pool([trending, signal, memepump], errors=['sample warning'])

    assert pool['source'] == 'okx_onchainos'
    assert pool['order_execution_enabled'] is False
    assert pool['errors'] == ['sample warning']
    assert len(pool['candidates']) == 2
    bonk = next(c for c in pool['candidates'] if c['symbol'] == 'BONK')
    assert bonk['source'] == ['trending', 'smart_money']
    assert bonk['smart_money_signal_count'] == 2
    assert bonk['allow_trade'] is False
    assert bonk['paper_observation_tier'] == 'observe'

    paper_rows = build_paper_trade_rows({'source_status': {'order_execution': 'disabled'}, 'candidates': pool['candidates']}, min_score=1)
    assert paper_rows == []


def test_onchain_lookup_from_pool_keeps_okx_listed_symbols_for_non_social_deep_scan():
    pool = build_onchain_observation_pool([
        normalize_trending_token({'symbol': 'HYPE', 'tokenContractAddress': 'mint-hype', 'volume': 1000}, rank=2, chain='solana'),
        normalize_signal_row({'tokenSymbol': 'AXS', 'tokenContractAddress': 'mint-axs', 'triggerWalletCount': 3, 'amountUsd': 40000}, chain='solana'),
        normalize_trending_token({'symbol': 'PRIVATE', 'tokenContractAddress': 'mint-private', 'volume': 1000}, rank=1, chain='solana'),
    ])

    lookup = onchain_lookup_from_pool(pool, allowed_symbols={'HYPE', 'AXS'})

    assert sorted(lookup) == ['AXS', 'HYPE']
    assert lookup['HYPE']['onchain_observation_score'] > 0
    assert lookup['HYPE']['onchain_sources'] == ['trending']
    assert lookup['AXS']['onchain_sources'] == ['smart_money']
    assert lookup['AXS']['onchain_observation_tier'] == 'C_ONCHAIN_OBSERVE'


def test_run_onchainos_injects_default_proxy_and_returns_error_status_on_timeout(monkeypatch):
    captured = {}

    def fake_run(cmd, *, capture_output, text, timeout, env, check):
        captured['cmd'] = cmd
        captured['env'] = env
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=timeout)

    monkeypatch.setattr(subprocess, 'run', fake_run)

    result = run_onchainos(['token', 'trending', '--chains', 'solana'], timeout=1)

    assert result.status == 'error:timeout'
    assert captured['cmd'][:3] == ['onchainos', 'token', 'trending']
    for key, value in DEFAULT_PROXY_ENV.items():
        assert captured['env'][key] == value


def test_collect_onchain_candidates_uses_runner_fallback_and_writes_stable_json(tmp_path):
    calls = []

    def fake_runner(args, timeout=8):
        calls.append(args)
        if args[:2] == ['token', 'trending']:
            return {'status': 'ok', 'data': [{'symbol': 'BONK', 'tokenContractAddress': 'mint1', 'volume': 1000}]}
        if args[:2] == ['signal', 'list']:
            return {'status': 'error:timeout', 'data': []}
        if args[:2] == ['memepump', 'tokens']:
            return {'status': 'ok', 'data': [{'symbol': 'NEW', 'tokenContractAddress': '0xnew', 'liquidity': 5000}]}
        return {'status': 'error:unexpected', 'data': []}

    pool = collect_onchain_candidates(runner=fake_runner, trending_chains=['solana'], signal_chains=['solana'], memepump_chains=['xlayer'], timeout=2)
    out = tmp_path / 'onchainos_candidates.json'
    write_onchain_candidates(pool, out)
    loaded = json.loads(out.read_text(encoding='utf-8'))

    assert any(call[:2] == ['token', 'trending'] for call in calls)
    assert any(call[:2] == ['signal', 'list'] for call in calls)
    assert any(call[:2] == ['memepump', 'tokens'] for call in calls)
    assert loaded['source_status']['onchainos'].startswith('partial')
    assert loaded['order_execution_enabled'] is False
    assert {c['symbol'] for c in loaded['candidates']} == {'BONK', 'NEW'}
    assert all(c['allow_trade'] is False for c in loaded['candidates'])
    assert loaded['errors']


def test_scanner_can_attach_onchain_pool_without_changing_main_candidates(monkeypatch):
    from src import scanner

    monkeypatch.setattr(scanner, 'load_knowledge_summary', lambda: {'available': True})
    pool = build_onchain_observation_pool([
        normalize_trending_token({'symbol': 'BONK', 'tokenContractAddress': 'mint1', 'volume': 1000}, rank=1, chain='solana')
    ])

    result = scanner.run_scan(limit=1, use_live=False, include_onchain=True, onchain_pool=pool)

    assert result['source_status']['onchainos'] == pool['source_status']['onchainos']
    assert result['onchain_observation_pool']['candidates'][0]['symbol'] == 'BONK'
    assert result['onchain_observation_pool']['candidates'][0]['allow_trade'] is False
    assert [c['symbol'] for c in result['candidates']] == ['BTC']
    assert '链上观察池' in result['report']
    assert 'BONK｜C_ONCHAIN_OBSERVE' in result['report']


def test_scanner_uses_onchain_pool_extra_for_okx_deep_scan_without_social_posts(monkeypatch):
    from src import scanner

    instruments = [{'instId': 'BTC-USDT-SWAP', 'state': 'live'}, {'instId': 'HYPE-USDT-SWAP', 'state': 'live'}, {'instId': 'AXS-USDT-SWAP', 'state': 'live'}]
    tickers = [
        {'instId': 'BTC-USDT-SWAP', 'last': '100000', 'open24h': '100000', 'volCcy24h': '1000000'},
        {'instId': 'HYPE-USDT-SWAP', 'last': '30', 'open24h': '30', 'volCcy24h': '20000'},
        {'instId': 'AXS-USDT-SWAP', 'last': '3', 'open24h': '3', 'volCcy24h': '20000'},
    ]
    pool = build_onchain_observation_pool([
        normalize_trending_token({'symbol': 'HYPE', 'tokenContractAddress': 'mint-hype', 'volume': 1000}, rank=1, chain='solana'),
        normalize_signal_row({'tokenSymbol': 'AXS', 'tokenContractAddress': 'mint-axs', 'triggerWalletCount': 3, 'amountUsd': 40000}, chain='solana'),
    ])
    built = []

    monkeypatch.setattr(scanner, 'load_knowledge_summary', lambda: {'available': True})
    monkeypatch.setattr(scanner, 'fetch_binance_rank', lambda size=50: scanner.SourceResult('disabled', []))
    monkeypatch.setattr(scanner, 'fetch_okx_instruments', lambda limit=1000: scanner.SourceResult('ok', instruments))
    monkeypatch.setattr(scanner, 'fetch_okx_tickers', lambda: scanner.SourceResult('ok', tickers))
    monkeypatch.setattr(scanner, 'build_okx_candidate', lambda inst_id: built.append(inst_id) or {'symbol': inst_id, 'sources': []})

    result = scanner.run_scan(
        limit=1,
        use_live=True,
        include_onchain=True,
        onchain_pool=pool,
        onchain_pool_extra=2,
        social_posts=None,
        social_pool_extra=0,
    )

    assert result['source_status'].get('social_x') is None
    assert result['source_status']['okx_selection'] == 'dynamic_top_3'
    assert built == ['HYPE-USDT-SWAP', 'AXS-USDT-SWAP', 'BTC-USDT-SWAP']
    assert result['candidates'][0]['onchain_observation_score'] > 0
    assert result['candidates'][0]['sources'].count('okx_onchainos') == 1
    assert all(c.get('allow_trade') is not True for c in result['onchain_observation_pool']['candidates'])
