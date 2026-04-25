from __future__ import annotations

from typing import Any, Dict, List


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == '':
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def assess_funding_quality(candidate: Dict[str, Any]) -> Dict[str, Any]:
    funding = _num(candidate.get('funding_rate_pct'))
    oi = _num(candidate.get('oi_change_1h_pct'))
    price = _num(candidate.get('price_change_1h_pct') or candidate.get('return_1h_pct'))
    vol = _num(candidate.get('volume_change_1h_pct') or candidate.get('volume_1h_vs_24h_avg_pct'))
    persistence = _num(candidate.get('signal_persistence_count'))
    reasons: List[str] = []
    risks: List[str] = []
    quality = 'neutral'
    score = 0

    if funding <= -0.01:
        if oi >= 12 and price >= -1.5 and vol >= 30:
            quality = 'negative_confirmed_long_fuel'
            score = 12
            reasons.append('负费率伴随 OI 增长、价格抗跌和成交放大，空头燃料被确认')
            if persistence >= 2:
                score += 8
                reasons.append('负费率/OI/成交结构持续出现，不是单次监控噪音')
        elif oi <= 0 or price <= -4 or vol < 25:
            quality = 'negative_funding_trap'
            score = -25
            risks.append('负费率缺少 OI/价格/成交确认，可能是诱多或做市商猎杀跟车多头')
        else:
            quality = 'negative_unconfirmed'
            score = -5
            risks.append('负费率尚未获得 OI 与价格结构确认，禁止直接追多')
    elif funding >= 0.08:
        quality = 'positive_tail_risk'
        score = -18
        risks.append('正资金费率偏极端，多头拥挤/尾部收网风险升高')
    elif abs(funding) >= 0.01:
        quality = 'funding_deviation'
        score = 5
        reasons.append('资金费率偏离常态，可作为情绪燃料但需结构确认')

    return {
        'funding_quality': quality,
        'funding_quality_score': score,
        'reasons': reasons,
        'risks': risks,
    }


def detect_guillotine_candle_risk(candidate: Dict[str, Any]) -> Dict[str, Any]:
    ret_24h = _num(candidate.get('return_24h_pct'))
    ret_1h = _num(candidate.get('return_1h_pct') or candidate.get('price_change_1h_pct'))
    range_pos = _num(candidate.get('range_position_24h_pct'), 50.0)
    volume_boost = _num(candidate.get('volume_1h_vs_24h_avg_pct') or candidate.get('volume_change_1h_pct'))
    atr = _num(candidate.get('atr_1h_pct'))
    is_risk = ret_24h >= 25 and ret_1h <= -8 and range_pos >= 75 and volume_boost >= 80
    score = -30 if is_risk else 0
    risks: List[str] = []
    if is_risk:
        risks.append('断头线风险：高位放量急砸，疑似庄币拉高后派发/猎杀追涨')
        if atr >= 5:
            risks.append('ATR 偏高，止损容易被大波动扫掉')
    return {
        'guillotine_candle_risk': is_risk,
        'guillotine_risk_score': score,
        'risks': risks,
    }


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
    return_4h = _num(candidate.get('return_4h_pct'))
    return_24h = _num(candidate.get('return_24h_pct'))
    range_pos = _num(candidate.get('range_position_24h_pct'), 50.0)
    trend_strength = _num(candidate.get('trend_strength'))
    funding_extreme = abs(funding) >= 0.10
    long_liq = _num(candidate.get('long_liq_1h_usd'))
    short_liq = _num(candidate.get('short_liq_1h_usd'))
    depth = _num(candidate.get('depth_usd'))
    spread = _num(candidate.get('spread_pct'))
    top10 = _num(candidate.get('top10_holder_pct'))
    funding_quality = assess_funding_quality(candidate)
    guillotine = detect_guillotine_candle_risk(candidate)

    if depth <= 0 or spread <= 0:
        return {'state': 'WATCH_ONLY', 'model': '待确认', 'direction': '待确认', 'strategy': '只观察', 'allow_trade': False}

    if guillotine['guillotine_candle_risk']:
        return {'state': 'NO_CHASE_GUILLOTINE', 'model': '断头线风险', 'direction': '不追', 'strategy': '禁止追涨/等待结构修复', 'allow_trade': False}

    if funding_quality['funding_quality'] == 'negative_funding_trap':
        return {'state': 'NO_CHASE_NEGATIVE_FUNDING', 'model': '负费率诱多风险', 'direction': '不追多', 'strategy': '只观察/等待持续确认', 'allow_trade': False}

    liquidity_bad = depth < 50_000 or spread > 0.25
    liq_total = long_liq + short_liq
    oi_without_liq = oi >= 25 and liq_total < 20_000
    tail_risk = funding_extreme and oi >= 25 and return_24h >= 30 and range_pos >= 80

    if tail_risk:
        return {
            'state': 'SHORT_TAIL_RISK',
            'model': '做空模型B-尾部高危反手观察',
            'direction': '不追多',
            'strategy': '减多/观察反手',
            'allow_trade': False,
        }

    if funding_extreme:
        return {'state': 'EXIT_RISK', 'model': '尾部风险', 'direction': '不做', 'strategy': '退出/禁止', 'allow_trade': False}

    if liquidity_bad or top10 >= 55:
        if oi_without_liq or liquidity_bad:
            return {'state': 'EXIT_RISK' if liquidity_bad else 'NO_TRADE_FAKE_OI', 'model': '无效模型-OI未验证', 'direction': '不做', 'strategy': '退出/禁止' if liquidity_bad else '只观察', 'allow_trade': False}

    if oi_without_liq:
        return {'state': 'NO_TRADE_FAKE_OI', 'model': '无效模型-OI未验证', 'direction': '不做', 'strategy': '只观察', 'allow_trade': False}

    if oi >= 15 and vol >= 50 and max(long_liq, short_liq) >= 80_000:
        if short_liq > long_liq * 2 and price >= 0:
            return {'state': 'LONG_SQUEEZE', 'model': '做多模型A-爆空顺势多', 'direction': '偏多', 'strategy': '趋势/爆空', 'allow_trade': False}
        if long_liq > short_liq * 2 and price <= 0:
            return {'state': 'SHORT_BREAKDOWN', 'model': '做空模型A-庄撤仓收网', 'direction': '偏空', 'strategy': '做空/瀑布', 'allow_trade': False}
        return {'state': 'TREND_ALERT', 'model': '趋势燃料待确认', 'direction': '待确认', 'strategy': '趋势观察', 'allow_trade': False}

    pullback_reclaim = (
        return_24h >= 20
        and return_4h <= -6
        and price >= 2
        and vol >= 50
        and oi >= 8
        and depth >= 100_000
        and spread <= 0.10
        and abs(funding) <= 0.05
        and 20 <= range_pos <= 70
        and trend_strength >= 1.0
    )
    if pullback_reclaim:
        return {'state': 'LONG_PULLBACK', 'model': '做多模型B-强庄回调抄底', 'direction': '偏多', 'strategy': '回调试多', 'allow_trade': False}

    if depth >= 100_000 and spread <= 0.10 and abs(price) <= 3 and abs(funding) <= 0.03 and oi <= 12:
        return {'state': 'GRID_ALLOWED', 'model': '震荡网格', 'direction': '中性', 'strategy': '网格/震荡', 'allow_trade': False}

    return {'state': 'WATCH_ONLY', 'model': '待确认', 'direction': '待确认', 'strategy': '只观察', 'allow_trade': False}


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
    persistence_score = _num(c.get('signal_persistence_score'))
    if persistence_score <= 0 and _num(c.get('signal_persistence_count')) > 0:
        persistence_score = min(20, _num(c.get('signal_persistence_count')) * 5)
    funding_quality = assess_funding_quality({**c, 'signal_persistence_score': persistence_score})
    guillotine = detect_guillotine_candle_risk(c)
    c['funding_quality'] = funding_quality['funding_quality']
    c['funding_quality_score'] = funding_quality['funding_quality_score']
    c['signal_persistence_score'] = persistence_score
    c['guillotine_candle_risk'] = guillotine['guillotine_candle_risk']
    c['guillotine_risk_score'] = guillotine['guillotine_risk_score']

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
            reasons.append('多头爆仓显著，做空/砸盘结构被验证')
        else:
            reasons.append('爆仓金额放大，验证对手盘活跃')
    elif oi >= 25:
        score -= 12
        risks.append('OI 上升但爆仓没有验证')

    if abs(funding) >= 0.10:
        score -= 25
        risks.append('资金费率极端，进入尾部/收网风险区')
    else:
        score += funding_quality['funding_quality_score']
        reasons.extend(funding_quality['reasons'])
        risks.extend(funding_quality['risks'])

    if persistence_score >= 10:
        score += min(10, persistence_score / 2)
        reasons.append('信号持续性达标：多次监控确认 funding/OI/成交/价格结构')
    elif funding <= -0.01 and _num(c.get('signal_persistence_count')) <= 1:
        score -= 8
        risks.append('单次负费率/OI监控触发，缺少持续性确认，禁止追车')

    if guillotine['guillotine_candle_risk']:
        score += guillotine['guillotine_risk_score']
        risks.extend(guillotine['risks'])

    buy_sell_ratio = _num(c.get('buy_sell_ratio_1h'))
    top_account_lsr = _num(c.get('top_account_long_short_ratio'))
    top_position_lsr = _num(c.get('top_position_long_short_ratio'))
    binance_oi_share = _num(c.get('binance_oi_share_pct'))
    okx_oi_share = _num(c.get('okx_oi_share_pct'))
    if buy_sell_ratio >= 1.5:
        reasons.append('主动买盘明显强于卖盘')
        score += 6
    elif 0 < buy_sell_ratio <= 0.67:
        reasons.append('主动卖盘明显强于买盘')
        score += 6
    if top_account_lsr >= 2.0 or top_position_lsr >= 2.0:
        risks.append('大户多空比偏多，注意多头拥挤')
        score -= 4
    elif 0 < top_account_lsr <= 0.5 or 0 < top_position_lsr <= 0.5:
        risks.append('大户多空比偏空，注意空头拥挤/爆空')
        score -= 2
    if binance_oi_share >= 35:
        reasons.append('Binance OI 占比高，主战场流动性更强')
        score += 4
    if okx_oi_share >= 35:
        reasons.append('OKX OI 占比高，本交易所信号参考价值更强')
        score += 4

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
    if cls['state'] in {'LONG_SQUEEZE', 'SQUEEZE_ACTIVE', 'SHORT_BREAKDOWN', 'SHORT_ALERT'}:
        score += 10
    elif cls['state'] == 'LONG_PULLBACK':
        score += 25
        reasons.append('强势币深回调后放量回拉，符合回调试多模型')
    elif cls['state'] in {'EXIT_RISK', 'NO_TRADE_FAKE_OI', 'OI_FAKE_SUSPECT', 'SHORT_TAIL_RISK', 'NO_CHASE_NEGATIVE_FUNDING', 'NO_CHASE_GUILLOTINE'}:
        score = min(score, 45)

    c.update(cls)
    c['score'] = max(0, min(100, round(score)))
    c['reasons'] = reasons
    c['risks'] = risks
    c['manual_confirmation_required'] = True
    c['allow_trade'] = False
    return c
