from __future__ import annotations

import os
from pathlib import Path

PROXY_URL = os.getenv('ARYA_PROXY_URL', 'http://127.0.0.1:7897')
VAULT_PATH = os.getenv('OBSIDIAN_VAULT_PATH') or '/home/hpp/vault'
PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = PROJECT_ROOT / 'runs'
DATA_DIR = PROJECT_ROOT / 'data'
MARKET_STATE_DB = DATA_DIR / 'market_state.sqlite'


def use_coinank_enrichment() -> bool:
    """CoinAnk is an optional enhancement; default scanner mode is OKX-only."""
    mode = os.getenv('ARYA_DERIVATIVES_MODE', '').strip().lower()
    if mode in {'okx_only', 'okx-only'}:
        return False
    if mode in {'okx_coinank', 'coinank', 'okx+coinank'}:
        return True
    return os.getenv('ARYA_USE_COINANK', '').strip().lower() in {'1', 'true', 'yes', 'on'}


# V1/V1.5 安全边界：代码层永久禁止自动下单。
ORDER_EXECUTION_ENABLED = False

