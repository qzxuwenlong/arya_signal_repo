from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


def _f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None or x == '':
            return default
        return float(x)
    except Exception:
        return default


def _ticker_volume_usd(ticker: Dict[str, Any]) -> float:
    quote = _f(ticker.get('volCcyQuote24h'))
    if quote:
        return quote
    # OKX swap tickers do not always expose volCcyQuote24h consistently.
    # For preselection we prefer a stable activity proxy over undercounting low-price memes.
    return _f(ticker.get('volCcy24h'))


def _ticker_change_24h_pct(ticker: Dict[str, Any]) -> float:
    last = _f(ticker.get('last'))
    open24h = _f(ticker.get('open24h'))
    return ((last - open24h) / open24h * 100) if last and open24h else 0.0


def extract_social_tickers(
    posts: List[Dict[str, Any]],
    *,
    symbol_aliases: Optional[Dict[str, str]] = None,
    allowed_symbols: Optional[set[str]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Extract ticker mentions from social posts for candidate-pool boosting.

    This is intentionally an observation signal only. It should help the scanner
    inspect talked-about OKX contracts, not create trade entries by itself.
    """
    aliases = {str(k).upper(): str(v).upper() for k, v in (symbol_aliases or {}).items()}
    allowed = {str(s).upper() for s in allowed_symbols} if allowed_symbols else None
    out: Dict[str, Dict[str, Any]] = {}

    def add(raw: str, post: Dict[str, Any]) -> None:
        token = str(raw or '').upper().strip()
        if not token or len(token) > 16:
            return
        symbol = aliases.get(token, token)
        if allowed is not None and symbol not in allowed:
            return
        row = out.setdefault(symbol, {
            'social_mention_count': 0,
            'social_sources': set(),
            'social_aliases': set(),
            'social_examples': [],
        })
        row['social_mention_count'] += 1
        if token != symbol:
            row['social_aliases'].add(token)
        source = post.get('source') or post.get('account') or post.get('author') or 'social'
        row['social_sources'].add(str(source))
        if len(row['social_examples']) < 3:
            row['social_examples'].append({
                'id': post.get('id'),
                'created_at': post.get('created_at'),
                'text': str(post.get('text') or '')[:220],
            })

    for post in posts or []:
        text = str(post.get('text') or '')
        seen_symbols: set[str] = set()
        raw_by_symbol: Dict[str, str] = {}
        for match in re.findall(r'\$([A-Za-z][A-Za-z0-9]{1,15})\b', text):
            token = match.upper()
            symbol = aliases.get(token, token)
            seen_symbols.add(symbol)
            raw_by_symbol.setdefault(symbol, token)
        if allowed is not None:
            for sym in set(allowed) | set(aliases):
                if re.search(rf'(?<![A-Za-z0-9_]){re.escape(sym)}(?![A-Za-z0-9_])', text, flags=re.IGNORECASE):
                    token = sym.upper()
                    symbol = aliases.get(token, token)
                    seen_symbols.add(symbol)
                    raw_by_symbol.setdefault(symbol, token)
        for symbol in seen_symbols:
            add(raw_by_symbol.get(symbol, symbol), post)

    normalized: Dict[str, Dict[str, Any]] = {}
    for symbol, row in out.items():
        normalized[symbol] = {
            'social_mention_count': row['social_mention_count'],
            'social_sources': sorted(row['social_sources']),
            'social_aliases': sorted(row['social_aliases']),
            'social_examples': row['social_examples'],
        }
    return normalized


def select_okx_opportunity_pool(
    instruments: List[dict],
    tickers: List[dict],
    *,
    rank_lookup: Optional[Dict[str, Dict[str, Any]]] = None,
    social_lookup: Optional[Dict[str, Dict[str, Any]]] = None,
    onchain_lookup: Optional[Dict[str, Dict[str, Any]]] = None,
    limit: int = 30,
    min_24h_volume_usd: float = 50_000,
) -> List[Dict[str, Any]]:
    """Select a dynamic OKX USDT-swap opportunity pool from live market tickers.

    This is a cheap prefilter: it avoids deep OI/book/funding calls for the whole market,
    while still escaping the old fixed watchlist trap.
    """
    rank_lookup = rank_lookup or {}
    social_lookup = social_lookup or {}
    onchain_lookup = onchain_lookup or {}
    live_ids = {r.get('instId') for r in instruments if str(r.get('instId', '')).endswith('-USDT-SWAP') and r.get('state', 'live') == 'live'}
    if not live_ids:
        live_ids = {r.get('instId') for r in tickers if str(r.get('instId', '')).endswith('-USDT-SWAP')}
    ticker_by_id = {r.get('instId'): r for r in tickers if r.get('instId') in live_ids}
    rows: List[Dict[str, Any]] = []
    for inst_id, ticker in ticker_by_id.items():
        symbol = str(inst_id).replace('-USDT-SWAP', '')
        social = social_lookup.get(symbol, {})
        onchain = onchain_lookup.get(symbol, {})
        social_mentions = int(social.get('social_mention_count') or 0)
        onchain_score = _f(onchain.get('onchain_observation_score'))
        volume_usd = _ticker_volume_usd(ticker)
        if volume_usd < min_24h_volume_usd and not social_mentions and onchain_score <= 0:
            continue
        change_pct = _ticker_change_24h_pct(ticker)
        rank = rank_lookup.get(symbol, {}).get('binance_hype_rank')
        hype_bonus = max(0.0, 35.0 - float(rank)) if rank else 0.0
        social_bonus = min(45.0, social_mentions * 18.0) if social_mentions else 0.0
        onchain_bonus = min(55.0, onchain_score * 1.25) if onchain_score else 0.0
        meme_bonus = 12.0 if symbol in {'BOME', 'WIF', 'PEPE', 'ORDI', 'DOGE', 'BONK', 'FLOKI', 'SHIB', 'NEIRO'} else 0.0
        # log10-like volume score without importing math edge cases into tests.
        volume_score = min(45.0, len(str(int(max(volume_usd, 1)))) * 5.0)
        volatility_score = min(35.0, abs(change_pct) * 1.5)
        selection_score = volume_score + volatility_score + hype_bonus + social_bonus + onchain_bonus + meme_bonus
        row = {
            'inst_id': inst_id,
            'symbol': symbol,
            'price': _f(ticker.get('last')),
            'change_24h_pct': round(change_pct, 6),
            'volume_24h_usd': volume_usd,
            'selection_score': round(selection_score, 6),
        }
        if rank:
            row['binance_hype_rank'] = rank
        if social_mentions:
            row.update({k: v for k, v in social.items() if k.startswith('social_')})
        if onchain_score > 0:
            row.update({k: v for k, v in onchain.items() if k.startswith('onchain_')})
        rows.append(row)
    rows.sort(key=lambda r: (-float(r.get('selection_score') or 0), -float(r.get('onchain_observation_score') or 0), -int(r.get('social_mention_count') or 0), -float(r.get('volume_24h_usd') or 0), str(r.get('inst_id'))))
    return rows[:limit]
