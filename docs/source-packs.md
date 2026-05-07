# 精选信源包 / Source Packs

观澜把公开信源面、真实链接验证和人工判断沉淀为“精选信源包”，用于增强路由和 scope 搜索。它不是热榜结果，也不是全量白名单，而是一组可长期维护的信源资产，优先服务中文互联网研究，同时覆盖少量高价值全球 AI/开发者入口。

## 设计原则

1. 去粗取精：只收录精品、稳定、解释力强的渠道。
2. 分层使用：`core` 进主路由，`vertical` 进垂类增强，`sample` 只做样本/讨论。
3. 信源优先于热榜：热点目录只作为入口和快照线索，不替代原始页面和信源判断。
4. 谨慎扩展：博客专栏、电子报、购物榜单暂不进入本批 source pack；政务只挑中央/省级以上及党央媒解释源。
5. 每个 pack 都有测试，避免路由增强反而污染主路径。

## 当前信源包

完整清单见：[观澜精选信源包清单](source-pack-inventory-2026-05-04.md)。

| Pack | 用途 | 示例信源 |
| --- | --- | --- |
| `policy_research` | 政策、官方口径、党央媒解释 | 中国政府网、人民网、新华网、央视新闻、求是网、半月谈 |
| `tech_research` | 科技、AI、产业与产品观察 | IT之家、少数派、36氪、虎嗅、机器之心、量子位、OpenAI、Anthropic、Google DeepMind、Mistral、arXiv、BAIR |
| `wps_office_research` | 金山办公/WPS、办公 AI、PPT、文档协作、SaaS、信创、安全和竞品选题 | WPS、WPS 365、金山文档、WPS 官方社区、安全中心、Microsoft 365、Google Workspace、Canva、Gamma、飞书、少数派、36氪、V2EX |
| `finance_research` | 财经新闻、行情、研报与投资者情绪 | 财联社、证券时报、上海证券报、第一财经、21财经、华尔街见闻、东方财富、雪球 |
| `entertainment_research` | 影视、游戏、评分、票房和平台热度 | 豆瓣电影、猫眼、灯塔、1905、B站、微博、TapTap、游民星空、机核、游研社 |
| `developer_research` | 开发者、开源、工程实践与安全社区 | GitHub、Hugging Face、GitHub Blog、Cloudflare Blog、NVIDIA Developer、V2EX、掘金、HelloGitHub、TesterHome、看雪、Simon Willison |
| `university_official` | 高校官网、招生和院系信息 | 清华、北大、复旦、上交、浙大、南大、中科大、哈工大、武大、北航 |

## 代码入口

- 数据定义：`guanlan/source_packs.py`
- scope 增强：`guanlan/search_sources.py`
- 路由站点推荐：`guanlan/router.py`
- 本地热点目录：`guanlan/data/hotboard_nodes.json`
- 热点目录入口：`guanlan hotnews hotboard:*`

## 与 hotnews 的关系

`source_packs` 回答“应该去哪类信源找”。

`hotnews hotboard:*` 回答“某个榜单现在/最近有哪些入口或快照”。

Agent 应先使用 source pack 驱动的 scope/search/research，再按需调用 hotnews 读取具体榜单入口；不能把第三方聚合榜单当作事实主证据。
