from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List


def render_markdown_report(candidates: Iterable[Dict[str, Any]], source_status: Dict[str, str] | None = None) -> str:
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
        return '\n'.join(lines)
    for i, c in enumerate(rows, 1):
        lines.append(f'### {i}. {c.get("symbol", "UNKNOWN")}｜{c.get("state", "WATCH_ONLY")}｜{c.get("score", 0)}分')
        lines.append(f'- 方向：{c.get("direction", "待确认")}')
        lines.append(f'- 策略：{c.get("strategy", "只观察")}')
        lines.append(f'- 执行：不自动下单，需人工确认')
        if 'local_history_ready' in c:
            ready = 'ready' if c.get('local_history_ready') else 'warming_up'
            lines.append(
                f'- 本地燃料：{ready}｜OI 1h {float(c.get("oi_change_1h_pct") or 0):.2f}%｜量 1h {float(c.get("volume_change_1h_pct") or 0):.2f}%｜价 1h {float(c.get("price_change_1h_pct") or 0):.2f}%'
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
    return '\n'.join(lines)
