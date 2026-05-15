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


def compute_counterparty_fuel_score(candidate: Dict[str, Any]) -> Dict[str, Any]:
    price = _num(candidate.get('price_change_1h_pct') or candidate.get('return_1h_pct'))
    vol = _num(candidate.get('volume_change_1h_pct') or candidate.get('volume_1h_vs_24h_avg_pct'))
    oi = _num(candidate.get('oi_change_1h_pct'))
    funding = _num(candidate.get('funding_rate_pct'))
    long_liq = _num(candidate.get('long_liq_1h_usd'))
    short_liq = _num(candidate.get('short_liq_1h_usd'))
    buy_sell = _num(candidate.get('buy_sell_ratio_1h'))
    persistence = _num(candidate.get('signal_persistence_count'))
    score = 0.0
    reasons: List[str] = []
    direction = 'unconfirmed'

    if oi >= 15:
        score += 20
        reasons.append('OI 增长，场内新增对手盘燃料')
    if vol >= 50:
        score += 18
        reasons.append('成交放大，燃料开始进入可收割状态')
    if max(long_liq, short_liq) >= 80_000:
        score += 22
        if short_liq > long_liq * 2:
            direction = 'shorts_as_fuel'
            reasons.append('空头燃料占优，若价格抗跌/上行可形成爆空顺势多')
        elif long_liq > short_liq * 2:
            direction = 'longs_as_fuel'
            reasons.append('多头燃料占优，若高位破位可形成闪崩空')
        else:
            reasons.append('多空爆仓均放大，燃料活跃但方向待确认')
    if funding <= -0.01 and oi >= 12 and price >= -2:
        score += 14
        direction = 'shorts_as_fuel'
        reasons.append('负费率 + OI + 价格抗跌，空头燃料被确认')
    elif funding >= 0.02 and oi >= 12 and price <= 0:
        score += 12
        direction = 'longs_as_fuel'
        reasons.append('正费率拥挤且价格转弱，多头燃料可被收割')
    if buy_sell >= 1.5 and direction == 'shorts_as_fuel':
        score += 6
        reasons.append('主动买盘配合爆空方向')
    elif 0 < buy_sell <= 0.67 and direction == 'longs_as_fuel':
        score += 6
        reasons.append('主动卖盘配合杀多方向')
    if persistence >= 2:
        score += 8
        reasons.append('燃料结构多次持续出现，降低单点噪音')

    return {
        'counterparty_fuel_score': round(_clamp(score)),
        'counterparty_fuel_direction': direction,
        'reasons': reasons,
    }


def assess_fair_game_filter(candidate: Dict[str, Any]) -> Dict[str, Any]:
    depth = _num(candidate.get('depth_usd'))
    spread = _num(candidate.get('spread_pct'))
    atr = _num(candidate.get('atr_1h_pct'))
    top10 = _num(candidate.get('top10_holder_pct'))
    guillotine = bool(candidate.get('guillotine_candle_risk'))
    score = 0.0
    risks: List[str] = []
    reasons: List[str] = []

    if depth >= 100_000:
        score += 15
        reasons.append('深度达标，基础可交易性较好')
    elif depth > 0:
        score -= 25
        risks.append('公平场不足：盘口深度太薄，容易被扫损/插针')
    else:
        score -= 35
        risks.append('公平场不足：缺少盘口深度数据')
    if 0 < spread <= 0.10:
        score += 10
        reasons.append('点差正常')
    elif spread > 0.25:
        score -= 25
        risks.append('公平场不足：点差过大，成交成本和滑点风险高')
    elif spread > 0.10:
        score -= 10
        risks.append('点差偏大，需要降低信号权重')
    if atr >= 10:
        score -= 18
        risks.append('公平场不足：波动/插针过大')
    elif atr >= 6:
        score -= 8
        risks.append('ATR 偏高，止损容易被噪音扫掉')
    if top10 >= 65:
        score -= 25
        risks.append('庄控/筹码集中度过高，场子不公平')
    elif top10 >= 55:
        score -= 12
        risks.append('Top10 持仓偏集中，需防庄控')
    if guillotine:
        score -= 25
        risks.append('断头线已出现，禁止当作公平趋势场追单')

    fair_game = score > -25 and not (depth > 0 and depth < 50_000) and spread <= 0.25 and top10 < 65
    return {
        'fair_game': fair_game,
        'fair_game_score': round(score),
        'reasons': reasons,
        'risks': risks,
    }


def detect_flash_crash_short_model(candidate: Dict[str, Any]) -> Dict[str, Any]:
    ret_24h = _num(candidate.get('return_24h_pct'))
    ret_1h = _num(candidate.get('return_1h_pct') or candidate.get('price_change_1h_pct'))
    range_pos = _num(candidate.get('range_position_24h_pct'), 50.0)
    vol = _num(candidate.get('volume_change_1h_pct') or candidate.get('volume_1h_vs_24h_avg_pct'))
    oi = _num(candidate.get('oi_change_1h_pct'))
    long_liq = _num(candidate.get('long_liq_1h_usd'))
    short_liq = _num(candidate.get('short_liq_1h_usd'))
    depth = _num(candidate.get('depth_usd'))
    spread = _num(candidate.get('spread_pct'))
    atr = _num(candidate.get('atr_1h_pct'))
    overheated = ret_24h >= 35 and range_pos >= 75
    breakdown = ret_1h <= -8 and vol >= 80 and oi >= 15
    longs_trapped = long_liq >= 80_000 and long_liq > max(short_liq * 2, 1)
    tradable = depth >= 100_000 and 0 < spread <= 0.15 and (atr <= 0 or atr <= 5)
    is_flash = overheated and breakdown and longs_trapped and tradable
    reasons: List[str] = []
    if overheated:
        reasons.append('妖币/强势币 24h 高位过热')
    if breakdown:
        reasons.append('高位放量破位，闪崩结构启动')
    if longs_trapped:
        reasons.append('多头爆仓显著，杀多燃料被验证')
    return {
        'flash_crash_short': is_flash,
        'state': 'FLASH_CRASH_SHORT' if is_flash else 'WATCH_ONLY',
        'score_bonus': 25 if is_flash else 0,
        'reasons': reasons,
    }



def compute_anti_consensus_score(candidate: Dict[str, Any]) -> Dict[str, Any]:
    funding = _num(candidate.get('funding_rate_pct'))
    oi = _num(candidate.get('oi_change_1h_pct'))
    price = _num(candidate.get('price_change_1h_pct') or candidate.get('return_1h_pct'))
    vol = _num(candidate.get('volume_change_1h_pct') or candidate.get('volume_1h_vs_24h_avg_pct'))
    buy_sell = _num(candidate.get('buy_sell_ratio_1h'))
    persistence = _num(candidate.get('signal_persistence_count'))
    top_account_lsr = _num(candidate.get('top_account_long_short_ratio'))
    top_position_lsr = _num(candidate.get('top_position_long_short_ratio'))
    score = 0.0
    direction = 'neutral'
    reasons: List[str] = []
    risks: List[str] = []

    crowded_shorts = funding <= -0.01 and oi >= 12 and price >= -1.5 and vol >= 40
    crowded_longs = funding >= 0.02 and oi >= 12 and price <= 0 and vol >= 40
    if crowded_shorts:
        direction = 'fade_crowded_shorts'
        score += 45
        reasons.append('反共识：负费率下空头拥挤，但价格抗跌/转强，空头可能成为燃料')
    elif crowded_longs:
        direction = 'fade_crowded_longs'
        score += 40
        reasons.append('反共识：正费率下多头拥挤且价格转弱，多头可能成为燃料')

    if oi >= 20:
        score += 10
        reasons.append('OI 持续扩张，市场共识仓位变重')
    if vol >= 80:
        score += 10
        reasons.append('成交放大，错误共识进入可被收割阶段')
    if persistence >= 2:
        score += 10
        reasons.append('反共识结构多次持续，不是单点噪音')
    if buy_sell >= 1.3 and direction == 'fade_crowded_shorts':
        score += 8
        reasons.append('主动买盘开始反向承接空头共识')
    elif 0 < buy_sell <= 0.75 and direction == 'fade_crowded_longs':
        score += 8
        reasons.append('主动卖盘开始反向承接多头共识')
    if top_account_lsr >= 2.0 or top_position_lsr >= 2.0:
        risks.append('大户多头拥挤，反共识做多需要降权')
        if direction == 'fade_crowded_shorts':
            score -= 8
    if 0 < top_account_lsr <= 0.5 or 0 < top_position_lsr <= 0.5:
        risks.append('大户空头拥挤，反共识做空需要降权')
        if direction == 'fade_crowded_longs':
            score -= 8

    return {
        'anti_consensus_score': round(_clamp(score)),
        'anti_consensus_direction': direction,
        'reasons': reasons,
        'risks': risks,
    }


def compute_early_demon_trend_score(candidate: Dict[str, Any]) -> Dict[str, Any]:
    ret_24h = _num(candidate.get('return_24h_pct'))
    price = _num(candidate.get('price_change_1h_pct') or candidate.get('return_1h_pct'))
    vol = _num(candidate.get('volume_change_1h_pct') or candidate.get('volume_1h_vs_24h_avg_pct'))
    oi = _num(candidate.get('oi_change_1h_pct'))
    range_pos = _num(candidate.get('range_position_24h_pct'), 50.0)
    atr = _num(candidate.get('atr_1h_pct'))
    hype_rank = _num(candidate.get('binance_hype_rank'), 999)
    depth = _num(candidate.get('depth_usd'))
    spread = _num(candidate.get('spread_pct'))
    score = 0.0
    reasons: List[str] = []
    risks: List[str] = []

    if 8 <= ret_24h <= 35:
        score += 18
        reasons.append('早期妖币：24h 已启动但尚未进入极端尾部')
    elif ret_24h > 45:
        score -= 25
        risks.append('涨幅过大，可能已进入尾部收网区')
    if 2 <= price <= 9:
        score += 16
        reasons.append('1h 转强但未出现末端暴拉')
    if vol >= 80:
        score += 16
        reasons.append('注意力/成交正在流入')
    if 10 <= oi <= 35:
        score += 14
        reasons.append('OI 增长适中，燃料形成但未极端拥挤')
    elif oi > 45:
        score -= 12
        risks.append('OI 过热，容易从早期机会变成尾部风险')
    if 25 <= range_pos <= 70:
        score += 12
        reasons.append('价格处于区间中上部，尚非高位追尾')
    elif range_pos > 82:
        score -= 18
        risks.append('区间位置太高，禁止当早期妖币追')
    if 0 < atr <= 5:
        score += 8
        reasons.append('ATR 可控，观察级止损有意义')
    elif atr >= 8:
        score -= 12
        risks.append('ATR 过高，插针风险大')
    if hype_rank <= 25:
        score += 10
        reasons.append('热度入口靠前，叙事/注意力有传播可能')
    if depth >= 100_000 and 0 < spread <= 0.15:
        score += 8
        reasons.append('深度/点差支持观察级跟踪')

    score = round(_clamp(score))
    return {
        'early_demon_trend': score >= 65 and not (ret_24h > 45 or range_pos > 82 or atr >= 8),
        'early_demon_trend_score': score,
        'reasons': reasons,
        'risks': risks,
    }


def assess_sector_leader_filter(candidate: Dict[str, Any]) -> Dict[str, Any]:
    rank = _num(candidate.get('sector_rank') or candidate.get('sector_leader_rank'))
    sector = str(candidate.get('sector') or candidate.get('narrative') or '')
    reasons: List[str] = []
    risks: List[str] = []
    if rank <= 0:
        return {'sector_filter': 'unknown', 'sector_leader': False, 'score_adjustment': 0, 'reasons': reasons, 'risks': risks}
    if rank <= 2:
        reasons.append(f'板块龙头优先：{sector or "unknown"} rank {rank:.0f}')
        return {'sector_filter': 'leader', 'sector_leader': True, 'score_adjustment': 6, 'reasons': reasons, 'risks': risks}
    risks.append(f'板块后排：{sector or "unknown"} rank {rank:.0f}，只做观察，不抢后排补涨')
    return {'sector_filter': 'laggard_observe_only', 'sector_leader': False, 'score_adjustment': -18, 'reasons': reasons, 'risks': risks}


def detect_smart_short_observation(candidate: Dict[str, Any]) -> Dict[str, Any]:
    funding = _num(candidate.get('funding_rate_pct'))
    oi = _num(candidate.get('oi_change_1h_pct'))
    price = _num(candidate.get('price_change_1h_pct') or candidate.get('return_1h_pct'))
    vol = _num(candidate.get('volume_change_1h_pct') or candidate.get('volume_1h_vs_24h_avg_pct'))
    persistence = _num(candidate.get('signal_persistence_count'))
    previous_state = str(candidate.get('previous_state') or candidate.get('prior_state') or '')
    reasons: List[str] = []
    risks: List[str] = []

    negative_funding_pressure = funding <= -0.05
    volume_expanding = vol >= 80
    fair_depth = _num(candidate.get('depth_usd')) >= 100_000 and 0 < _num(candidate.get('spread_pct')) <= 0.15
    if not (negative_funding_pressure and volume_expanding and fair_depth):
        return {'state': None, 'score_floor': 0, 'reasons': reasons, 'risks': risks}

    if funding <= -0.10 and oi <= -5 and price <= -4:
        risks.append('负费率极端且 OI 大幅下降，已进入出清/收网段，禁止追空')
        return {'state': 'EXIT_RISK', 'score_floor': 0, 'reasons': reasons, 'risks': risks}

    if previous_state == 'SMART_SHORT_PROBE':
        if price <= -1.5 and oi >= -3:
            reasons.extend([
                '空头试探后价格开始破位，成交继续放大',
                'OI 未快速消失，说明空头/对手盘仍在场内，进入确认中而非追空开仓',
            ])
            return {'state': 'SHORT_CONFIRMING', 'score_floor': 58, 'reasons': reasons, 'risks': risks}
        if price >= 3 and oi >= 1:
            reasons.extend([
                '空头试探后价格继续抗住/上破，空头更可能成为燃料',
                '防止把拥挤空头误判成聪明钱做空',
            ])
            return {'state': 'SHORTS_AS_FUEL', 'score_floor': 55, 'reasons': reasons, 'risks': risks}

    if oi >= 1 and price >= 0 and persistence >= 2:
        reasons.extend([
            '空头试探：负费率高成本下 OI 增加，价格仍抗跌/滞涨',
            '成交放大但尚未破位，只能观察谁被迫交易，等待破位与反抽失败确认',
        ])
        return {'state': 'SMART_SHORT_PROBE', 'score_floor': 52, 'reasons': reasons, 'risks': risks}

    return {'state': None, 'score_floor': 0, 'reasons': reasons, 'risks': risks}


def build_thesis_invalidation(candidate: Dict[str, Any]) -> List[str]:
    state = str(candidate.get('state') or '')
    side = str(candidate.get('direction') or '')
    invalidation: List[str] = []
    if state in {'LONG_SQUEEZE', 'LONG_PULLBACK', 'EARLY_DEMON_TREND'} or '多' in side:
        invalidation.extend([
            '1h 价格跌回启动位下方且成交继续放大',
            'OI 继续增加但价格不再抗跌，燃料从爆空变成诱多',
            '盘口深度跌破 100k 或点差扩大到 0.25% 以上',
        ])
    elif state in {'SHORT_BREAKDOWN', 'SHORT_ALERT', 'FLASH_CRASH_SHORT', 'SMART_SHORT_PROBE', 'SHORT_CONFIRMING'} or '空' in side:
        invalidation.extend([
            '1h 价格收回破位位上方且空头爆仓开始放大',
            '主动买盘恢复并带动 OI 下降，杀多逻辑结束',
            '盘口深度跌破 100k 或点差扩大到 0.25% 以上',
        ])
    elif state == 'SHORTS_AS_FUEL':
        invalidation.extend([
            '价格重新跌破试探区间且反抽失败',
            'OI 快速下降导致空头燃料消失',
            '盘口深度跌破 100k 或点差扩大到 0.25% 以上',
        ])
    else:
        invalidation.extend([
            '核心触发因子连续两轮监控消失',
            '公平场恶化：深度不足、点差扩大或插针增多',
        ])
    return invalidation

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
    liquidity_bad = depth < 50_000 or spread > 0.25
    liq_total = long_liq + short_liq
    oi_without_liq = oi >= 25 and liq_total < 20_000
    tail_risk = funding_extreme and oi >= 25 and return_24h >= 30 and range_pos >= 80

    if depth <= 0 or spread <= 0:
        return {'state': 'WATCH_ONLY', 'model': '待确认', 'direction': '待确认', 'strategy': '只观察', 'allow_trade': False}

    if funding_extreme:
        if tail_risk:
            return {
                'state': 'SHORT_TAIL_RISK',
                'model': '做空模型B-尾部高危反手观察',
                'direction': '不追多',
                'strategy': '减多/观察反手',
                'allow_trade': False,
            }
        return {'state': 'EXIT_RISK', 'model': '尾部风险', 'direction': '不做', 'strategy': '退出/禁止', 'allow_trade': False}

    smart_short = detect_smart_short_observation(candidate)
    if smart_short['state'] == 'EXIT_RISK':
        return {'state': 'EXIT_RISK', 'model': '尾部风险', 'direction': '不做', 'strategy': '退出/禁止', 'allow_trade': False}

    funding_quality = assess_funding_quality(candidate)
    guillotine = detect_guillotine_candle_risk(candidate)
    fair_game = assess_fair_game_filter({**candidate, 'guillotine_candle_risk': guillotine['guillotine_candle_risk']})
    flash_crash = detect_flash_crash_short_model(candidate)

    if not fair_game['fair_game']:
        return {'state': 'NO_TRADE_UNFAIR_GAME', 'model': '公平场过滤', 'direction': '不做', 'strategy': '禁止交易/等待深度修复', 'allow_trade': False}

    if smart_short['state'] == 'SHORT_CONFIRMING':
        return {'state': 'SHORT_CONFIRMING', 'model': '空头确认中', 'direction': '偏空观察', 'strategy': '高优先级观察/等待反抽失败', 'allow_trade': False}
    if smart_short['state'] == 'SHORTS_AS_FUEL':
        return {'state': 'SHORTS_AS_FUEL', 'model': '空头燃料观察', 'direction': '偏多观察', 'strategy': '观察/防做空/等待爆空确认', 'allow_trade': False}
    if smart_short['state'] == 'SMART_SHORT_PROBE':
        return {'state': 'SMART_SHORT_PROBE', 'model': '空头试探观察', 'direction': '偏空观察', 'strategy': '观察/等待破位与反抽失败确认', 'allow_trade': False}

    if flash_crash['flash_crash_short']:
        return {'state': 'FLASH_CRASH_SHORT', 'model': '妖币高位破位闪崩空', 'direction': '偏空', 'strategy': '做空/闪崩', 'allow_trade': False}

    if guillotine['guillotine_candle_risk']:
        return {'state': 'NO_CHASE_GUILLOTINE', 'model': '断头线风险', 'direction': '不追', 'strategy': '禁止追涨/等待结构修复', 'allow_trade': False}

    if funding_quality['funding_quality'] == 'negative_funding_trap':
        return {'state': 'NO_CHASE_NEGATIVE_FUNDING', 'model': '负费率诱多风险', 'direction': '不追多', 'strategy': '只观察/等待持续确认', 'allow_trade': False}

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
    fuel = compute_counterparty_fuel_score(c)
    fair_game = assess_fair_game_filter({**c, 'guillotine_candle_risk': guillotine['guillotine_candle_risk']})
    flash_crash = detect_flash_crash_short_model(c)
    anti_consensus = compute_anti_consensus_score(c)
    early_demon = compute_early_demon_trend_score(c)
    sector_filter = assess_sector_leader_filter(c)
    smart_short = detect_smart_short_observation(c)
    c['funding_quality'] = funding_quality['funding_quality']
    c['funding_quality_score'] = funding_quality['funding_quality_score']
    c['signal_persistence_score'] = persistence_score
    c['guillotine_candle_risk'] = guillotine['guillotine_candle_risk']
    c['guillotine_risk_score'] = guillotine['guillotine_risk_score']
    c['counterparty_fuel_score'] = fuel['counterparty_fuel_score']
    c['counterparty_fuel_direction'] = fuel['counterparty_fuel_direction']
    c['fair_game'] = fair_game['fair_game']
    c['fair_game_score'] = fair_game['fair_game_score']
    c['flash_crash_short'] = flash_crash['flash_crash_short']
    c['anti_consensus_score'] = anti_consensus['anti_consensus_score']
    c['anti_consensus_direction'] = anti_consensus['anti_consensus_direction']
    c['early_demon_trend'] = early_demon['early_demon_trend']
    c['early_demon_trend_score'] = early_demon['early_demon_trend_score']
    c['sector_filter'] = sector_filter['sector_filter']
    c['sector_leader'] = sector_filter['sector_leader']
    c['smart_short_observation_state'] = smart_short['state'] or 'none'

    if depth >= 100_000 and spread <= 0.10:
        score += 15
        reasons.append('盘口深度/点差满足基础交易条件')
    else:
        risks.append('盘口深度不足或点差偏大')
        score -= 10

    if oi >= 15 and vol >= 50:
        score += 25
        reasons.append('OI 与成交量同步放大，存在合约燃料')
    if fuel['counterparty_fuel_score'] >= 70:
        score += 12
        reasons.extend(fuel['reasons'][:3])
    elif fuel['counterparty_fuel_score'] >= 45:
        score += 6
        reasons.extend(fuel['reasons'][:2])
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

    if fair_game['fair_game']:
        score += max(0, min(8, fair_game['fair_game_score'] / 3))
        reasons.extend(fair_game['reasons'][:2])
    else:
        score = min(score + fair_game['fair_game_score'], 40)
        risks.extend(fair_game['risks'])

    if flash_crash['flash_crash_short']:
        score += flash_crash['score_bonus']
        reasons.extend(flash_crash['reasons'])

    if anti_consensus['anti_consensus_score'] >= 65:
        score += 8
        reasons.extend(anti_consensus['reasons'][:2])
    elif anti_consensus['anti_consensus_score'] >= 45:
        score += 4
        reasons.extend(anti_consensus['reasons'][:1])
    risks.extend(anti_consensus['risks'])
    if smart_short['state'] in {'SMART_SHORT_PROBE', 'SHORT_CONFIRMING', 'SHORTS_AS_FUEL'}:
        reasons.extend(smart_short['reasons'])
        risks.extend(smart_short['risks'])

    if early_demon['early_demon_trend_score'] >= 65:
        score += 10
        reasons.extend(early_demon['reasons'][:3])
    risks.extend(early_demon['risks'])

    score += sector_filter['score_adjustment']
    reasons.extend(sector_filter['reasons'])
    risks.extend(sector_filter['risks'])

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
    if early_demon['early_demon_trend'] and cls['state'] in {'GRID_ALLOWED', 'WATCH_ONLY'}:
        cls = {'state': 'EARLY_DEMON_TREND', 'model': '第一性原理-早期妖币观察', 'direction': '偏多观察', 'strategy': '观察级paper/等待二次确认', 'allow_trade': False}
    if sector_filter['sector_filter'] == 'laggard_observe_only' and cls['state'] == 'EARLY_DEMON_TREND':
        cls = {'state': 'SECTOR_LAGGARD_OBSERVE', 'model': '板块后排观察过滤', 'direction': '只观察', 'strategy': '观察级paper/不抢后排', 'allow_trade': False}
    if cls['state'] in {'LONG_SQUEEZE', 'SQUEEZE_ACTIVE', 'SHORT_BREAKDOWN', 'SHORT_ALERT', 'FLASH_CRASH_SHORT'}:
        score += 10
    elif cls['state'] == 'LONG_PULLBACK':
        score += 25
        reasons.append('强势币深回调后放量回拉，符合回调试多模型')
    elif cls['state'] in {'EARLY_DEMON_TREND'}:
        score = min(max(score, 55), 72)
    elif cls['state'] in {'SMART_SHORT_PROBE', 'SHORT_CONFIRMING', 'SHORTS_AS_FUEL'}:
        score = min(max(score, smart_short['score_floor']), 72)
    elif cls['state'] in {'SECTOR_LAGGARD_OBSERVE'}:
        score = min(score, 65)
    elif cls['state'] in {'EXIT_RISK', 'NO_TRADE_FAKE_OI', 'OI_FAKE_SUSPECT', 'SHORT_TAIL_RISK', 'NO_CHASE_NEGATIVE_FUNDING', 'NO_CHASE_GUILLOTINE', 'NO_TRADE_UNFAIR_GAME'}:
        score = min(score, 45)

    c.update(cls)
    c['score'] = max(0, min(100, round(score)))
    c['reasons'] = reasons
    c['risks'] = risks
    c['paper_observation_tier'] = 'observe' if c.get('state') in {'EARLY_DEMON_TREND', 'SECTOR_LAGGARD_OBSERVE', 'SMART_SHORT_PROBE', 'SHORT_CONFIRMING', 'SHORTS_AS_FUEL'} else 'main' if c.get('state') in {'LONG_SQUEEZE', 'LONG_PULLBACK', 'SHORT_BREAKDOWN', 'SHORT_ALERT', 'TREND_ALERT', 'FLASH_CRASH_SHORT'} else 'none'
    c['thesis_invalidation'] = build_thesis_invalidation(c)
    c['manual_confirmation_required'] = True
    c['allow_trade'] = False
    return c
