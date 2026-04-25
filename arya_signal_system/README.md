# Arya Signal System V1.5

AI 辅助的热币/合约燃料/链上热度结构识别系统。

## 边界

- V1.5 只扫描、评分、记录本地市场状态、生成建议。
- 不自动下单。
- 任何交易必须人工确认。

## 数据源

- OKX public API：合约列表、ticker、K线、盘口、OI、资金费率。
- Binance Web3 public API：Trending/热度榜。
- 本地 SQLite：`data/market_state.sqlite`，记录 price、volume_1h、open_interest_usd、funding、depth、spread，并计算 1h 变化。
- CoinAnk：检测 API key 状态；后续只作为爆仓、多空比、全网 OI 的增强验证源。
- Obsidian：`/home/hpp/vault/traders/Arya_web3/` 作为知识库依据。

## 运行

```bash
cd /home/hpp/xm/arya_signal_system
./run_scan.sh --limit 8
```

输出：

- `runs/latest.md`
- `runs/latest.json`
- `data/market_state.sqlite`

## 测试

```bash
cd /home/hpp/xm/arya_signal_system
pytest -q
```
