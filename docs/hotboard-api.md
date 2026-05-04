# 热点目录接入

观澜把热点目录拆成“本地目录”和“显式详情”两层，避免把热点路由稳定性绑死在实时网络上。

## 本地全量榜单目录

- 拉取时间：2026-05-04T11:07:08Z
- 拉取页数：109 页，停止页：110
- 原始记录：10,858 条
- 去重后节点：10,843 个
- 随包数据：`guanlan/data/hotboard_nodes.json`
- 可审阅表：`docs/data/hotboard_nodes.csv`
- 摘要文件：`docs/data/hotboard_nodes_summary.json`

本地目录用于路由、榜单发现和 Agent 选源，不需要 API key，也不会产生额度消耗。

## 类目分布

| cid | 类目 | 节点数 |
| --- | --- | ---: |
| 1 | 综合 | 767 |
| 2 | 科技 | 609 |
| 3 | 娱乐 | 1185 |
| 4 | 社区 | 422 |
| 5 | 购物 | 141 |
| 6 | 财经 | 396 |
| 7 | 开发 | 407 |
| 8 | 高校 | 440 |
| 9 | 机构 | 1275 |
| 10 | 博客 | 4608 |
| 12 | 电子报 | 553 |
| 13 | 设计 | 40 |

## 命令层语义

```bash
# 本地目录检索：不需要 key，不消耗额度
guanlan hotnews hotboard:catalog:finance --limit 30

# 快照列表：需要 key 和有效余额，返回 ssid/timestamp，不取详情，不消耗 u
guanlan hotnews hotboard:snapshots:weibo --limit 20

# 单榜详情：显式 opt-in，约 1u/次，观澜会走缓存；失败时降级到公开 HTML 入口
guanlan hotnews hotboard:weibo --limit 80
```

## 路由层接入原则

1. 路由只依赖本地全量目录，不实时调用详情接口。
2. Agent 看到热点目录推荐时，应先把它理解为“去哪看”的信源发现，而不是事实证据。
3. 单榜详情属于显式读取动作，输出会携带 `paid_api`、`cost_u`、`provider_status`、`cache/stale_cache` 等元数据。
4. 外部聚合信号适合补充“水势”和“平台入口”，不应替代官方原文、平台原帖或可审计正文。
