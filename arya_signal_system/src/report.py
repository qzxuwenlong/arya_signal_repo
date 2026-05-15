from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List


STATE_NOTES: Dict[str, str] = {
    'LONG_SQUEEZE': '爆空顺势多：空头燃料被验证，可人工确认后观察做多',
    'LONG_PULLBACK': '强庄回调试多：强势币回踩后转强，等待人工确认',
    'SHORT_BREAKDOWN': '破位做空：多头爆仓/庄撤仓结构，偏空观察',
    'SHORT_ALERT': '偏空警报：下跌放量且多头爆仓占优',
    'FLASH_CRASH_SHORT': '妖币闪崩空：高位过热后放量破位，多头燃料被收割',
    'TREND_ALERT': '趋势警报：趋势和热度共振，需人工确认',
    'SQUEEZE_ACTIVE': '挤压启动：爆仓燃料正在释放，需人工确认',
    'GRID_ALLOWED': '网格可观察：震荡结构，非追涨杀跌信号',
    'WATCH_ONLY': '只观察：数据不足或结构未确认',
    'EXIT_RISK': '退出风险：尾部/收网风险高，不作为入场信号',
    'NO_TRADE_FAKE_OI': '假 OI 风险：OI 增长未被价格/成交验证，禁止交易',
    'OI_FAKE_SUSPECT': '疑似假 OI：只观察，等待更多确认',
    'SHORT_TAIL_RISK': '尾部高危：多头拥挤或顶部风险，不追多',
    'NO_CHASE_NEGATIVE_FUNDING': '负费率诱多，不追多：缺少 OI/价格/成交持续确认',
    'NO_CHASE_GUILLOTINE': '断头线风险，不追涨：高位放量急砸，等待结构修复',
    'NO_TRADE_UNFAIR_GAME': '公平场不足，禁止交易：深度差/点差大/插针或庄控风险高',
    'SMART_SHORT_PROBE': '空头试探观察：负费率 + OI 增 + 价格抗住，只观察谁被迫交易，等待破位与反抽失败确认',
    'SHORT_CONFIRMING': '空头确认中：试探后破位但仍不自动开仓，等待反抽失败/盘口卖压确认',
    'SHORTS_AS_FUEL': '空头燃料观察：价格继续抗住或上破，防止把拥挤空头误判成聪明钱做空',
    'EARLY_DEMON_TREND': '早期妖币观察：注意力刚流入，只进观察级 paper，不污染主信号',
    'SECTOR_LAGGARD_OBSERVE': '板块后排观察：不抢后排补涨，只记录观察样本',
}


def state_note(state: str | None) -> str:
    return STATE_NOTES.get(state or '', '状态待确认：只作为观察信号')


def render_markdown_report(candidates: Iterable[Dict[str, Any]], source_status: Dict[str, str] | None = None, onchain_observation_pool: Dict[str, Any] | None = None) -> str:
    rows: List[Dict[str, Any]] = sorted(list(candidates), key=lambda x: x.get('score', 0), reverse=True)
    source_status = source_status or {}
    lines: List[str] = []
    lines.append('# Arya 知识库驱动热币扫描 V1')
    lines.append('')
    lines.append(f'时间：{datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")}')
    lines.append('')
    lines.append('原则：**只输出投资建议，不自动下单；任何交易必须人工确认。**')
    lines.append('')
    lines.append('## 数据源状态')
    label = {'coinank': 'CoinAnk', 'okx': 'OKX', 'binance_web3': 'Binance Web3', 'onchainos': 'OKX OnchainOS'}
    for k, v in source_status.items():
        lines.append(f'- {label.get(k, k)}：{v}')
    lines.append('')
    lines.append('## 候选币')
    if not rows:
        lines.append('暂无符合条件的异常币。')
    else:
        for i, c in enumerate(rows, 1):
            state = c.get("state", "WATCH_ONLY")
            lines.append(f'### {i}. {c.get("symbol", "UNKNOWN")}｜{state}｜{state_note(state)}｜{c.get("score", 0)}分')
            lines.append(f'- 方向：{c.get("direction", "待确认")}')
            lines.append(f'- 策略：{c.get("strategy", "只观察")}')
            lines.append(f'- 执行：不自动下单，需人工确认')
            if 'local_history_ready' in c:
                ready = 'ready' if c.get('local_history_ready') else 'warming_up'
                lines.append(
                    f'- 本地燃料：{ready}｜OI 1h {float(c.get("oi_change_1h_pct") or 0):.2f}%｜量 1h {float(c.get("volume_change_1h_pct") or 0):.2f}%｜价 1h {float(c.get("price_change_1h_pct") or 0):.2f}%'
                )
            if c.get('funding_quality'):
                lines.append(
                    f'- 负费率质量：{c.get("funding_quality")}｜funding_score {float(c.get("funding_quality_score") or 0):.0f}｜persistence {float(c.get("signal_persistence_score") or 0):.0f}｜断头线 {"yes" if c.get("guillotine_candle_risk") else "no"}'
                )
            if 'counterparty_fuel_score' in c or 'fair_game_score' in c:
                lines.append(
                    f'- 对手盘燃料/公平场：fuel {float(c.get("counterparty_fuel_score") or 0):.0f}({c.get("counterparty_fuel_direction", "unconfirmed")})｜fair {"yes" if c.get("fair_game") else "no"}({float(c.get("fair_game_score") or 0):.0f})｜闪崩空 {"yes" if c.get("flash_crash_short") else "no"}'
                )
            if 'anti_consensus_score' in c or 'early_demon_trend_score' in c:
                lines.append(
                    f'- 第一性原理观察层：反共识 {float(c.get("anti_consensus_score") or 0):.0f}({c.get("anti_consensus_direction", "neutral")})｜早期妖币 {float(c.get("early_demon_trend_score") or 0):.0f}｜板块 {c.get("sector_filter", "unknown")}｜观察层 {c.get("paper_observation_tier", "none")}'
                )
            invalidation = c.get('thesis_invalidation') or []
            if invalidation:
                lines.append('- 失效条件：')
                for item in invalidation[:3]:
                    lines.append(f'  - {item}')
            if c.get('coinank_status'):
                lines.append(
                    f'- 衍生品增强：CoinAnk {c.get("coinank_status")}｜爆多1h {float(c.get("long_liq_1h_usd") or 0):.0f}｜爆空1h {float(c.get("short_liq_1h_usd") or 0):.0f}｜买卖比 {float(c.get("buy_sell_ratio_1h") or 0):.2f}'
                )
                lines.append(
                    f'- OI分布：Binance {float(c.get("binance_oi_share_pct") or 0):.1f}%｜OKX {float(c.get("okx_oi_share_pct") or 0):.1f}%｜OKX OI 5m/15m/1h {float(c.get("coinank_oi_change_5m_pct") or 0):.2f}%/{float(c.get("coinank_oi_change_15m_pct") or 0):.2f}%/{float(c.get("coinank_oi_change_1h_pct") or 0):.2f}%'
                )
            reasons = c.get('reasons') or []
            risks = c.get('risks') or []
            if reasons:
                lines.append('- 证据：')
                for r in reasons[:6]:
                    lines.append(f'  - {r}')
            if risks:
                lines.append('- 风险：')
                for r in risks[:6]:
                    lines.append(f'  - {r}')
            lines.append('')
    if onchain_observation_pool:
        lines.append('## 链上观察池（OnchainOS C档）')
        lines.append('原则：只做前置发现/聪明钱确认/安全过滤；不是开仓信号，不进入主 paper entries，不自动下单。')
        onchain_rows = sorted(onchain_observation_pool.get('candidates') or [], key=lambda x: float(x.get('score') or 0), reverse=True)
        if not onchain_rows:
            lines.append('暂无链上观察候选。')
        for i, c in enumerate(onchain_rows[:10], 1):
            lines.append(f'### C{i}. {c.get("symbol", "UNKNOWN")}｜{c.get("tier", "C_ONCHAIN_OBSERVE")}｜{int(float(c.get("score") or 0))}分')
            lines.append(f'- 链/合约：{c.get("chain", "unknown")}｜{c.get("contract", "-")}')
            lines.append(f'- 来源：{",".join(str(x) for x in (c.get("source") or [])[:4])}｜趋势 #{c.get("onchain_trending_rank", "-")}｜聪明钱 {int(float(c.get("smart_money_signal_count") or 0))} 笔/${float(c.get("smart_money_amount_usd") or 0):.0f}')
            reasons = c.get('reasons') or []
            risks = c.get('risks') or []
            if reasons:
                lines.append('- 链上证据：' + '；'.join(str(x) for x in reasons[:3]))
            if risks:
                lines.append('- 风险过滤：' + '；'.join(str(x) for x in risks[:3]))
            lines.append('- 执行：观察层，allow_trade=false，需等 OKX 合约结构确认。')
            lines.append('')
    return '\n'.join(lines)
