# 熹米Cycler💦（@ximihoo1）数据源与证据索引｜初版

## 1. 抓取状态

用户请求：

```text
拉取 @ximihoo1 最近 1000 条推文，并蒸馏该博主
```

实际完成：

```text
账号：@ximihoo1 / 熹米Cycler💦
成功保存：18 条
时间范围：2026-04-22T12:05:35+00:00 → 2026-04-25T08:35:29+00:00
保存路径：/home/hpp/vault/traders/ximihoo1/raw/
原始 JSON：tweets_raw.json
文本版：tweets_text.md
SHA256：d6c7300089b3bf63af728ec108ffa8bdd2101ee3dcbc4e0cdead0813b965a696
```

## 2. 为什么没有拿到 1000 条

当前环境可用工具受限：

1. `x-cli` 可执行存在，但本机 X/Twitter OAuth 配置只有 consumer key/secret，缺少可用 access token/secret，不能正常调用用户时间线接口。
2. `snscrape` 已安装最新版源码版，但 X GraphQL 接口变更/封锁导致 twitter-user 抓取失败。
3. Nitter 普通页面为空或被实例限制。
4. Nitter RSS fallback 成功，但只能返回最近 18 条。
5. Jina Reader 能读取 X 公开 Profile 页面，但也只是近端页面，不支持稳定翻页到 1000 条。

因此本次蒸馏标记为：

```text
LOW_SAMPLE_INITIAL_DISTILLATION
```

不应当替代完整 1000 条画像。

## 3. 原始数据字段

`tweets_raw.json` 每条包含：

```json
{
  "id": "推文ID",
  "url": "https://x.com/ximihoo1/status/...",
  "nitter_url": "Nitter RSS 原链接",
  "created_at": "ISO 时间",
  "raw_pubDate": "RSS pubDate",
  "text": "推文文本",
  "source": "nitter_rss",
  "author": {
    "username": "ximihoo1",
    "display_name": "熹米Cycler💦"
  },
  "public_metrics": {},
  "note": "抓取限制说明"
}
```

没有互动指标：

```text
like_count
retweet_count
reply_count
quote_count
view_count
```

所以本次不能做“高互动样本”排序，只能做主题频率和人工证据索引。

## 4. 主题统计

基于 18 条文本粗分类：

```text
cycle_rotation: 6
macro_assets: 8
risk: 3
technical: 4
community: 1
poll: 1
```

解释：

- `cycle_rotation`：周期、轮动、资产轮动、顺势。
- `macro_assets`：BTC、美股、黄金、白银、微策略等跨资产。
- `risk`：危险、不要追高、骗子、防风险。
- `technical`：KDJ、MACD、日级别、0轴、背离。
- `community`：社群/防诈骗。
- `poll`：投票/偏好调查。

## 5. 关键证据摘录

### 5.1 资产轮动

ID：2047957656481214706  
时间：2026-04-25T08:35:29+00:00  
链接：https://x.com/ximihoo1/status/2047957656481214706

> 当前资产轮动阶段，你最看好哪个？

用途：证明其关注“资产轮动阶段”而不是单一币种短线。

---

### 5.2 防诈骗/账号边界

ID：2047947359339040963  
时间：2026-04-25T07:54:34+00:00  
链接：https://x.com/ximihoo1/status/2047947359339040963

> 你们别信骗子，我不会私信你🫵 这几天评论区仿冒我的人，拉黑都拉不完🤦‍♀️

用途：社群安全边界；不要把私信/仿冒号作为信号来源。

---

### 5.3 黄金白银风险：0轴下 MACD 死叉

ID：2047875523221852510  
时间：2026-04-25T03:09:07+00:00  
链接：https://x.com/ximihoo1/status/2047875523221852510

> 黄金和白银，危。Gold and Silver are dangerous。日级别MACD，如果在这个位置（0轴之下死叉），那么将引来深深的急跌！但我希望不要这样。非投资建议！

用途：提炼 `MACD_BELOW_ZERO_DEATH_CROSS` 深跌风险规则。

---

### 5.4 BTC 长期统治力叙事

ID：2047938858948657164  
时间：2026-04-25T07:20:47+00:00  
链接：https://x.com/ximihoo1/status/2047938858948657164

> 2025年总交易量 Mastercard：9.7万亿美元 Visa：16万亿美元 Bitcoin：25万亿美元。总结：2025年Bitcoin在支付/交易领域的交易量已经远超 Visa、Mastercard，显示强势“统治力”+增长势头，可这才刚刚开始。

用途：说明其 BTC 长期叙事偏强。

---

### 5.5 KDJ / MACD 顶背离

ID：2047883945627545732  
时间：2026-04-25T03:42:35+00:00  
链接：https://x.com/ximihoo1/status/2047883945627545732

> KDJ顶背离和MACD顶背离相似，都是：指标向下，而价格却创下新高。

用途：提炼 `DIVERGENCE_RISK` 规则。

---

### 5.6 BTC 完成目标后不要追高

ID：2047855083803844844  
时间：2026-04-25T01:47:53+00:00  
链接：https://x.com/ximihoo1/status/2047855083803844844

> 比特币已完成4月目标：$75K-80K。目前盘面风险较高，不要盲目追高了。

用途：提炼 `NO_CHASE_ZONE` 规则。

---

### 5.7 2日级别 MACD 预测

ID：2047650575366738239  
时间：2026-04-24T12:15:15+00:00  
链接：https://x.com/ximihoo1/status/2047650575366738239

> 我在3月曾预测：比特币2日级别MACD在“箭头”位置不会死叉，如今也应验了！

用途：说明其偏好多日级别 MACD，而非纯短线。

---

### 5.8 3日级别 KDJ 结构

ID：2047530580015984685  
时间：2026-04-24T04:18:26+00:00  
链接：https://x.com/ximihoo1/status/2047530580015984685

> 比特币K线走势，如我引文中预测一样：透过3日级别KDJ看，（结构2）明显要比（结构1）走的时间要更长！而且要更强劲！

用途：说明其用 3D KDJ 做结构延伸判断。

---

### 5.9 微策略 vs 比特币

ID：2047280820344537532  
时间：2026-04-23T11:45:58+00:00  
链接：https://x.com/ximihoo1/status/2047280820344537532

> 微策略 vs 比特币，你们观察出来什么没？

用途：证明跨资产/代理资产相对强弱观察。

---

### 5.10 清算地图多周期冲突

ID：2047256789872472122  
时间：2026-04-23T10:10:29+00:00  
链接：https://x.com/ximihoo1/status/2047256789872472122

> 清算地图：左图1日，右图30日。短期爆空，长期爆多。

用途：提炼 `LIQUIDATION_WINDOW_CONFLICT` 规则。

---

### 5.11 猎杀空头

ID：2046957595517432303  
时间：2026-04-22T14:21:36+00:00  
链接：https://x.com/ximihoo1/status/2046957595517432303

> #比特币 猎杀空头时刻，刚刚7.9万了😏

用途：说明她关注短期空头清算推动。

## 6. 数据质量评级

```text
覆盖量：低
时间跨度：低，约 3 天
互动数据：无
适合：初步理论/规则抽取
不适合：完整人格画像、长期胜率评估、自动信号权重提升
```

## 7. 后续补数方案

要真正拿到 1000 条，需要任选其一：

1. 给 `x-cli` 补完整 OAuth access token/access secret；
2. 使用已登录浏览器导出 X 时间线；
3. 使用第三方 tweet archive/API；
4. 等 Nitter/snscrape 可用实例恢复；
5. 手动提供该博主 tweet archive JSON。

补齐后，应覆盖重写：

```text
theory.md
framework.md
sources.md
raw/tweets_raw.json
raw/tweets_text.md
```
