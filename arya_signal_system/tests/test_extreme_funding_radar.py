import importlib.util
from pathlib import Path

radar_path = Path('/home/hpp/okx_extreme_funding_radar.py')
spec = importlib.util.spec_from_file_location('okx_extreme_funding_radar', radar_path)
radar = importlib.util.module_from_spec(spec)
spec.loader.exec_module(radar)
render_markdown = radar.render_markdown
scan_extreme_funding = radar.scan_extreme_funding


def test_extreme_funding_scan_filters_and_ranks(monkeypatch):
    tickers = [
        {'instId': 'HOT-USDT-SWAP', 'last': '1.20', 'open24h': '1.00', 'volCcyQuote24h': '1000000'},
        {'instId': 'MILD-USDT-SWAP', 'last': '1.01', 'open24h': '1.00', 'volCcyQuote24h': '1000000'},
        {'instId': 'LOWVOL-USDT-SWAP', 'last': '2', 'open24h': '1', 'volCcyQuote24h': '100'},
    ]

    monkeypatch.setattr(radar, 'fetch_okx_usdt_swap_tickers', lambda: tickers)
    monkeypatch.setattr(radar, 'fetch_okx_funding', lambda inst_id: {
        'HOT-USDT-SWAP': {'fundingRate': '0.0012', 'fundingTime': '1', 'nextFundingTime': '2'},
        'MILD-USDT-SWAP': {'fundingRate': '0.0001', 'fundingTime': '1', 'nextFundingTime': '2'},
    }[inst_id])

    result = scan_extreme_funding(min_abs_funding_pct=0.05, top_n=5, max_prefetch=5, min_volume_24h=50000)
    assert len(result['alerts']) == 1
    assert result['alerts'][0]['inst_id'] == 'HOT-USDT-SWAP'
    assert result['alerts'][0]['funding_rate_pct'] == 0.12
    assert result['order_execution'] == 'disabled'
    md = render_markdown(result)
    assert '只预警' in md
    assert 'HOT-USDT-SWAP' in md
