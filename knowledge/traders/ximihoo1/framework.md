# 熹米Cycler💦（@ximihoo1）可执行交易框架｜1000 条重蒸馏版

> 目标：把 @ximihoo1 的周期资产轮动、BTC 锚点、技术结构、清算风险，转成 Arya Signal System 可执行的评分因子和状态机。交易执行仍需人工确认。

## 0. 使用边界

```text
适合：BTC 周期过滤、山寨追高过滤、清算冲突过滤、热币合约风控
不适合：独立 5m 开仓、meme 抢跑、自动交易
默认权重：15%-25% 风控层权重，不作为唯一买卖依据
```

## 1. 输入数据

### 1.1 市场数据

```text
BTC/USDT 1h/4h/1d/1w K线
ETH/USDT 1h/4h/1d K线
TOTAL2/TOTAL3 或山寨指数
OKX/Binance 合约 OI
Funding rate
成交量变化
爆仓/清算热力图（如可用）
美股指数：Nasdaq/SPX
黄金/白银/石油价格
```

### 1.2 知识库数据

```text
/home/hpp/vault/traders/ximihoo1/theory.md
/home/hpp/vault/traders/ximihoo1/framework.md
/home/hpp/vault/traders/ximihoo1/sources.md
/home/hpp/vault/traders/ximihoo1/raw/tweets_raw.json
```

## 2. 状态机

新增 `ximihoo_macro_state`：

```text
CYCLE_RISK_ON       BTC 长周期/风险资产偏强，可以允许热币候选进入观察
BTC_TARGET_RISK     BTC 已进入目标/清算/追高风险区，禁止追多
ALT_CONFIRMING      BTC 反弹，山寨开始跟随，允许低仓位观察
ALT_WEAKNESS        BTC 反弹但山寨不跟，山寨/meme 降权
LIQUIDATION_CONFLICT 1D/30D 清算方向冲突，降低仓位或只观察
NO_CHASE            社交情绪过热/目标价已到/资金费率偏热，禁止追高
```

与现有系统映射：

```text
CYCLE_RISK_ON + local_fuel_ready -> WATCH_ONLY 或 GRID_ALLOWED
BTC_TARGET_RISK -> EXIT_RISK / WATCH_ONLY
ALT_CONFIRMING -> TREND_ALERT 候选加分，但仍需本地燃料确认
ALT_WEAKNESS -> meme 候选减分
LIQUIDATION_CONFLICT -> 禁止普通网格扩大仓位
NO_CHASE -> 禁止开新追多单
```

## 3. 评分因子

### 3.1 ximihoo_cycle_bias_score，0-20 分

```text
+8 BTC 1D/1W 趋势向上，价格在关键均线之上
+4 ETH 同步或不明显拖累
+4 山寨总市值相对 BTC 不再创新低
+4 美股/黄金等风险偏好不冲突
-8 美股或风险资产处在诱多/末端反弹信号
-6 BTC 到达预设目标区间后转弱
```

### 3.2 ximihoo_no_chase_risk，0-25 分，越高越危险

```text
+8 BTC 已到目标区间或短期涨幅过大
+5 社交平台一致喊山寨季/暴富/冲
+5 meme 标的 24h 涨幅过大但 OI/资金费率过热
+4 价格接近清算密集区上方
+3 成交量放大但主动买盘衰竭
```

触发：

```text
no_chase_risk >= 15 -> 禁止追多
no_chase_risk >= 20 -> 标记 EXIT_RISK
```

### 3.3 ximihoo_alt_relative_strength，-20 到 +20

```text
+8 BTC 反弹时山寨指数同步反弹
+5 目标币成交量增速 > BTC 成交量增速
+4 目标币价格结构强于 BTC
+3 Funding 未极端拥挤
-8 BTC 反弹但山寨不涨
-5 BTC 横盘时山寨继续下跌
-4 目标币 OI 增加但价格不涨
-3 社交过热但盘口承接弱
```

### 3.4 ximihoo_liquidation_conflict，0-20 分，越高越危险

```text
+8 1D 清算方向与 30D 清算方向相反
+5 短期挤空后长期多头清算池更大
+4 Funding 正值过热且价格靠近上方清算带
+3 OI 快速增加但现货量不同步
```

触发：

```text
>= 12 -> LIQUIDATION_CONFLICT
>= 16 -> EXIT_RISK
```

### 3.5 ximihoo_failed_breakout_reclaim，0-15 分

用于捕捉博主“失败突破有时更看涨”的规则：

```text
+5 跌破关键位后快速收回
+4 跌破时成交量放大但没有延续下跌
+3 OI 去杠杆后价格站回关键位
+3 Funding 从过热回落
```

限制：

```text
只有 BTC/ETH/主流币适用。
meme 小币不得单独用该因子开仓。
```

## 4. 候选池规则

### 4.1 允许进入候选池

```text
BTC 未处于 BTC_TARGET_RISK
山寨相对强度 >= 0
no_chase_risk < 15
local_history_ready = true
ORDER_EXECUTION_ENABLED = False
```

### 4.2 降权或剔除

```text
BTC 到达目标区间且风险堆积
山寨没有跟 BTC 反弹
目标币属于妖币/土狗且合约 OI 异常上升
清算方向冲突严重
Funding 极端正值
社交已经全网 FOMO
```

## 5. 开仓建议逻辑，仅提醒不下单

### 5.1 可推送观察信号

```text
if arya_score >= 50
and ximihoo_no_chase_risk < 15
and ximihoo_liquidation_conflict < 12
and alt_relative_strength >= 0
and local_history_ready:
    推送“可观察，不自动下单”
```

### 5.2 风险提醒信号

```text
if ximihoo_no_chase_risk >= 15
or ximihoo_liquidation_conflict >= 12
or BTC_TARGET_RISK:
    推送“不要追高/降低仓位/人工复核”
```

### 5.3 禁止信号

```text
妖币暴涨 + 合约 OI 暴增 + Funding 极热 -> 禁止合约
BTC 反弹到目标区间 + 山寨不跟 -> 禁止追山寨
1D 爆空但 30D 爆多 + 多头拥挤 -> 禁止扩大网格
```

## 6. 仓位规则

```text
基础仓位 <= 1R
NO_CHASE -> 0R 新仓
LIQUIDATION_CONFLICT -> <= 0.25R，仅观察或极轻仓
ALT_CONFIRMING + local fuel ok -> <= 0.5R 提醒
CYCLE_RISK_ON + 多源确认 -> <= 1R，但仍需人工确认
```

## 7. 与 Arya Signal System 的集成建议

建议新增模块：

```text
src/knowledge_filters/ximihoo1.py
```

输出字段：

```json
{
  "ximihoo_cycle_state": "BTC_TARGET_RISK",
  "ximihoo_cycle_bias_score": 8,
  "ximihoo_no_chase_risk": 18,
  "ximihoo_alt_relative_strength": -6,
  "ximihoo_liquidation_conflict": 13,
  "ximihoo_action": "NO_CHASE",
  "ximihoo_reason": "BTC 进入目标区间，山寨未同步，清算方向冲突"
}
```

对总分影响：

```text
TREND_ALERT 加分最多 +10
NO_CHASE 扣分 -20
LIQUIDATION_CONFLICT 扣分 -15
ALT_WEAKNESS 扣分 -10
FAILED_BREAKOUT_RECLAIM 对 BTC/ETH 加分 +8，对 meme 不加分
```

## 8. 报告模板

```text
## ximihoo1 周期过滤
状态：BTC_TARGET_RISK / NO_CHASE
结论：不建议追高
原因：BTC 已完成目标区间，山寨未同步，合约风险堆积
动作：只观察；如已有仓位，人工复核是否减仓
```

## 9. 安全边界

```text
ORDER_EXECUTION_ENABLED 必须保持 False
任何交易必须人工确认
ximihoo1 因子只做过滤和建议，不自动调用交易 API
```

## 10. 最小实现优先级

第一阶段只实现 4 个字段：

```text
btc_target_risk
no_chase_risk
alt_relative_strength
liquidation_conflict
```

第二阶段再实现：

```text
macro_asset_rotation
failed_breakout_reclaim
technical_divergence
```

## 11. 重蒸馏完成

本文件已基于 1000 条 X API v2 推文重蒸馏。相比 18 条 RSS 初版，当前版本可以进入系统设计，但仍必须经过回测/观察验证。
