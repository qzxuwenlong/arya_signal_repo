from src.data_sources import build_okx_candidate_from_payloads, select_okx_opportunity_pool


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
