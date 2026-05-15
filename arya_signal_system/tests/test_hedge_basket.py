from __future__ import annotations

import json
from pathlib import Path

from src.strategies.hedge_basket import (
    ORDER_EXECUTION_ENABLED,
    append_hedge_basket_from_scan,
    build_hedge_basket_report,
    build_professional_summary,
    compute_relative_strength_score,
    update_hedge_basket_ledger_results,
)


def test_relative_strength_score_ranks_strong_and_weak_symbols():
    strong = {
        "symbol": "STRONG-USDT-SWAP",
        "return_1h_pct": 4.0,
        "return_4h_pct": 10.0,
        "return_24h_pct": 18.0,
        "volume_change_1h_pct": 90.0,
        "oi_change_1h_pct": 18.0,
        "funding_rate_pct": -0.01,
        "depth_usd": 2_000_000,
        "spread_pct": 0.03,
        "atr_1h_pct": 4.0,
        "fair_game": True,
    }
    weak = {
        "symbol": "WEAK-USDT-SWAP",
        "return_1h_pct": -3.0,
        "return_4h_pct": -8.0,
        "return_24h_pct": -12.0,
        "volume_change_1h_pct": 70.0,
        "oi_change_1h_pct": 12.0,
        "funding_rate_pct": 0.04,
        "depth_usd": 2_000_000,
        "spread_pct": 0.03,
        "atr_1h_pct": 4.0,
        "fair_game": True,
    }

    strong_score = compute_relative_strength_score(strong)
    weak_score = compute_relative_strength_score(weak)

    assert strong_score["bucket"] == "long_candidate"
    assert weak_score["bucket"] == "short_candidate"
    assert strong_score["relative_strength_score"] > 35
    assert weak_score["relative_strength_score"] < -25
    assert "多周期收益强" in strong_score["evidence"]
    assert "弱势下跌" in weak_score["evidence"]


def test_hedge_basket_report_pairs_strong_longs_with_weak_shorts_paper_only():
    markets = [
        {"symbol": "AAA-USDT-SWAP", "return_1h_pct": 5, "return_4h_pct": 11, "return_24h_pct": 20, "volume_change_1h_pct": 80, "oi_change_1h_pct": 20, "funding_rate_pct": -0.01, "depth_usd": 2_000_000, "spread_pct": 0.03, "atr_1h_pct": 4, "fair_game": True, "last_price": 10},
        {"symbol": "BBB-USDT-SWAP", "return_1h_pct": 3, "return_4h_pct": 8, "return_24h_pct": 14, "volume_change_1h_pct": 50, "oi_change_1h_pct": 8, "funding_rate_pct": 0.0, "depth_usd": 1_500_000, "spread_pct": 0.04, "atr_1h_pct": 3, "fair_game": True, "last_price": 20},
        {"symbol": "CCC-USDT-SWAP", "return_1h_pct": -4, "return_4h_pct": -9, "return_24h_pct": -15, "volume_change_1h_pct": 90, "oi_change_1h_pct": 15, "funding_rate_pct": 0.04, "depth_usd": 2_000_000, "spread_pct": 0.03, "atr_1h_pct": 5, "fair_game": True, "last_price": 5},
        {"symbol": "DDD-USDT-SWAP", "return_1h_pct": -2, "return_4h_pct": -7, "return_24h_pct": -11, "volume_change_1h_pct": 40, "oi_change_1h_pct": 9, "funding_rate_pct": 0.03, "depth_usd": 1_800_000, "spread_pct": 0.04, "atr_1h_pct": 4, "fair_game": True, "last_price": 7},
        {"symbol": "PIN-USDT-SWAP", "return_1h_pct": 20, "return_4h_pct": 30, "return_24h_pct": 60, "volume_change_1h_pct": 200, "oi_change_1h_pct": 50, "funding_rate_pct": 0.1, "depth_usd": 20_000, "spread_pct": 0.8, "atr_1h_pct": 30, "fair_game": False, "last_price": 1},
    ]

    report = build_hedge_basket_report(markets, equity_usdt=10000, top_n=2)

    assert report["strategy"] == "long_short_relative_strength_basket"
    assert report["order_execution"] == "disabled"
    assert report["order_execution_enabled"] is False
    assert ORDER_EXECUTION_ENABLED is False
    assert report["mode"] == "paper_observation"
    assert report["requires_manual_confirmation"] is True
    assert report["arya_main_entry_count"] == 0
    assert [x["symbol"] for x in report["long_basket"]] == ["AAA-USDT-SWAP", "BBB-USDT-SWAP"]
    assert [x["symbol"] for x in report["short_basket"]] == ["CCC-USDT-SWAP", "DDD-USDT-SWAP"]
    assert report["basket_plan"]["gross_exposure_usdt"] <= 3000
    assert abs(report["basket_plan"]["net_exposure_usdt"]) <= 1e-9
    assert all(x["symbol"] != "PIN-USDT-SWAP" for x in report["ranked_markets"])
    assert "强弱对冲观察" in report["notes"][0]


def test_append_hedge_basket_from_scan_writes_separate_ledger(tmp_path: Path):
    scan = {
        "source_status": {"order_execution": "disabled"},
        "candidates": [
            {"symbol": "UP-USDT-SWAP", "return_1h_pct": 4, "return_4h_pct": 9, "return_24h_pct": 15, "volume_change_1h_pct": 70, "oi_change_1h_pct": 15, "funding_rate_pct": -0.01, "depth_usd": 2_000_000, "spread_pct": 0.03, "atr_1h_pct": 4, "fair_game": True, "last_price": 10},
            {"symbol": "DOWN-USDT-SWAP", "return_1h_pct": -4, "return_4h_pct": -9, "return_24h_pct": -15, "volume_change_1h_pct": 70, "oi_change_1h_pct": 15, "funding_rate_pct": 0.04, "depth_usd": 2_000_000, "spread_pct": 0.03, "atr_1h_pct": 4, "fair_game": True, "last_price": 5},
        ],
    }
    scan_path = tmp_path / "scan.json"
    ledger = tmp_path / "hedge_basket.jsonl"
    scan_path.write_text(json.dumps(scan), encoding="utf-8")

    result = append_hedge_basket_from_scan(scan_path, ledger, now_ts=1710000000, equity_usdt=10000, top_n=1)

    assert result["appended"] == 1
    assert result["ledger"] == str(ledger)
    row = json.loads(ledger.read_text(encoding="utf-8").strip())
    assert row["mode"] == "paper_observation"
    assert row["order_execution"] == "disabled"
    assert row["arya_main_entry_count"] == 0
    assert row["long_symbols"] == ["UP-USDT-SWAP"]
    assert row["short_symbols"] == ["DOWN-USDT-SWAP"]
    assert row["basket_plan"]["net_exposure_usdt"] == 0
    assert "no API order" in row["notes"]


def test_update_hedge_basket_ledger_results_marks_pnl_funding_drawdown_and_reversal(tmp_path: Path):
    ledger = tmp_path / "hedge_basket.jsonl"
    row = {
        "basket_id": "basket-1",
        "mode": "paper_observation",
        "status": "open_observation",
        "created_ts": 1710000000,
        "strategy": "long_short_relative_strength_basket",
        "order_execution": "disabled",
        "requires_manual_confirmation": True,
        "arya_main_entry_count": 0,
        "long_symbols": ["LONG-USDT-SWAP"],
        "short_symbols": ["SHORT-USDT-SWAP"],
        "basket_plan": {"long_gross_usdt": 1500.0, "short_gross_usdt": 1500.0, "net_exposure_usdt": 0.0},
        "long_basket": [{"symbol": "LONG-USDT-SWAP", "last_price": 100.0, "relative_strength_score": 45.0, "metrics": {"funding_rate_pct": -0.01}}],
        "short_basket": [{"symbol": "SHORT-USDT-SWAP", "last_price": 50.0, "relative_strength_score": -42.0, "metrics": {"funding_rate_pct": 0.04}}],
        "result_1h_pct": None,
        "result_4h_pct": None,
        "result_24h_pct": None,
        "max_drawdown_pct": None,
        "close_reason": None,
    }
    ledger.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    market_snapshot = {
        "candidates": [
            {"symbol": "LONG-USDT-SWAP", "last_price": 110.0, "relative_strength_score": -5.0, "funding_rate_pct": -0.02},
            {"symbol": "SHORT-USDT-SWAP", "last_price": 45.0, "relative_strength_score": 12.0, "funding_rate_pct": 0.02},
        ]
    }
    snapshot_path = tmp_path / "latest.json"
    snapshot_path.write_text(json.dumps(market_snapshot), encoding="utf-8")

    result = update_hedge_basket_ledger_results(
        ledger,
        snapshot_path,
        now_ts=1710003600,
        holding_hours=1.0,
        max_drawdown_stop_pct=-4.0,
        reversal_threshold=0.0,
    )

    assert result["updated"] == 1
    updated = json.loads(ledger.read_text(encoding="utf-8").strip())
    assert updated["result_1h_pct"] == 10.0025
    assert updated["spread_return_pct"] == 10.0
    assert updated["funding_drag_pct"] == 0.0025
    assert updated["net_result_after_funding_pct"] == 10.0025
    assert updated["max_drawdown_pct"] == 0.0
    assert updated["strength_reversal"] is True
    assert updated["status"] == "closed_observation"
    assert updated["close_reason"] == "strength_reversal"
    assert updated["order_execution"] == "disabled"
    assert updated["arya_main_entry_count"] == 0


def test_professional_summary_reports_win_rate_avg_return_and_safety(tmp_path: Path):
    ledger = tmp_path / "hedge_basket.jsonl"
    rows = [
        {"basket_id": "win", "status": "closed_observation", "net_result_after_funding_pct": 4.5, "spread_return_pct": 4.8, "funding_drag_pct": -0.3, "max_drawdown_pct": -1.2, "order_execution": "disabled", "arya_main_entry_count": 0},
        {"basket_id": "loss", "status": "closed_observation", "net_result_after_funding_pct": -2.0, "spread_return_pct": -1.6, "funding_drag_pct": -0.4, "max_drawdown_pct": -3.5, "order_execution": "disabled", "arya_main_entry_count": 0},
        {"basket_id": "open", "status": "open_observation", "net_result_after_funding_pct": None, "order_execution": "disabled", "arya_main_entry_count": 0},
    ]
    ledger.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")

    summary = build_professional_summary(ledger)

    assert summary["strategy"] == "long_short_relative_strength_basket"
    assert summary["mode"] == "paper_observation"
    assert summary["order_execution"] == "disabled"
    assert summary["total_baskets"] == 3
    assert summary["closed_baskets"] == 2
    assert summary["open_baskets"] == 1
    assert summary["win_rate_pct"] == 50.0
    assert summary["avg_net_result_after_funding_pct"] == 1.25
    assert summary["avg_funding_drag_pct"] == -0.35
    assert summary["worst_drawdown_pct"] == -3.5
    assert summary["safety"]["arya_main_entry_count"] == 0
    assert "paper-only" in summary["safety"]["notes"]
