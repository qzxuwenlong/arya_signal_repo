from __future__ import annotations

import argparse
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

USER_AGENT = 'arya-extreme-funding-radar/1.0 (Hermes; no-order-execution)'
OKX_TICKERS_URL = 'https://www.okx.com/api/v5/market/tickers?instType=SWAP'
OKX_FUNDING_URL = 'https://www.okx.com/api/v5/public/funding-rate?instId='


def _request_json(url: str, timeout: int = 10) -> Any:
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept-Encoding': 'identity'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode('utf-8', errors='replace')
    return json.loads(raw)


def _f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None or x == '':
            return default
        return float(x)
    except Exception:
        return default


def _change_24h_pct(ticker: Dict[str, Any]) -> float:
    last = _f(ticker.get('last'))
    open24h = _f(ticker.get('open24h'))
    return (last - open24h) / open24h * 100 if last and open24h else 0.0


def _volume_24h(ticker: Dict[str, Any]) -> float:
    return _f(ticker.get('volCcyQuote24h')) or _f(ticker.get('volCcy24h'))


def fetch_okx_usdt_swap_tickers() -> List[Dict[str, Any]]:
    payload = _request_json(OKX_TICKERS_URL, timeout=12)
    rows = payload.get('data') or []
    return [r for r in rows if str(r.get('instId', '')).endswith('-USDT-SWAP')]


def fetch_okx_funding(inst_id: str) -> Dict[str, Any]:
    payload = _request_json(OKX_FUNDING_URL + urllib.parse.quote(inst_id), timeout=8)
    rows = payload.get('data') or []
    return rows[0] if rows else {}


def scan_extreme_funding(
    *,
    min_abs_funding_pct: float = 0.05,
    top_n: int = 20,
    max_prefetch: int = 80,
    min_volume_24h: float = 50_000,
) -> Dict[str, Any]:
    tickers = fetch_okx_usdt_swap_tickers()
    tickers = [t for t in tickers if _volume_24h(t) >= min_volume_24h]
    tickers.sort(key=lambda t: (abs(_change_24h_pct(t)), _volume_24h(t)), reverse=True)
    selected = tickers[:max_prefetch]

    alerts: List[Dict[str, Any]] = []
    errors: List[str] = []
    for t in selected:
        inst_id = str(t.get('instId'))
        try:
            funding = fetch_okx_funding(inst_id)
            funding_pct = _f(funding.get('fundingRate')) * 100
            if abs(funding_pct) < min_abs_funding_pct:
                continue
            change_24h = _change_24h_pct(t)
            row = {
                'inst_id': inst_id,
                'symbol': inst_id.replace('-USDT-SWAP', ''),
                'last': _f(t.get('last')),
                'change_24h_pct': round(change_24h, 6),
                'volume_24h_usd': _volume_24h(t),
                'funding_rate_pct': round(funding_pct, 6),
                'funding_time': funding.get('fundingTime'),
                'next_funding_time': funding.get('nextFundingTime'),
                'direction_hint': '多头拥挤/谨慎追多' if funding_pct > 0 else '空头拥挤/警惕爆空',
                'risk_note': '只预警不下单，需结合 OI/爆仓/盘口人工确认',
            }
            # More interesting when funding crowding aligns with a tail move.
            row['radar_score'] = round(min(100.0, abs(funding_pct) * 700 + abs(change_24h) * 1.2), 3)
            alerts.append(row)
        except Exception as e:
            errors.append(f'{inst_id}:{type(e).__name__}')
    alerts.sort(key=lambda r: (r['radar_score'], abs(r['funding_rate_pct'])), reverse=True)
    return {
        'ts': int(time.time()),
        'source': 'okx_public_funding_rate',
        'order_execution': 'disabled',
        'params': {
            'min_abs_funding_pct': min_abs_funding_pct,
            'top_n': top_n,
            'max_prefetch': max_prefetch,
            'min_volume_24h': min_volume_24h,
        },
        'scanned_prefetch': len(selected),
        'alerts': alerts[:top_n],
        'errors': errors[:20],
    }


def render_markdown(result: Dict[str, Any]) -> str:
    lines = [
        '# OKX 极端资金费率雷达',
        '',
        '原则：只预警，不自动下单；任何交易必须人工确认。',
        '',
        f"扫描：{result.get('scanned_prefetch', 0)} 个高波动/高成交合约",
        f"阈值：abs(funding) >= {result.get('params', {}).get('min_abs_funding_pct')}%",
        '',
    ]
    alerts = result.get('alerts') or []
    if not alerts:
        lines.append('暂无极端资金费率。')
        return '\n'.join(lines)
    lines.append('## 候选')
    for i, r in enumerate(alerts, 1):
        lines.append(f"### {i}. {r['inst_id']}｜funding {r['funding_rate_pct']:.4f}%｜score {r['radar_score']}")
        lines.append(f"- 24h：{r['change_24h_pct']:.2f}%｜24h量：{r['volume_24h_usd']:.0f}")
        lines.append(f"- 提示：{r['direction_hint']}")
        lines.append(f"- 风险：{r['risk_note']}")
        lines.append('')
    return '\n'.join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description='OKX all-market extreme funding radar. Alert only; no order execution.')
    ap.add_argument('--min-abs-funding-pct', type=float, default=float(os.getenv('FUNDING_MIN_ABS_PCT', '0.05')))
    ap.add_argument('--top-n', type=int, default=int(os.getenv('FUNDING_ALERT_TOP_N', '20')))
    ap.add_argument('--max-prefetch', type=int, default=int(os.getenv('FUNDING_MAX_PREFETCH', '80')))
    ap.add_argument('--min-volume-24h', type=float, default=float(os.getenv('FUNDING_MIN_VOLUME_24H', '50000')))
    ap.add_argument('--json-out', default=os.getenv('FUNDING_JSON_OUT', '/home/hpp/extreme_funding_latest.json'))
    ap.add_argument('--md-out', default=os.getenv('FUNDING_MD_OUT', '/home/hpp/extreme_funding_latest.md'))
    args = ap.parse_args()

    result = scan_extreme_funding(
        min_abs_funding_pct=args.min_abs_funding_pct,
        top_n=args.top_n,
        max_prefetch=args.max_prefetch,
        min_volume_24h=args.min_volume_24h,
    )
    md = render_markdown(result)
    Path(args.json_out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    Path(args.md_out).write_text(md, encoding='utf-8')
    print(md)
    print(f"JSON: {args.json_out}")
    print(f"MD: {args.md_out}")
    print('ORDER_EXECUTION: DISABLED')


if __name__ == '__main__':
    main()
