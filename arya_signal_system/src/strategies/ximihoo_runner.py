from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

from .ximihoo_strategy import ORDER_EXECUTION_ENABLED, evaluate_ximihoo_signal, plan_okx_contract_order


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


def build_ximihoo_strategy_report(
    markets: Iterable[Dict[str, Any]],
    account_equity_usdt: float = 0.0,
    source: str | None = None,
) -> Dict[str, Any]:
    """Build a standalone ximihoo1 strategy report.

    Boundary: this report is intentionally separate from Arya main A档 scoring.
    It produces observation/paper plans only, never main Arya paper entries or OKX orders.
    """
    signals: List[Dict[str, Any]] = []
    order_plans: List[Dict[str, Any]] = []

    for market in markets:
        signal = evaluate_ximihoo_signal(market)
        signals.append(signal)
        order_plans.append(plan_okx_contract_order(signal, account_equity_usdt=account_equity_usdt))

    return {
        "strategy": "ximihoo1_standalone",
        "integration_boundary": "separate_from_arya_main",
        "source": source,
        "order_execution": "disabled" if not ORDER_EXECUTION_ENABLED else "enabled",
        "order_execution_enabled": ORDER_EXECUTION_ENABLED,
        "requires_manual_confirmation": True,
        "arya_main_entry_count": 0,
        "notes": [
            "ximihoo1 是独立策略/风控过滤器，不并入 Arya A档主开仓逻辑",
            "所有输出均为观察层或纸面计划，不调用 OKX 下单 API",
        ],
        "signals": signals,
        "order_plans": order_plans,
    }


def run_ximihoo_strategy_file(
    input_json: str,
    output_json: str,
    account_equity_usdt: float = 0.0,
) -> Dict[str, Any]:
    input_path = Path(input_json)
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    markets = _extract_markets(payload)
    report = build_ximihoo_strategy_report(markets, account_equity_usdt=account_equity_usdt, source=str(input_path))
    Path(output_json).parent.mkdir(parents=True, exist_ok=True)
    Path(output_json).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run standalone ximihoo1 OKX contract observation strategy")
    parser.add_argument("--input-json", required=True, help="Market JSON containing candidates/markets/list")
    parser.add_argument("--out", default="runs/ximihoo1_latest.json", help="Output standalone report JSON")
    parser.add_argument("--equity", type=float, default=0.0, help="Paper account equity in USDT")
    args = parser.parse_args(argv)

    report = run_ximihoo_strategy_file(args.input_json, args.out, account_equity_usdt=args.equity)
    print(json.dumps({
        "strategy": report["strategy"],
        "signals": len(report["signals"]),
        "order_execution": report["order_execution"],
        "out": args.out,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
