import json
from pathlib import Path

from src.strategies.ximihoo_runner import build_ximihoo_strategy_report, run_ximihoo_strategy_file


def test_ximihoo_strategy_report_is_standalone_and_not_arya_entry():
    markets = [
        {
            "symbol": "BTC-USDT-SWAP",
            "btc_price": 73200,
            "btc_target_low": 75000,
            "btc_target_high": 80000,
            "failed_breakout_reclaim": True,
            "reclaim_strength_pct": 1.6,
            "funding_rate_pct": -0.003,
            "depth_usd": 9000000,
            "spread_pct": 0.01,
        },
        {
            "symbol": "1000PEPE-USDT-SWAP",
            "is_meme": True,
            "return_24h_pct": 60,
            "atr_1h_pct": 12,
            "depth_usd": 30000,
            "spread_pct": 0.4,
        },
    ]

    report = build_ximihoo_strategy_report(markets, account_equity_usdt=10000)

    assert report["strategy"] == "ximihoo1_standalone"
    assert report["integration_boundary"] == "separate_from_arya_main"
    assert report["order_execution"] == "disabled"
    assert report["arya_main_entry_count"] == 0
    assert len(report["signals"]) == 2
    assert all(s["strategy"] == "ximihoo1_cycle_filter" for s in report["signals"])
    assert all(s["allow_trade"] is False for s in report["signals"])
    assert report["order_plans"][0]["mode"] == "paper"
    assert report["order_plans"][0]["requires_manual_confirmation"] is True


def test_ximihoo_runner_reads_json_and_writes_separate_report(tmp_path):
    input_path = tmp_path / "markets.json"
    output_path = tmp_path / "ximihoo_report.json"
    input_path.write_text(json.dumps({"candidates": [{"symbol": "ETH-USDT-SWAP", "btc_price": 79000, "btc_target_low": 75000, "btc_target_high": 80000}]}), encoding="utf-8")

    result = run_ximihoo_strategy_file(str(input_path), str(output_path), account_equity_usdt=5000)

    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert result["strategy"] == "ximihoo1_standalone"
    assert saved["strategy"] == "ximihoo1_standalone"
    assert saved["source"] == str(input_path)
    assert saved["signals"][0]["state"] == "BTC_TARGET_RISK"
    assert saved["signals"][0]["allow_trade"] is False
