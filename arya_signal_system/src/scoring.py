from __future__ import annotations

from typing import Any, Dict, List


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == '':
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_symbol(symbol: str) -> str:
    s = (symbol or '').upper().strip()
    for suffix in ('-USDT-SWAP', '-USDT', 'USDT', 'USD'):
        if s.endswith(suffix):
            s = s[: -len(suffix)]
            break
    return s.replace('-', '').replace('_', '')


def classify_signal(candidate: Dict[str, Any]) -> Dict[str, Any]:
    price = _num(candidate.get('price_change_1h_pct'))
    vol = _num(candidate.get('volume_change_1h_pct'))
    oi = _num(candidate.get('oi_change_1h_pct'))
    funding = _num(candidate.get('funding_rate_pct'))
    long_liq = _num(candidate.get('long_liq_1h_usd'))
    short_liq = _num(candidate.get('short_liq_1h_usd'))
    depth = _num(candidate.get('depth_usd'))
    spread = _num(candidate.get('spread_pct'))
    top10 = _num(candidate.get('top10_holder_pct'))

    liquidity_bad = depth < 50_000 or spread > 0.25
    funding_extreme = abs(funding) >= 0.10
    liq_total = long_liq + short_liq
    oi_without_liq = oi >= 25 and liq_total < 20_000

    if liquidity_bad or funding_extreme or top10 >= 55:
        if oi_without_liq or funding_extreme or liquidity_bad:
            return {'state': 'EXIT_RISK' if funding_extreme or liquidity_bad else 'OI_FAKE_SUSPECT', 'direction': '不做', 'strategy': '退出/禁止', 'allow_trade': False}

    if oi_without_liq:
        return {'state': 'OI_FAKE_SUSPECT', 'direction': '不做', 'strategy': '只观察', 'allow_trade': False}

    if oi >= 15 and vol >= 50 and max(long_liq, short_liq) >= 80_000:
        if short_liq > long_liq * 2 and price >= 0:
            return {'state': 'SQUEEZE_ACTIVE', 'direction': '偏多', 'strategy': '趋势/爆空', 'allow_trade': False}
        if long_liq > short_liq * 2 and price <= 0:
            return {'state': 'SQUEEZE_ACTIVE', 'direction': '偏空', 'strategy': '趋势/爆多', 'allow_trade': False}
        return {'state': 'TREND_ALERT', 'direction': '待确认', 'strategy': '趋势观察', 'allow_trade': False}

    if depth >= 100_000 and spread <= 0.10 and abs(price) <= 3 and abs(funding) <= 0.03 and oi <= 12:
        return {'state': 'GRID_ALLOWED', 'direction': '中性', 'strategy': '网格/震荡', 'allow_trade': False}

    return {'state': 'WATCH_ONLY', 'direction': '待确认', 'strategy': '只观察', 'allow_trade': False}


def score_candidate(candidate: Dict[str, Any]) -> Dict[str, Any]:
    c = dict(candidate)
    c['symbol'] = normalize_symbol(str(c.get('symbol', 'UNKNOWN')))

    reasons: List[str] = []
    risks: List[str] = []
    score = 0.0

    depth = _num(c.get('depth_usd'))
    spread = _num(c.get('spread_pct'))
    oi = _num(c.get('oi_change_1h_pct'))
    vol = _num(c.get('volume_change_1h_pct'))
    funding = _num(c.get('funding_rate_pct'))
    long_liq = _num(c.get('long_liq_1h_usd'))
    short_liq = _num(c.get('short_liq_1h_usd'))
    hype_rank = _num(c.get('binance_hype_rank'), 999)
    smart = _num(c.get('smart_money_count'))
    top10 = _num(c.get('top10_holder_pct'))

    if depth >= 100_000 and spread <= 0.10:
        score += 15
        reasons.append('盘口深度/点差满足基础交易条件')
    else:
        risks.append('盘口深度不足或点差偏大')
        score -= 10

    if oi >= 15 and vol >= 50:
        score += 25
        reasons.append('OI 与成交量同步放大，存在合约燃料')
    elif oi >= 20 and vol < 20:
        score -= 15
        risks.append('OI 增长但成交量不匹配，疑似假 OI')

    if max(long_liq, short_liq) >= 80_000:
        score += 20
        if short_liq > long_liq * 2:
            reasons.append('空头爆仓显著，爆空结构被验证')
        elif long_liq > short_liq * 2:
            reasons.append('多头爆仓显著，爆多/砸盘结构被验证')
        else:
            reasons.append('爆仓金额放大，验证对手盘活跃')
    elif oi >= 25:
        score -= 12
        risks.append('OI 上升但爆仓没有验证')

    if abs(funding) >= 0.10:
        score -= 25
        risks.append('资金费率极端，进入尾部/收网风险区')
    elif abs(funding) >= 0.01:
        score += 8
        reasons.append('资金费率偏离常态，可作为情绪燃料')

    if hype_rank <= 20:
        score += 10
        reasons.append('Binance Web3 热度靠前，具备传播入口')
    if smart >= 2:
        score += 10
        reasons.append('Smart Money/KOL/鲸鱼信号出现')
    if top10 >= 50:
        score -= 20
        risks.append('Top10 持仓过度集中')

    cls = classify_signal(c)
    if cls['state'] == 'SQUEEZE_ACTIVE':
        score += 10
    elif cls['state'] in {'EXIT_RISK', 'OI_FAKE_SUSPECT'}:
        score = min(score, 45)

    c.update(cls)
    c['score'] = max(0, min(100, round(score)))
    c['reasons'] = reasons
    c['risks'] = risks
    c['manual_confirmation_required'] = True
    c['allow_trade'] = False
    return c
