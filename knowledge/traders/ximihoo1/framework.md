# 熹米Cycler💦（@ximihoo1）可执行交易框架｜初版

> 数据状态：当前仅 18 条近端推文，框架为“可执行假设版”。适合先接入系统做低权重辅助因子，不适合作为独立交易引擎。补齐 1000 条后必须重蒸馏。

## 0. 框架定位

@ximihoo1 框架适合承担：

```text
大周期资产轮动判断器 + 追高风险过滤器 + 多日级别技术结构确认器
```

不适合单独承担：

```text
5m 高频开仓器
meme 拉盘扫描器
自动下单信号源
```

在 Arya Signal System 中，建议作为 `knowledge_factor.ximihoo_cycle`，权重低于实时燃料指标，但高于普通新闻噪音。

---

## 1. 输入数据

### 1.1 必需行情

```text
BTCUSDT: 1D / 2D / 3D K线
ETHUSDT: 1D / 2D / 3D K线
黄金/白银代理: XAUUSD/XAGUSD 或 GLD/SLV
美股代理: SPX/NDX/QQQ
MSTR 或相关 BTC proxy
```

### 1.2 技术指标

```text
MACD: 1D / 2D / 3D
KDJ: 1D / 2D / 3D
价格阶段目标位: 手工或系统估计
近端涨幅: 1D / 3D / 7D
```

### 1.3 衍生品/燃料指标

```text
OI 当前值
OI 1h / 4h / 24h 变化
Funding
盘口深度/点差
清算地图 1D / 30D（可用 CoinAnk/CoinGlass 增强；无则降级）
```

---

## 2. 状态机

### 2.1 CYCLE_BULLISH_BACKGROUND：周期偏多背景

触发条件：

```text
BTC 大周期结构未破
AND 2D/3D MACD 未死叉或处于修复中
AND 资产轮动叙事仍支持 BTC/crypto
```

动作：

```text
允许系统寻找顺势多头机会；
但不直接追高；
需要等待燃料指标或回踩确认。
```

风险：

```text
如果价格已完成阶段目标，必须叠加 NO_CHASE_ZONE。
```

---

### 2.2 NO_CHASE_ZONE：目标完成后禁止追高

触发条件：

```text
价格触及或超过阶段目标区
OR 近 3D/7D 涨幅过大
OR 用户/知识库标记“目标已完成”
```

典型证据：

```text
“比特币已完成4月目标：$75K-80K，目前盘面风险较高，不要盲目追高了”
```

动作：

```text
禁止新增追多；
已有多单考虑减仓/保护止盈；
只允许等待回踩、震荡消化或新结构确认。
```

系统规则：

```python
if state == 'NO_CHASE_ZONE':
    allow_new_long = False
    allow_grid = only_if_low_leverage_and_range_confirmed
    alert_type = 'risk_warning'
```

---

### 2.3 DIVERGENCE_RISK：顶背离风险

触发条件：

```text
价格创新高
AND KDJ 或 MACD 没有创新高，反而向下
```

动作：

```text
降低多头评分；
提高退出风险分；
提醒不要追高；
若 OI/Funding 同时过热，标记 EXIT_RISK。
```

伪代码：

```python
if price_new_high and (kdj_lower_high or macd_lower_high):
    risk_score += 25
    long_score -= 20
    tags.append('ximihoo_divergence_risk')
```

---

### 2.4 MACD_BELOW_ZERO_DEATH_CROSS：0轴下死叉深跌风险

触发条件：

```text
日线 MACD 位于 0 轴下方
AND DIF 下穿 DEA
```

动作：

```text
禁止抄底；
禁止网格下沿接飞刀；
若价格跌破关键位，优先顺势防守而不是逆势加仓。
```

适用对象：

```text
黄金/白银
BTC/ETH
高 beta 山寨
```

---

### 2.5 LIQUIDATION_WINDOW_CONFLICT：清算窗口冲突

触发条件：

```text
1D 清算图显示短期爆空
AND 30D 清算图显示长期爆多
```

解释：

```text
短期可能先上冲扫空；
中长期仍有清理多头杠杆的风险；
不应把短线 squeeze 误判为无风险趋势。
```

动作：

```text
允许短线提醒；
降低持仓周期；
禁止高杠杆隔夜；
要求更严格止盈。
```

---

## 3. 评分因子设计

### 3.1 ximihoo_cycle_score

```text
+20 BTC 大周期强势
+15 2D/3D MACD 未死叉
+10 3D KDJ 结构仍有延伸
+10 BTC 相对美股/黄金/白银更强
-20 目标区已完成
-25 顶背离
-30 日线 MACD 0轴下死叉
```

输出：

```text
>= 40: cycle_supportive
10 ~ 39: neutral
< 10: defensive
< -20: high_risk
```

### 3.2 no_chase_penalty

```text
目标完成: -30
3D 涨幅过大: -15
Funding 过热: -15
OI 过热但价格不再创新高: -20
顶背离: -25
```

### 3.3 liquidation_conflict_penalty

```text
1D/30D 清算方向冲突: -10 ~ -20
清算方向与趋势方向相反: -15
```

---

## 4. 与现有 Arya Signal System 的集成方式

### 4.1 候选币增强字段

给每个候选加入：

```json
{
  "ximihoo_cycle_state": "cycle_supportive|neutral|defensive|high_risk",
  "ximihoo_no_chase": true,
  "ximihoo_divergence_risk": false,
  "ximihoo_liquidation_conflict": true,
  "ximihoo_notes": ["目标完成后禁止追高", "1D爆空但30D爆多"]
}
```

### 4.2 报告展示

Markdown 报告中增加：

```text
知识库因子：ximihoo1
- 周期状态：cycle_supportive
- 追高过滤：NO_CHASE_ZONE
- 技术风险：KDJ/MACD 顶背离
- 清算冲突：1D vs 30D
- 建议：不追高，等回踩或结构延伸确认
```

---

## 5. 执行规则

### 5.1 多头允许条件

```text
允许多头建议，仅当：
1. cycle_state != high_risk
2. no_chase_zone = false
3. divergence_risk = false
4. funding 不极端
5. OI 上升能被价格/成交量确认
```

### 5.2 禁止追高条件

```text
任何一个满足即禁止追高：
- 阶段目标已达成；
- KDJ/MACD 顶背离；
- Funding 极端为正；
- OI 高位扩张但价格滞涨；
- 1D 与 30D 清算方向冲突且长期爆多。
```

### 5.3 抄底禁止条件

```text
- 日线 MACD 0轴下死叉；
- 价格跌破关键结构位；
- OI 未释放；
- 清算图下方多头密集仍未清理。
```

---

## 6. 人工确认模板

当系统发出 ximihoo1 风险提示时，Telegram 文案：

```text
【ximihoo1 周期因子】
标的：BTC/ETH/xxx
状态：NO_CHASE_ZONE / DIVERGENCE_RISK / CYCLE_SUPPORTIVE
证据：2D MACD、3D KDJ、目标位、清算窗口
建议：只提醒，不下单。若已持仓，考虑保护止盈；若未持仓，等待回踩。
```

---

## 7. 低样本权重

当前只有 18 条推文，因此建议：

```text
ximihoo1 因子权重 <= 10%
只做 risk filter，不做 primary entry signal
不允许单独触发开仓建议
```

补齐 1000 条后，若框架稳定，可提升到：

```text
15% ~ 25%，主要用于周期状态和风险过滤
```

---

## 8. 下一步重蒸馏要求

补齐 1000 条后必须重新计算：

1. 高频标的；
2. 预测命中/失败案例；
3. 各资产轮动顺序；
4. 技术指标实际组合；
5. 高互动推文是否集中在风险提示还是趋势提示；
6. 与 Arya_web3、BTC_Alert_ 等知识库是否冲突。
