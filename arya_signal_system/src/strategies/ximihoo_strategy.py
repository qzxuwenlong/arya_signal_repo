from __future__ import annotations

from typing import Any, Dict, List

ORDER_EXECUTION_ENABLED = False
MAJOR_SYMBOL_PREFIXES = ("BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "AVAX", "LINK")


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _base_symbol(symbol: str) -> str:
    return str(symbol or "").split("-")[0].upper()


def _is_major(symbol: str) -> bool:
    base = _base_symbol(symbol)
    return base in MAJOR_SYMBOL_PREFIXES


def _is_meme_like(market: Dict[str, Any]) -> bool:
    if _bool(market.get("is_meme")):
        return True
    base = _base_symbol(market.get("symbol", ""))
    meme_keys = ("PEPE", "BONK", "FLOKI", "SHIB", "DOG", "MEME", "TURBO", "WIF")
    return base.startswith("1000") or any(k in base for k in meme_keys)


def _btc_target_risk(market: Dict[str, Any]) -> bool:
    btc = _num(market.get("btc_price"))
    low = _num(market.get("btc_target_low"), 75_000)
    high = _num(market.get("btc_target_high"), 80_000)
    return low > 0 and high >= low and low <= btc <= high


def evaluate_ximihoo_signal(market: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate ximihoo1-style cycle/risk filter for OKX swap candidates.

    This module intentionally returns paper/observation advice only. It does not
    call OKX trading APIs and never enables live order execution.
    """
    symbol = str(market.get("symbol") or market.get("instId") or "")
    ret_24h = _num(market.get("return_24h_pct") or market.get("price_change_24h_pct"))
    ret_1h = _num(market.get("return_1h_pct") or market.get("price_change_1h_pct"))
    range_pos = _num(market.get("range_position_24h_pct"), 50)
    alt_vs_btc = _num(market.get("alt_vs_btc_24h_pct"))
    funding = _num(market.get("funding_rate_pct"))
    oi = _num(market.get("oi_change_1h_pct"))
    long_liq = _num(market.get("long_liq_1h_usd"))
    short_liq = _num(market.get("short_liq_1h_usd"))
    depth = _num(market.get("depth_usd"))
    spread = _num(market.get("spread_pct"))
    atr = _num(market.get("atr_1h_pct"))
    top10 = _num(market.get("top10_holder_pct"))

    risks: List[str] = []
    reasons: List[str] = []
    risk_score = 0
    opportunity_score = 0
    state = "OBSERVE"
    direction = "observe"
    paper_trade_only = True

    btc_risk = _btc_target_risk(market)
    if btc_risk:
        risk_score += 25
        risks.append("BTC 已进入目标/风险区间，ximihoo1 框架禁止盲目追高")

    if _is_meme_like(market) and (ret_24h >= 40 or atr >= 8 or (0 < depth < 80_000) or spread >= 0.25 or top10 >= 65):
        risks.append("妖币/土狗合约禁入：涨幅、ATR、深度、点差或筹码集中度使合约场不公平")
        return _result(symbol, "MEME_CONTRACT_BANNED", "flat", 100, 0, reasons, risks, False, paper_trade_only)

    if market.get("liq_1d_bias") and market.get("liq_30d_bias") and market.get("liq_1d_bias") != market.get("liq_30d_bias"):
        risks.append("1D/30D 清算方向冲突：短线与中线燃料不一致，不做单向重仓")
        risk_score += 35
        return _result(symbol, "LIQUIDATION_CONFLICT", "observe", risk_score, opportunity_score, reasons, risks, False, paper_trade_only)

    if _bool(market.get("kdj_top_divergence")) or _bool(market.get("macd_top_divergence")):
        risks.append("KDJ/MACD 顶背离：指标下行但价格新高，优先退出多头而不是自动追空")
        risk_score += 35
        if btc_risk:
            risk_score += 15
        return _result(symbol, "TECHNICAL_DIVERGENCE_EXIT_RISK", "flat", risk_score, opportunity_score, reasons, risks, False, paper_trade_only)

    chasing = ret_24h >= 12 and ret_1h >= 3 and range_pos >= 80
    if chasing:
        risk_score += 20
        risks.append("价格处于 24h 高位且短线拉升，属于追高结构")
    if alt_vs_btc <= -2 and symbol and _base_symbol(symbol) != "BTC":
        risk_score += 15
        risks.append("山寨弱于 BTC，反弹不跟涨时后续补跌风险更高")
    if funding >= 0.04 and oi >= 10:
        risk_score += 15
        risks.append("正费率/OI 偏拥挤，多头尾部风险升高")
    if long_liq > max(short_liq * 2, 1) and long_liq >= 100_000:
        risk_score += 10
        risks.append("多头清算燃料偏大，高位破位可能杀多")

    if risk_score >= 45:
        return _result(symbol, "NO_CHASE_EXIT_RISK", "flat", risk_score, opportunity_score, reasons, risks, False, paper_trade_only)

    reclaim = _bool(market.get("failed_breakout_reclaim")) and _num(market.get("reclaim_strength_pct")) >= 1.0
    if reclaim and _is_major(symbol) and not btc_risk:
        opportunity_score += 35
        reasons.append("失败突破/假跌破后快速收回：甩掉弱手并重置仓位，主流币可做纸面顺势多观察")
        if -0.02 <= funding <= 0.02:
            opportunity_score += 8
            reasons.append("资金费率未拥挤，追多尾部风险较低")
        if depth >= 500_000 and spread <= 0.08:
            opportunity_score += 7
            reasons.append("OKX 合约深度/点差允许小仓试错")
        return _result(symbol, "FAILED_BREAKOUT_RECLAIM_LONG", "long", risk_score, opportunity_score, reasons, risks, False, paper_trade_only)

    if btc_risk:
        return _result(symbol, "BTC_TARGET_RISK", "flat", risk_score, opportunity_score, reasons, risks, False, paper_trade_only)

    return _result(symbol, state, direction, risk_score, opportunity_score, reasons, risks, False, paper_trade_only)


def _result(symbol: str, state: str, direction: str, risk_score: float, opportunity_score: float,
            reasons: List[str], risks: List[str], allow_trade: bool, paper_trade_only: bool) -> Dict[str, Any]:
    return {
        "strategy": "ximihoo1_cycle_filter",
        "symbol": symbol,
        "state": state,
        "direction": direction,
        "risk_score": round(risk_score),
        "opportunity_score": round(opportunity_score),
        "allow_trade": bool(allow_trade and ORDER_EXECUTION_ENABLED),
        "paper_trade_only": paper_trade_only,
        "paper_observation_tier": "observe",
        "reasons": reasons,
        "risks": risks,
        "requires_manual_confirmation": True,
    }


def plan_okx_contract_order(signal: Dict[str, Any], account_equity_usdt: float = 0.0) -> Dict[str, Any]:
    """Build a paper OKX swap order plan from a ximihoo1 signal.

    Live execution is deliberately impossible here: ORDER_EXECUTION_ENABLED is
    hard-coded False and the returned mode is paper even for long setups.
    """
    if signal.get("state") != "FAILED_BREAKOUT_RECLAIM_LONG" or signal.get("direction") != "long":
        return {
            "action": "no_order",
            "mode": "paper",
            "reason": "ximihoo1 filter is risk/observation only for this state",
            "requires_manual_confirmation": True,
        }

    equity = max(_num(account_equity_usdt), 0.0)
    margin = min(max(equity * 0.02, 0.0), 250.0)
    leverage = 2
    return {
        "action": "paper_order_plan",
        "mode": "paper",
        "symbol": signal.get("symbol"),
        "side": "buy",
        "posSide": "long",
        "ordType": "market_observation",
        "margin_usdt": round(margin, 2),
        "leverage": leverage,
        "risk_note": "只做纸面/人工确认；不调用 OKX 下单 API",
        "requires_manual_confirmation": True,
        "order_execution_enabled": ORDER_EXECUTION_ENABLED,
    }
