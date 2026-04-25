from __future__ import annotations

import os
from pathlib import Path

PROXY_URL = os.getenv('ARYA_PROXY_URL', 'http://127.0.0.1:7897')
VAULT_PATH = os.getenv('OBSIDIAN_VAULT_PATH') or '/home/hpp/vault'
PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = PROJECT_ROOT / 'runs'
DATA_DIR = PROJECT_ROOT / 'data'
MARKET_STATE_DB = DATA_DIR / 'market_state.sqlite'

# V1/V1.5 安全边界：代码层永久禁止自动下单。
ORDER_EXECUTION_ENABLED = False
