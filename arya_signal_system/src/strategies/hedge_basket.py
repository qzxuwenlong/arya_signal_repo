from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

ORDER_EXECUTION_ENABLED = False


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _symbol(market: Dict[str, Any]) -> str:
    return str(market.get("symbol") or market.get("instId") or "UNKNOWN").upper()


def _is_tradeable_observation(market: Dict[str, Any]) -> bool:
    if market.get("allow_trade") is False and str(market.get("tier") or "") == "C_ONCHAIN_OBSERVE":
        return False
    if market.get("fair_game") is False:
        return False
    if str(market.get("state") or "") in {
        "NO_TRADE_UNFAIR_GAME",
        "NO_CHASE_GUILLOTINE",
        "EXIT_RISK",
        "MEME_CONTRACT_BANNED",
    }:
        return False
    depth = _num(market.get("depth_usd"))
    spread = _num(market.get("spread_pct"))
    atr = abs(_num(market.get("atr_1h_pct")))
    if depth and depth < 100_000:
        return False
    if spread and spread > 0.30:
        return False
    if atr and atr > 18.0:
        return False
    return True


def compute_relative_strength_score(market: Dict[str, Any]) -> Dict[str, Any]:
    """Score one market for long/short basket observation.

    Positive score means relative strength / possible long leg. Negative score means
    relative weakness / possible short leg. This is not a standalone trade signal.
    """
    r1 = _num(market.get("return_1h_pct") or market.get("price_change_1h_pct"))
    r4 = _num(market.get("return_4h_pct"))
    r24 = _num(market.get("return_24h_pct") or market.get("price_change_24h_pct"))
    vol = _num(market.get("volume_change_1h_pct"))
    oi = _num(market.get("oi_change_1h_pct"))
    funding = _num(market.get("funding_rate_pct"))
    range_pos = _num(market.get("range_position_24h_pct"), 50.0)
    trend = _num(market.get("trend_strength"))

    momentum = r1 * 3.0 + r4 * 1.8 + r24 * 0.7
    participation = min(max(vol, -50.0), 150.0) * 0.08 + min(max(oi, -30.0), 60.0) * 0.22
    funding_adj = 0.0
    evidence: List[str] = []
    risks: List[str] = []

    if r1 > 0 and r4 > 0 and r24 > 0:
        evidence.append("多周期收益强")
    if r1 < 0 and r4 < 0 and r24 < 0:
        evidence.append("弱势下跌")
    if vol > 30:
        evidence.append("成交放大")
    if oi > 8:
        evidence.append("OI 增长")
    if trend > 0:
        evidence.append("趋势强度为正")

    # Negative funding while price is strong can mean shorts are fuel; positive
    # funding while price is weak can mean crowded longs are fuel for downside.
    if funding < -0.005 and r1 >= 0 and r4 >= 0:
        funding_adj += 6.0
        evidence.append("负费率但价格抗住，空头可能是燃料")
    elif funding > 0.02 and r1 <= 0 and r4 <= 0:
        funding_adj -= 6.0
        evidence.append("正费率但价格走弱，多头可能是燃料")
    elif funding > 0.05 and r24 > 10:
        funding_adj -= 5.0
        risks.append("强势但资金费率拥挤，防追高")

    if range_pos > 92 and r1 < 0:
        risks.append("高位回落，可能进入收网风险")
        funding_adj -= 4.0

    score = momentum + participation + funding_adj
    if not _is_tradeable_observation(market):
        risks.append("流动性/公平场不足，剔除篮子")

    if score >= 18:
        bucket = "long_candidate"
    elif score <= -18:
        bucket = "short_candidate"
    else:
        bucket = "neutral"

    return {
        "symbol": _symbol(market),
        "relative_strength_score": round(score, 4),
        "bucket": bucket,
        "evidence": evidence,
        "risks": risks,
        "metrics": {
            "return_1h_pct": r1,
            "return_4h_pct": r4,
            "return_24h_pct": r24,
            "volume_change_1h_pct": vol,
            "oi_change_1h_pct": oi,
            "funding_rate_pct": funding,
            "range_position_24h_pct": range_pos,
        },
        "last_price": _num(market.get("last_price") or market.get("price")),
        "tradeable_observation": _is_tradeable_observation(market),
    }


def _extract_markets(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [m for m in payload if isinstance(m, dict)]
    if isinstance(payload, dict):
        for key in ("candidates", "markets", "signals"):
            value = payload.get(key)
            if isinstance(value, list):
                return [m for m in value if isinstance(m, dict)]
        return [payload]
    return []


def _market_lookup(payload: Any) -> Dict[str, Dict[str, Any]]:
    return {_symbol(m): m for m in _extract_markets(payload)}


def _entry_price(leg: Dict[str, Any]) -> float:
    return _num(leg.get("entry_price") or leg.get("last_price") or leg.get("price"))


def _current_price(symbol: str, market_lookup: Dict[str, Dict[str, Any]]) -> float:
    market = market_lookup.get(symbol, {})
    return _num(market.get("last_price") or market.get("price") or market.get("mark_price"))


def _avg(values: Iterable[float]) -> float:
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else 0.0


def _side_returns(row: Dict[str, Any], market_lookup: Dict[str, Dict[str, Any]]) -> Dict[str, List[float]]:
    long_returns: List[float] = []
    short_returns: List[float] = []
    for leg in row.get("long_basket", []) or []:
        sym = str(leg.get("symbol") or "").upper()
        entry = _entry_price(leg)
        current = _current_price(sym, market_lookup)
        if entry > 0 and current > 0:
            long_returns.append((current - entry) / entry * 100.0)
    for leg in row.get("short_basket", []) or []:
        sym = str(leg.get("symbol") or "").upper()
        entry = _entry_price(leg)
        current = _current_price(sym, market_lookup)
        if entry > 0 and current > 0:
            short_returns.append((entry - current) / entry * 100.0)
    return {"long": long_returns, "short": short_returns}


def _funding_drag_pct(row: Dict[str, Any], market_lookup: Dict[str, Dict[str, Any]], holding_hours: float) -> float:
    """Approximate funding effect as pct of side capital.

    Positive funding helps shorts and hurts longs; negative funding helps longs and hurts shorts.
    funding_rate_pct is treated as one 8h funding interval. This is deliberately conservative
    and only for paper observation analytics.
    """
    interval_factor = max(holding_hours, 0.0) / 8.0
    long_effects: List[float] = []
    short_effects: List[float] = []
    for leg in row.get("long_basket", []) or []:
        sym = str(leg.get("symbol") or "").upper()
        current = market_lookup.get(sym, {})
        funding = _num(current.get("funding_rate_pct"), _num((leg.get("metrics") or {}).get("funding_rate_pct")))
        long_effects.append(-funding * interval_factor)
    for leg in row.get("short_basket", []) or []:
        sym = str(leg.get("symbol") or "").upper()
        current = market_lookup.get(sym, {})
        funding = _num(current.get("funding_rate_pct"), _num((leg.get("metrics") or {}).get("funding_rate_pct")))
        short_effects.append(funding * interval_factor)
    if not long_effects and not short_effects:
        return 0.0
    return _avg(long_effects + short_effects)


def _strength_reversal(row: Dict[str, Any], market_lookup: Dict[str, Dict[str, Any]], threshold: float) -> bool:
    reversals = 0
    checks = 0
    for leg in row.get("long_basket", []) or []:
        sym = str(leg.get("symbol") or "").upper()
        market = market_lookup.get(sym, {})
        if "relative_strength_score" in market:
            checks += 1
            reversals += 1 if _num(market.get("relative_strength_score")) <= threshold else 0
    for leg in row.get("short_basket", []) or []:
        sym = str(leg.get("symbol") or "").upper()
        market = market_lookup.get(sym, {})
        if "relative_strength_score" in market:
            checks += 1
            reversals += 1 if _num(market.get("relative_strength_score")) >= -threshold else 0
    return checks > 0 and reversals >= max(1, checks // 2)


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def _write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in rows) + ("\n" if rows else ""), encoding="utf-8")


def update_hedge_basket_ledger_results(
    ledger_path: str | Path,
    market_snapshot_path: str | Path,
    *,
    now_ts: int | None = None,
    holding_hours: float | None = None,
    max_drawdown_stop_pct: float = -6.0,
    reversal_threshold: float = 0.0,
) -> Dict[str, Any]:
    ledger_path = Path(ledger_path)
    snapshot_payload = json.loads(Path(market_snapshot_path).read_text(encoding="utf-8"))
    markets = _market_lookup(snapshot_payload)
    rows = _read_jsonl(ledger_path)
    now_ts = int(time.time()) if now_ts is None else int(now_ts)
    updated = 0
    closed = 0

    for row in rows:
        if row.get("status") not in {"open_observation", "open"}:
            continue
        elapsed_hours = holding_hours
        if elapsed_hours is None:
            elapsed_hours = max((now_ts - int(row.get("created_ts") or now_ts)) / 3600.0, 0.0)
        side_returns = _side_returns(row, markets)
        if not side_returns["long"] and not side_returns["short"]:
            continue
        long_avg = _avg(side_returns["long"])
        short_avg = _avg(side_returns["short"])
        spread_return = _avg([long_avg, short_avg])
        funding_drag = _funding_drag_pct(row, markets, elapsed_hours)
        net_after_funding = spread_return + funding_drag
        previous_dd = row.get("max_drawdown_pct")
        max_drawdown = min(_num(previous_dd, 0.0), net_after_funding)
        reversal = _strength_reversal(row, markets, reversal_threshold)
        close_reason = None
        status = "open_observation"
        if max_drawdown <= max_drawdown_stop_pct:
            close_reason = "max_drawdown_stop"
            status = "closed_observation"
        elif reversal:
            close_reason = "strength_reversal"
            status = "closed_observation"
        elif elapsed_hours >= 24:
            close_reason = "time_stop_24h"
            status = "closed_observation"

        result_key = "result_24h_pct" if elapsed_hours >= 24 else "result_4h_pct" if elapsed_hours >= 4 else "result_1h_pct"
        row.update({
            result_key: round(net_after_funding, 4),
            "spread_return_pct": round(spread_return, 4),
            "long_leg_return_pct": round(long_avg, 4),
            "short_leg_return_pct": round(short_avg, 4),
            "funding_drag_pct": round(funding_drag, 4),
            "net_result_after_funding_pct": round(net_after_funding, 4),
            "max_drawdown_pct": round(max_drawdown, 4),
            "strength_reversal": reversal,
            "last_update_ts": now_ts,
            "last_update_utc": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(now_ts)),
            "holding_hours": round(elapsed_hours, 4),
            "status": status,
            "close_reason": close_reason,
            "order_execution": "disabled" if not ORDER_EXECUTION_ENABLED else "enabled",
            "arya_main_entry_count": 0,
        })
        updated += 1
        closed += 1 if status == "closed_observation" else 0

    _write_jsonl(ledger_path, rows)
    return {"updated": updated, "closed": closed, "ledger": str(ledger_path), "order_execution": "disabled"}


def build_professional_summary(ledger_path: str | Path) -> Dict[str, Any]:
    rows = _read_jsonl(Path(ledger_path))
    closed_rows = [r for r in rows if r.get("status") == "closed_observation" and r.get("net_result_after_funding_pct") is not None]
    open_rows = [r for r in rows if str(r.get("status") or "").startswith("open")]
    net_results = [_num(r.get("net_result_after_funding_pct")) for r in closed_rows]
    spread_results = [_num(r.get("spread_return_pct")) for r in closed_rows]
    funding_drags = [_num(r.get("funding_drag_pct")) for r in closed_rows]
    drawdowns = [_num(r.get("max_drawdown_pct")) for r in closed_rows if r.get("max_drawdown_pct") is not None]
    wins = [x for x in net_results if x > 0]
    return {
        "strategy": "long_short_relative_strength_basket",
        "mode": "paper_observation",
        "order_execution": "disabled" if not ORDER_EXECUTION_ENABLED else "enabled",
        "total_baskets": len(rows),
        "closed_baskets": len(closed_rows),
        "open_baskets": len(open_rows),
        "win_rate_pct": round(len(wins) / len(closed_rows) * 100.0, 4) if closed_rows else 0.0,
        "avg_net_result_after_funding_pct": round(_avg(net_results), 4),
        "avg_spread_return_pct": round(_avg(spread_results), 4),
        "avg_funding_drag_pct": round(_avg(funding_drags), 4),
        "worst_drawdown_pct": round(min(drawdowns), 4) if drawdowns else 0.0,
        "safety": {
            "order_execution": "disabled",
            "order_execution_enabled": ORDER_EXECUTION_ENABLED,
            "arya_main_entry_count": 0,
            "requires_manual_confirmation": True,
            "notes": "paper-only observation analytics; no OKX API order; not Arya main A-tier entry",
        },
    }


def _leg_plan(symbols: List[str], equity_usdt: float, gross_fraction: float) -> Dict[str, Any]:
    count = max(len(symbols), 1)
    gross = max(equity_usdt, 0.0) * gross_fraction
    side_gross = gross / 2.0
    per_symbol = side_gross / count
    return {"side_gross_usdt": round(side_gross, 4), "per_symbol_usdt": round(per_symbol, 4)}


def build_hedge_basket_report(
    markets: Iterable[Dict[str, Any]],
    *,
    equity_usdt: float = 0.0,
    top_n: int = 2,
    gross_fraction: float = 0.30,
    source: str | None = None,
) -> Dict[str, Any]:
    ranked = [compute_relative_strength_score(m) for m in markets]
    ranked = [r for r in ranked if r["tradeable_observation"]]
    ranked.sort(key=lambda x: x["relative_strength_score"], reverse=True)

    long_basket = [r for r in ranked if r["bucket"] == "long_candidate"][:top_n]
    short_basket = sorted(
        [r for r in ranked if r["bucket"] == "short_candidate"],
        key=lambda x: x["relative_strength_score"],
    )[:top_n]

    long_symbols = [r["symbol"] for r in long_basket]
    short_symbols = [r["symbol"] for r in short_basket]
    gross_exposure = max(equity_usdt, 0.0) * gross_fraction if long_symbols and short_symbols else 0.0
    long_plan = _leg_plan(long_symbols, equity_usdt, gross_fraction) if long_symbols else {"side_gross_usdt": 0.0, "per_symbol_usdt": 0.0}
    short_plan = _leg_plan(short_symbols, equity_usdt, gross_fraction) if short_symbols else {"side_gross_usdt": 0.0, "per_symbol_usdt": 0.0}

    return {
        "strategy": "long_short_relative_strength_basket",
        "mode": "paper_observation",
        "source": source,
        "order_execution": "disabled" if not ORDER_EXECUTION_ENABLED else "enabled",
        "order_execution_enabled": ORDER_EXECUTION_ENABLED,
        "requires_manual_confirmation": True,
        "arya_main_entry_count": 0,
        "notes": [
            "强弱对冲观察：多相对强、空相对弱，先只做纸面篮子，不调用 OKX 下单 API",
            "同币同仓位锁仓不是盈利模型；该模块跟踪的是相对强弱差、资金费率/拥挤度和组合净敞口",
        ],
        "long_basket": long_basket,
        "short_basket": short_basket,
        "ranked_markets": ranked,
        "basket_plan": {
            "gross_exposure_usdt": round(gross_exposure, 4),
            "long_gross_usdt": long_plan["side_gross_usdt"],
            "short_gross_usdt": short_plan["side_gross_usdt"],
            "long_per_symbol_usdt": long_plan["per_symbol_usdt"],
            "short_per_symbol_usdt": short_plan["per_symbol_usdt"],
            "net_exposure_usdt": round(long_plan["side_gross_usdt"] - short_plan["side_gross_usdt"], 4),
            "gross_fraction": gross_fraction,
        },
    }


def append_hedge_basket_from_scan(
    scan_path: str | Path,
    ledger_path: str | Path,
    *,
    now_ts: int | None = None,
    equity_usdt: float = 0.0,
    top_n: int = 2,
) -> Dict[str, Any]:
    scan_path = Path(scan_path)
    ledger_path = Path(ledger_path)
    payload = json.loads(scan_path.read_text(encoding="utf-8"))
    report = build_hedge_basket_report(_extract_markets(payload), equity_usdt=equity_usdt, top_n=top_n, source=str(scan_path))
    now_ts = int(time.time()) if now_ts is None else int(now_ts)
    row = {
        "basket_id": f"{now_ts}-long-short-relative-strength",
        "mode": report["mode"],
        "status": "open_observation",
        "created_ts": now_ts,
        "created_at_utc": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(now_ts)),
        "strategy": report["strategy"],
        "order_execution": report["order_execution"],
        "requires_manual_confirmation": True,
        "arya_main_entry_count": 0,
        "long_symbols": [x["symbol"] for x in report["long_basket"]],
        "short_symbols": [x["symbol"] for x in report["short_basket"]],
        "basket_plan": report["basket_plan"],
        "long_basket": report["long_basket"],
        "short_basket": report["short_basket"],
        "notes": "paper only; no API order; manual confirmation required for any real trade",
        "result_1h_pct": None,
        "result_4h_pct": None,
        "result_24h_pct": None,
        "max_drawdown_pct": None,
        "close_reason": None,
    }
    appendable = bool(row["long_symbols"] and row["short_symbols"])
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    if appendable:
        with ledger_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return {"appended": 1 if appendable else 0, "ledger": str(ledger_path), "longs": len(row["long_symbols"]), "shorts": len(row["short_symbols"])}


def run_hedge_basket_file(input_json: str, output_json: str, *, equity_usdt: float = 0.0, top_n: int = 2) -> Dict[str, Any]:
    input_path = Path(input_json)
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    report = build_hedge_basket_report(_extract_markets(payload), equity_usdt=equity_usdt, top_n=top_n, source=str(input_path))
    out = Path(output_json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run paper-only long/short relative-strength basket observation")
    parser.add_argument("--input-json", default="runs/latest.json")
    parser.add_argument("--out", default="runs/hedge_basket_latest.json")
    parser.add_argument("--ledger", default="runs/hedge_basket_paper.jsonl")
    parser.add_argument("--equity", type=float, default=10_000.0)
    parser.add_argument("--top-n", type=int, default=2)
    parser.add_argument("--append-ledger", action="store_true")
    parser.add_argument("--update-ledger", action="store_true", help="Update open paper baskets using --input-json as latest market snapshot")
    parser.add_argument("--summary", action="store_true", help="Print professional paper-performance summary from --ledger")
    args = parser.parse_args(argv)

    report = run_hedge_basket_file(args.input_json, args.out, equity_usdt=args.equity, top_n=args.top_n)
    result = {"appended": 0, "ledger": args.ledger}
    update_result = {"updated": 0, "closed": 0}
    summary = None
    if args.append_ledger:
        result = append_hedge_basket_from_scan(args.input_json, args.ledger, equity_usdt=args.equity, top_n=args.top_n)
    if args.update_ledger:
        update_result = update_hedge_basket_ledger_results(args.ledger, args.input_json)
    if args.summary:
        summary = build_professional_summary(args.ledger)
    output = {
        "strategy": report["strategy"],
        "mode": report["mode"],
        "longs": len(report["long_basket"]),
        "shorts": len(report["short_basket"]),
        "order_execution": report["order_execution"],
        "out": args.out,
        "ledger_appended": result["appended"],
        "ledger_updated": update_result["updated"],
        "ledger_closed": update_result["closed"],
    }
    if summary is not None:
        output["summary"] = summary
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
