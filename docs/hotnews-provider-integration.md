# 热榜外部聚合源整合说明

Guanlan 的热榜主链路仍然是原生公开端点和 RSS；TopHub、UAPI、HotList/VVHan 作为旁支增强源接入。它们能显著补足中文互联网热榜盲点，但都属于第三方聚合层，不能替代原站、权威媒体或正式公告。

## 接入原则

- 不把外部聚合源放进 `today` 默认主链路，避免单个第三方服务波动拖慢或污染默认体验。
- 所有外部条目都会带 `external_backend`、`third_party_aggregation`、`provider_volatility` 风险标签。
- 请求成功后写入本地缓存；上游失败时可返回 `stale_cache`，并在 `metrics.provider_status` 中标明。
- 如果上游返回 HTML、旧快照、空结果或反爬页，不把它解释成“没有热点”，而是保留 provider 诊断。

## 三类来源

| Provider | 用法 | 当前定位 | 风险边界 |
| --- | --- | --- | --- |
| TopHub | `guanlan hotnews tophub:weibo --limit 80`、`guanlan hotnews tophub:catalog:news --limit 80` | 最大的目录型热榜池，适合做 source catalog 和按节点取榜 | HTML 结构可能变化；不要一次性 live 抓全部节点 |
| UAPI | `guanlan hotnews uapis:catalog --limit 80`、`guanlan hotnews uapis:weibo --limit 80` | 40+ 平台目录，适合补文娱、开发者、生活风险等盲点 | API/Next 路由可能变化；解析失败时走缓存或清晰报错 |
| HotList/VVHan | `guanlan hotnews vvhan:all --limit 80`、`guanlan hotnews vvhan:weibo --limit 80` | 直接 JSON 聚合源，接入成本低 | 部分接口可能返回旧快照；Guanlan 会标记 `stale_external_snapshot` |

## 信源盲点补齐

UAPI 目录补上了 `51cto`、`52pojie`、`coolapk`、`csdn`、`douban-group`、`douban-movie`、`hostloc`、`nodeseek`、`ngabbs`、`qq-music`、`netease-music`、`weatheralarm`、`earthquake`、`genshin`、`honkai`、`starrail` 等原来不在稳定热榜主链路里的来源。

TopHub 的 `/c/news` 页面公开显示综合类目录有 490 个节点，因此它更适合做“目录同步 + 单节点按需读取”，而不是每次查询都全量抓取 490 个源。

## Agent 使用建议

- 今天全局水势：先用 `guanlan hotnews today --limit 80 --trends --brief`。
- 想补更多平台：再用 `guanlan hotnews tophub:catalog:news --limit 80` 找候选源。
- 需要某平台热榜：用 `guanlan hotnews tophub:weibo --limit 80` 或 `guanlan hotnews uapis:<platform> --limit 80`。
- 外部聚合源只能做“趋势线索”，重要事实仍应继续 `read` 原文或 `research` 交叉核验。

