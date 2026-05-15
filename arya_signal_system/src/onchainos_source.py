from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Sequence, Tuple

from .config import ORDER_EXECUTION_ENABLED

DEFAULT_PROXY_ENV = {
    'https_proxy': 'http://127.0.0.1:7897',
    'http_proxy': 'http://127.0.0.1:7897',
    'all_proxy': 'socks5://127.0.0.1:7897',
    'HTTPS_PROXY': 'http://127.0.0.1:7897',
    'HTTP_PROXY': 'http://127.0.0.1:7897',
    'ALL_PROXY': 'socks5://127.0.0.1:7897',
}

DEFAULT_TRENDING_CHAINS = ['solana', 'base', 'xlayer']
DEFAULT_SIGNAL_CHAINS = ['solana', 'base', 'xlayer']
DEFAULT_MEMEPUMP_CHAINS = ['solana', 'xlayer', 'bsc']


@dataclass
class OnchainCommandResult:
    status: str
    data: Any
    stderr: str = ''
    stdout: str = ''


def _num(value: Any, default: float | None = 0.0) -> float | None:
    try:
        if value is None or value == '':
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _first(row: Dict[str, Any], keys: Sequence[str], default: Any = None) -> Any:
    for key in keys:
        cur: Any = row
        ok = True
        for part in key.split('.'):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                ok = False
                break
        if ok and cur not in (None, ''):
            return cur
    return default


def _symbol(row: Dict[str, Any]) -> str:
    return str(_first(row, ['symbol', 'tokenSymbol', 'token.symbol', 'baseAsset'], 'UNKNOWN')).upper()


def _name(row: Dict[str, Any]) -> str | None:
    value = _first(row, ['name', 'tokenName', 'token.name'])
    return str(value) if value not in (None, '') else None


def _contract(row: Dict[str, Any]) -> str | None:
    value = _first(row, ['contract', 'tokenContractAddress', 'tokenAddress', 'token.tokenAddress', 'address'])
    return str(value) if value not in (None, '') else None


def _list_payload(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ('data', 'list', 'tokens', 'items', 'result'):
            value = payload.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
            if isinstance(value, dict):
                nested = _list_payload(value)
                if nested:
                    return nested
        # Some CLI calls return a single object.
        if any(k in payload for k in ('symbol', 'tokenSymbol', 'token', 'tokenContractAddress', 'tokenAddress')):
            return [payload]
    return []


def _parse_stdout(stdout: str) -> Any:
    text = stdout.strip()
    if not text:
        return []
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # CLI sometimes prints logs before JSON; recover the first plausible JSON block.
    for start_char, end_char in (('[', ']'), ('{', '}')):
        start = text.find(start_char)
        end = text.rfind(end_char)
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                continue
    return []


def run_onchainos(args: Sequence[str], *, timeout: int = 8, env: Dict[str, str] | None = None) -> OnchainCommandResult:
    run_env = os.environ.copy()
    run_env.update(DEFAULT_PROXY_ENV)
    if env:
        run_env.update(env)
    cmd = ['onchainos', *list(args)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=run_env, check=False)
    except FileNotFoundError as e:
        return OnchainCommandResult('error:not_found', [], str(e))
    except subprocess.TimeoutExpired as e:
        return OnchainCommandResult('error:timeout', [], str(e), e.stdout or '')
    except Exception as e:  # keep Arya main scanner safe from OnchainOS surprises
        return OnchainCommandResult(f'error:{type(e).__name__}', [], str(e))

    if proc.returncode != 0:
        return OnchainCommandResult(f'error:exit_{proc.returncode}', [], proc.stderr or '', proc.stdout or '')
    return OnchainCommandResult('ok', _parse_stdout(proc.stdout), proc.stderr or '', proc.stdout or '')


def _base_candidate(row: Dict[str, Any], *, chain: str, source: str) -> Dict[str, Any]:
    return {
        'symbol': _symbol(row),
        'name': _name(row),
        'chain': chain,
        'chain_index': _first(row, ['chainIndex', 'chainId']),
        'contract': _contract(row),
        'source': [source],
        'tier': 'C_ONCHAIN_OBSERVE',
        'state': 'ONCHAIN_OBSERVE',
        'score': 0,
        'allow_trade': False,
        'manual_confirmation_required': True,
        'paper_observation_tier': 'observe',
        'price': _num(_first(row, ['price']), None),
        'market_cap_usd': _num(_first(row, ['marketCap', 'marketCapUsd', 'token.marketCapUsd']), None),
        'liquidity_usd': _num(_first(row, ['liquidity', 'liquidityUsd']), None),
        'holders': _num(_first(row, ['holders', 'token.holders', 'totalHolders', 'tags.totalHolders']), None),
        'onchain_trending_rank': None,
        'onchain_volume_1h_usd': None,
        'onchain_unique_traders': None,
        'onchain_buy_sell_ratio': None,
        'smart_money_signal_count': 0,
        'smart_money_amount_usd': 0.0,
        'smart_money_sold_ratio_pct': None,
        'top10_holder_pct': None,
        'dev_holding_pct': None,
        'bundlers_pct': None,
        'snipers_pct': None,
        'dev_rug_count': None,
        'onchain_fair_game': None,
        'reasons': [],
        'risks': ['链上观察，不是开仓信号；OKX 合约结构确认前不进主交易'],
    }


def normalize_trending_token(row: Dict[str, Any], *, rank: int, chain: str) -> Dict[str, Any]:
    c = _base_candidate(row, chain=chain, source='trending')
    buy_txs = _num(_first(row, ['buyTxs', 'txsBuy', 'buyTxCount1h']), 0.0) or 0.0
    sell_txs = _num(_first(row, ['sellTxs', 'txsSell', 'sellTxCount1h']), 0.0) or 0.0
    c.update({
        'onchain_trending_rank': rank,
        'onchain_volume_1h_usd': _num(_first(row, ['volume1H', 'volumeUsd1h', 'volume', 'volume24H']), None),
        'onchain_unique_traders': _num(_first(row, ['uniqueTraders']), None),
        'onchain_buy_sell_ratio': round(buy_txs / sell_txs, 6) if sell_txs > 0 else (None if buy_txs <= 0 else buy_txs),
        'price_change_onchain_pct': _num(_first(row, ['change', 'priceChange1H', 'priceChange24H']), None),
        'score': max(1, min(49, 18 + max(0, 12 - rank))),
    })
    c['reasons'].append(f'链上趋势榜第 {rank} 名，进入早期观察池')
    return c


def normalize_signal_row(row: Dict[str, Any], *, chain: str) -> Dict[str, Any]:
    c = _base_candidate(row, chain=chain, source='smart_money')
    count = _num(_first(row, ['triggerWalletCount', 'triggerAddressCount']), 0.0) or 0.0
    amount = _num(_first(row, ['amountUsd', 'amountUSD']), 0.0) or 0.0
    c.update({
        'smart_money_signal_count': int(count),
        'smart_money_amount_usd': amount,
        'smart_money_sold_ratio_pct': _num(_first(row, ['soldRatioPercent']), None),
        'top10_holder_pct': _num(_first(row, ['top10HolderPercent', 'token.top10HolderPercent', 'tags.top10HoldingsPercent']), None),
        'score': max(1, min(49, 20 + int(min(count * 4, 16)) + int(min(amount / 25_000, 10)))),
    })
    c['reasons'].append(f'聪明钱/鲸鱼/KOL 信号出现：{int(count)} 个钱包，约 ${amount:,.0f}')
    if c['top10_holder_pct'] is not None and c['top10_holder_pct'] >= 50:
        c['risks'].append('Top10 持仓过度集中，链上风险偏高')
    return c


def normalize_memepump_token(row: Dict[str, Any], *, chain: str, stage: str = 'NEW') -> Dict[str, Any]:
    c = _base_candidate(row, chain=chain, source=f'memepump_{stage.lower()}')
    market = row.get('market') if isinstance(row.get('market'), dict) else {}
    tags = row.get('tags') if isinstance(row.get('tags'), dict) else {}
    merged = {**row, **{f'market.{k}': v for k, v in market.items()}, **{f'tags.{k}': v for k, v in tags.items()}}
    c.update({
        'market_cap_usd': _num(_first(merged, ['marketCap', 'marketCapUsd', 'market.marketCapUsd']), c.get('market_cap_usd')),
        'onchain_volume_1h_usd': _num(_first(merged, ['volume1H', 'volumeUsd1h', 'market.volumeUsd1h']), None),
        'onchain_buy_sell_ratio': None,
        'top10_holder_pct': _num(_first(merged, ['top10HolderPercent', 'top10HoldingsPercent', 'tags.top10HoldingsPercent']), None),
        'dev_holding_pct': _num(_first(merged, ['devHoldingPercent', 'devHoldingsPercent', 'tags.devHoldingsPercent']), None),
        'bundlers_pct': _num(_first(merged, ['bundlersPercent', 'tags.bundlersPercent']), None),
        'snipers_pct': _num(_first(merged, ['snipersPercent', 'tags.snipersPercent']), None),
        'dev_rug_count': _num(_first(merged, ['devRugCount', 'rugPullCount', 'devLaunchedInfo.rugPullCount']), None),
        'score': 15,
    })
    buy_txs = _num(_first(merged, ['buyTxCount1h', 'market.buyTxCount1h']), 0.0) or 0.0
    sell_txs = _num(_first(merged, ['sellTxCount1h', 'market.sellTxCount1h']), 0.0) or 0.0
    if sell_txs > 0:
        c['onchain_buy_sell_ratio'] = round(buy_txs / sell_txs, 6)
    liq = _num(c.get('liquidity_usd'), 0.0) or 0.0
    dev = _num(c.get('dev_holding_pct'), 0.0) or 0.0
    bundlers = _num(c.get('bundlers_pct'), 0.0) or 0.0
    snipers = _num(c.get('snipers_pct'), 0.0) or 0.0
    rugs = _num(c.get('dev_rug_count'), 0.0) or 0.0
    fair = liq >= 10_000 and dev < 10 and bundlers < 10 and snipers < 15 and rugs <= 0
    c['onchain_fair_game'] = fair
    c['reasons'].append(f'memepump {stage} 新币进入链上观察池')
    if liq < 10_000:
        c['risks'].append('低流动性新币，滑点/归零风险高')
    if dev >= 10:
        c['risks'].append('dev 持仓偏高，需过滤')
    if bundlers >= 8:
        c['risks'].append('bundler 风险偏高')
    if snipers >= 12:
        c['risks'].append('sniper 风险偏高')
    if rugs > 0:
        c['risks'].append('dev rug 历史风险，禁止直接追')
    return c


def _identity(c: Dict[str, Any]) -> Tuple[str, str, str]:
    return (str(c.get('chain') or '').lower(), str(c.get('contract') or '').lower(), str(c.get('symbol') or '').upper())


def _merge_candidate(dst: Dict[str, Any], src: Dict[str, Any]) -> Dict[str, Any]:
    for source in src.get('source') or []:
        if source not in dst['source']:
            dst['source'].append(source)
    for key, value in src.items():
        if key in {'source', 'reasons', 'risks'}:
            continue
        if value not in (None, '', 0, 0.0) or dst.get(key) in (None, '', 0, 0.0):
            if key == 'score':
                dst[key] = min(49, max(_num(dst.get(key), 0) or 0, _num(value, 0) or 0) + 5)
            else:
                dst[key] = value
    for key in ('reasons', 'risks'):
        for item in src.get(key) or []:
            if item not in dst[key]:
                dst[key].append(item)
    dst['allow_trade'] = False
    dst['manual_confirmation_required'] = True
    dst['paper_observation_tier'] = 'observe'
    return dst


def build_onchain_observation_pool(candidates: Iterable[Dict[str, Any]], *, errors: Iterable[str] | None = None) -> Dict[str, Any]:
    merged: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for c in candidates:
        key = _identity(c)
        if key in merged:
            _merge_candidate(merged[key], c)
        else:
            row = dict(c)
            row['source'] = list(row.get('source') or [])
            row['reasons'] = list(row.get('reasons') or [])
            row['risks'] = list(row.get('risks') or [])
            row['allow_trade'] = False
            row['manual_confirmation_required'] = True
            row['paper_observation_tier'] = 'observe'
            merged[key] = row
    rows = sorted(merged.values(), key=lambda x: (_num(x.get('score'), 0) or 0, _num(x.get('smart_money_amount_usd'), 0) or 0, -(_num(x.get('onchain_trending_rank'), 999) or 999)), reverse=True)
    errs = list(errors or [])
    status = 'ok' if not errs else ('partial:' + str(len(errs)) + '_errors' if rows else 'error:no_data')
    return {
        'generated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'source': 'okx_onchainos',
        'source_status': {'onchainos': status, 'order_execution': 'disabled'},
        'order_execution_enabled': bool(ORDER_EXECUTION_ENABLED),
        'candidates': rows,
        'errors': errs,
    }


def onchain_lookup_from_pool(pool: Dict[str, Any] | None, *, allowed_symbols: set[str] | None = None) -> Dict[str, Dict[str, Any]]:
    """Convert a C-tier OnchainOS observation pool into OKX deep-scan boosts.

    This keeps OnchainOS as discovery/observation only: it can reserve OKX
    contract inspection slots for already-listed symbols, but never grants trade
    permission or writes main paper entries by itself.
    """
    allowed = {str(s).upper() for s in allowed_symbols} if allowed_symbols else None
    lookup: Dict[str, Dict[str, Any]] = {}
    if not isinstance(pool, dict):
        return lookup
    for c in pool.get('candidates') or []:
        if not isinstance(c, dict):
            continue
        symbol = str(c.get('symbol') or '').upper().strip()
        if not symbol or symbol == 'UNKNOWN':
            continue
        if allowed is not None and symbol not in allowed:
            continue
        sources = list(c.get('source') or [])
        score = _num(c.get('score'), 0.0) or 0.0
        if c.get('onchain_trending_rank') not in (None, ''):
            score += max(0.0, 20.0 - float(c.get('onchain_trending_rank') or 20))
        score += min(20.0, float(c.get('smart_money_signal_count') or 0) * 4.0)
        score += min(15.0, float(c.get('smart_money_amount_usd') or 0) / 25_000.0)
        row = lookup.setdefault(symbol, {
            'onchain_observation_score': 0.0,
            'onchain_sources': [],
            'onchain_observation_tier': c.get('tier') or 'C_ONCHAIN_OBSERVE',
            'onchain_chain': c.get('chain'),
            'onchain_contract': c.get('contract'),
        })
        row['onchain_observation_score'] = round(max(float(row.get('onchain_observation_score') or 0), score), 6)
        for source in sources:
            if source not in row['onchain_sources']:
                row['onchain_sources'].append(source)
    return lookup


Runner = Callable[[Sequence[str], int], Any]


def _coerce_runner_result(result: Any) -> OnchainCommandResult:
    if isinstance(result, OnchainCommandResult):
        return result
    if isinstance(result, dict):
        return OnchainCommandResult(str(result.get('status', 'ok')), result.get('data', []), str(result.get('stderr', '')), str(result.get('stdout', '')))
    return OnchainCommandResult('ok', result)


def collect_onchain_candidates(
    *,
    runner: Callable[..., Any] = run_onchainos,
    trending_chains: Sequence[str] = DEFAULT_TRENDING_CHAINS,
    signal_chains: Sequence[str] = DEFAULT_SIGNAL_CHAINS,
    memepump_chains: Sequence[str] = DEFAULT_MEMEPUMP_CHAINS,
    timeout: int = 8,
) -> Dict[str, Any]:
    candidates: List[Dict[str, Any]] = []
    errors: List[str] = []

    for chain in trending_chains:
        res = _coerce_runner_result(runner(['token', 'trending', '--chains', chain, '--sort-by', '5', '--time-frame', '2'], timeout=timeout))
        if res.status == 'ok':
            for idx, row in enumerate(_list_payload(res.data), 1):
                candidates.append(normalize_trending_token(row, rank=idx, chain=chain))
        else:
            errors.append(f'trending:{chain}:{res.status}')

    for chain in signal_chains:
        res = _coerce_runner_result(runner(['signal', 'list', '--chain', chain, '--wallet-type', '1', '--min-amount-usd', '1000'], timeout=timeout))
        if res.status == 'ok':
            for row in _list_payload(res.data):
                candidates.append(normalize_signal_row(row, chain=chain))
        else:
            errors.append(f'signal:{chain}:{res.status}')

    for chain in memepump_chains:
        res = _coerce_runner_result(runner(['memepump', 'tokens', '--chain', chain, '--stage', 'NEW'], timeout=timeout))
        if res.status == 'ok':
            for row in _list_payload(res.data):
                candidates.append(normalize_memepump_token(row, chain=chain, stage='NEW'))
        else:
            errors.append(f'memepump:{chain}:{res.status}')

    return build_onchain_observation_pool(candidates, errors=errors)


def write_onchain_candidates(pool: Dict[str, Any], path: str | Path) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(pool, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def main() -> None:
    ap = argparse.ArgumentParser(description='Collect OKX OnchainOS candidates as Arya observation pool. No order execution.')
    ap.add_argument('--output', default='runs/onchainos_candidates.json')
    ap.add_argument('--timeout', type=int, default=8)
    ap.add_argument('--trending-chains', default=','.join(DEFAULT_TRENDING_CHAINS))
    ap.add_argument('--signal-chains', default=','.join(DEFAULT_SIGNAL_CHAINS))
    ap.add_argument('--memepump-chains', default=','.join(DEFAULT_MEMEPUMP_CHAINS))
    args = ap.parse_args()

    pool = collect_onchain_candidates(
        trending_chains=[x.strip() for x in args.trending_chains.split(',') if x.strip()],
        signal_chains=[x.strip() for x in args.signal_chains.split(',') if x.strip()],
        memepump_chains=[x.strip() for x in args.memepump_chains.split(',') if x.strip()],
        timeout=args.timeout,
    )
    write_onchain_candidates(pool, args.output)
    print(json.dumps({'output': args.output, 'candidates': len(pool.get('candidates') or []), 'status': pool.get('source_status', {}).get('onchainos'), 'order_execution': 'disabled'}, ensure_ascii=False, sort_keys=True))
    print('ORDER_EXECUTION: DISABLED')


if __name__ == '__main__':
    main()
