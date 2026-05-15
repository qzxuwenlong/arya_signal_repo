from src.data_sources import (
    build_okx_candidate_from_payloads,
)
from src.pool_selection import (
    extract_social_tickers,
    select_okx_opportunity_pool,
)


def _inst(inst_id):
    return {'instId': inst_id, 'state': 'live'}


def _ticker(inst_id, last, open24h, vol_ccy_24h, vol_ccy_quote_24h=0):
    return {
        'instId': inst_id,
        'last': str(last),
        'open24h': str(open24h),
        'volCcy24h': str(vol_ccy_24h),
        'volCcyQuote24h': str(vol_ccy_quote_24h),
    }


def test_select_okx_opportunity_pool_prefers_dynamic_hot_symbols_over_fixed_majors():
    instruments = [
        _inst('BTC-USDT-SWAP'),
        _inst('ETH-USDT-SWAP'),
        _inst('BOME-USDT-SWAP'),
        _inst('WIF-USDT-SWAP'),
        _inst('NEIRO-USDT-SWAP'),
    ]
    tickers = [
        _ticker('BTC-USDT-SWAP', 100000, 99000, 1_000),
        _ticker('ETH-USDT-SWAP', 3000, 2990, 1_000),
        _ticker('BOME-USDT-SWAP', 0.0012, 0.0010, 20_000_000),
        _ticker('WIF-USDT-SWAP', 2.4, 2.0, 18_000_000),
        _ticker('NEIRO-USDT-SWAP', 0.1, 0.07, 15_000_000),
    ]
    rank_lookup = {'NEIRO': {'binance_hype_rank': 3}, 'WIF': {'binance_hype_rank': 7}}

    pool = select_okx_opportunity_pool(instruments, tickers, rank_lookup=rank_lookup, limit=3)

    assert [x['inst_id'] for x in pool] == ['NEIRO-USDT-SWAP', 'WIF-USDT-SWAP', 'BOME-USDT-SWAP']
    assert all(x['selection_score'] > 0 for x in pool)
    assert pool[0]['binance_hype_rank'] == 3


def test_select_okx_opportunity_pool_can_fallback_to_tickers_when_instruments_fail():
    tickers = [
        _ticker('BTC-USDT-SWAP', 100000, 99000, 1_000),
        _ticker('BOME-USDT-SWAP', 0.0012, 0.0010, 20_000_000),
    ]

    pool = select_okx_opportunity_pool([], tickers, limit=1)

    assert [x['inst_id'] for x in pool] == ['BOME-USDT-SWAP']


def test_select_okx_opportunity_pool_boosts_social_mentions_with_aliases():
    instruments = [_inst('HYPE-USDT-SWAP'), _inst('AXS-USDT-SWAP'), _inst('BTC-USDT-SWAP')]
    tickers = [
        _ticker('HYPE-USDT-SWAP', 30, 30, 20_000),
        _ticker('AXS-USDT-SWAP', 3, 3, 20_000),
        _ticker('BTC-USDT-SWAP', 100000, 100000, 1_000_000),
    ]
    social_lookup = {
        'HYPE': {'social_mention_count': 2, 'social_aliases': ['HYPER']},
        'AXS': {'social_mention_count': 1},
    }

    pool = select_okx_opportunity_pool(
        instruments,
        tickers,
        social_lookup=social_lookup,
        limit=2,
        min_24h_volume_usd=50_000,
    )

    assert [x['inst_id'] for x in pool] == ['HYPE-USDT-SWAP', 'AXS-USDT-SWAP']
    assert pool[0]['social_mention_count'] == 2
    assert pool[1]['social_mention_count'] == 1


def test_select_okx_opportunity_pool_boosts_onchain_candidates_without_social_dependency():
    instruments = [_inst('HYPE-USDT-SWAP'), _inst('AXS-USDT-SWAP'), _inst('BTC-USDT-SWAP')]
    tickers = [
        _ticker('HYPE-USDT-SWAP', 30, 30, 20_000),
        _ticker('AXS-USDT-SWAP', 3, 3, 20_000),
        _ticker('BTC-USDT-SWAP', 100000, 100000, 1_000_000),
    ]
    onchain_lookup = {
        'HYPE': {'onchain_observation_score': 43, 'onchain_sources': ['trending', 'smart_money']},
        'AXS': {'onchain_observation_score': 31, 'onchain_sources': ['trending']},
    }

    pool = select_okx_opportunity_pool(
        instruments,
        tickers,
        onchain_lookup=onchain_lookup,
        limit=2,
        min_24h_volume_usd=50_000,
    )

    assert [x['inst_id'] for x in pool] == ['HYPE-USDT-SWAP', 'AXS-USDT-SWAP']
    assert pool[0]['onchain_observation_score'] == 43
    assert pool[0]['onchain_sources'] == ['trending', 'smart_money']
    assert pool[1]['onchain_observation_score'] == 31


def test_extract_social_tickers_recognizes_cashtags_lowercase_and_hyper_alias():
    tweets = [
        {'text': '$hyper 负费率拉满，OI 在增加'},
        {'text': '$AXS 这个多空比还不错'},
        {'text': 'hype 还能看，但不是开仓信号'},
    ]

    lookup = extract_social_tickers(tweets, symbol_aliases={'HYPER': 'HYPE'}, allowed_symbols={'HYPE', 'AXS'})

    assert lookup['HYPE']['social_mention_count'] == 2
    assert lookup['HYPE']['social_aliases'] == ['HYPER']
    assert lookup['AXS']['social_mention_count'] == 1


def test_build_okx_candidate_from_payloads_records_volume_1h_usd():
    ticker = _ticker('BOME-USDT-SWAP', 0.0012, 0.0010, 20_000_000)
    candles = [
        ['1000', '0.0010', '0.0013', '0.0010', '0.0012', '100000', '120000', '240000', '0'],
        ['0', '0.0010', '0.0011', '0.0009', '0.0010', '50000', '50000', '100000', '0'],
    ]
    book = {
        'bids': [['0.00119', '1000000'], ['0.00118', '1000000']],
        'asks': [['0.00121', '1000000'], ['0.00122', '1000000']],
    }
    oi = {'oiUsd': '1500000'}
    funding = {'fundingRate': '-0.0002'}

    c = build_okx_candidate_from_payloads('BOME-USDT-SWAP', ticker, candles, book, oi, funding)

    assert c['symbol'] == 'BOME-USDT-SWAP'
    assert c['volume_1h'] == 240000.0
    assert c['volume_change_1h_pct'] == 140.0
    assert c['open_interest_usd'] == 1500000.0
    assert c['funding_rate_pct'] == -0.02
