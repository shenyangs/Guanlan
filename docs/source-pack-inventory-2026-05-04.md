# 观澜精选信源包清单（v0.5.7）

生成日期：2026-05-04

这份清单列出已经沉淀进观澜主路由、scope 和路由推荐逻辑的精选信源。它们不是热榜结果，也不是全量白名单，而是经过“精品渠道 + 稳健性”筛选后的中文互联网信源资产。

## 分层原则

- `core`：进入主路由和优先 scope，用于官方、一手、权威、强解释力证据。
- `vertical`：进入垂类增强，用于行业、技术、财经、游戏、安全等专业补充。
- `sample`：只做发现、舆情和样本，不抢主证据位置。
- 热点目录只作为入口和快照线索，不替代原始页面、官方原文或可审计正文。
- 博客专栏、电子报、购物榜单没有进入本批 source pack；政务只选择中央/省级以上及党央媒解释源；娱乐只保留相对优质且稳健的渠道。

## 总览

| 指标 | 数量 |
| --- | ---: |
| Source Pack | 6 |
| 信源总数 | 75 |
| 主路由 / 高置信 | 59 |
| 垂类增强 / 中高置信 | 11 |
| 发现补充 / 样本 | 5 |

## 政策与党央媒信源包 `policy_research`

| 信源 | 域名 | 分层 | 进入 scope | 证据角色 | 权威 | 样本 | 时效 |
| --- | --- | --- | --- | --- | ---: | ---: | ---: |
| 中国政府网 | `gov.cn` | 主路由 / 高置信 | `gov` | `official_primary` | 0.97 | 0.05 | 0.62 |
| 人民网 | `people.com.cn` | 主路由 / 高置信 | `party_central` | `authoritative_report` | 0.88 | 0.18 | 0.66 |
| 新华网 | `xinhuanet.com` | 主路由 / 高置信 | `party_central` | `authoritative_report` | 0.88 | 0.16 | 0.66 |
| 央视新闻 | `news.cctv.com` | 主路由 / 高置信 | `party_central` | `authoritative_report` | 0.86 | 0.16 | 0.68 |
| 求是网 | `qstheory.cn` | 主路由 / 高置信 | `party_central` | `official_narrative` | 0.90 | 0.08 | 0.48 |
| 半月谈 | `banyuetan.org` | 主路由 / 高置信 | `party_central` | `policy_interpretation` | 0.82 | 0.20 | 0.62 |
| 光明网 | `gmw.cn` | 主路由 / 高置信 | `party_central` | `authoritative_report` | 0.82 | 0.18 | 0.60 |
| 经济日报 | `ce.cn` | 主路由 / 高置信 | `party_central` | `macro_policy_report` | 0.82 | 0.18 | 0.62 |
| 央广网 | `cnr.cn` | 主路由 / 高置信 | `party_central` | `authoritative_report` | 0.80 | 0.18 | 0.64 |
| 中国新闻网 | `chinanews.com.cn` | 主路由 / 高置信 | `party_central` | `news_signal` | 0.76 | 0.22 | 0.72 |

## 科技与产业信源包 `tech_research`

| 信源 | 域名 | 分层 | 进入 scope | 证据角色 | 权威 | 样本 | 时效 |
| --- | --- | --- | --- | --- | ---: | ---: | ---: |
| IT之家 | `ithome.com` | 主路由 / 高置信 | `tech_dev` | `tech_news_signal` | 0.58 | 0.48 | 0.90 |
| 少数派 | `sspai.com` | 主路由 / 高置信 | `tech_dev` | `tech_reading_signal` | 0.56 | 0.55 | 0.72 |
| 36氪 | `36kr.com` | 主路由 / 高置信 | `business` | `industry_report` | 0.54 | 0.38 | 0.80 |
| 虎嗅 | `huxiu.com` | 主路由 / 高置信 | `business` | `industry_analysis` | 0.52 | 0.38 | 0.76 |
| 钛媒体 | `tmtpost.com` | 主路由 / 高置信 | `business` | `industry_analysis` | 0.52 | 0.36 | 0.76 |
| 亿邦动力 | `ebrun.com` | 主路由 / 高置信 | `ecommerce` | `ecommerce_industry_report` | 0.56 | 0.36 | 0.78 |
| 极客公园 | `geekpark.net` | 主路由 / 高置信 | `tech_dev` | `product_context` | 0.50 | 0.42 | 0.72 |
| 爱范儿 | `ifanr.com` | 主路由 / 高置信 | `tech_dev` | `consumer_tech_signal` | 0.48 | 0.42 | 0.76 |
| 雷峰网 | `leiphone.com` | 主路由 / 高置信 | `tech_dev` | `ai_industry_report` | 0.52 | 0.36 | 0.72 |
| 机器之心 | `jiqizhixin.com` | 主路由 / 高置信 | `tech_dev` | `ai_research_news` | 0.56 | 0.34 | 0.74 |
| 量子位 | `qbitai.com` | 主路由 / 高置信 | `tech_dev` | `ai_news_signal` | 0.54 | 0.34 | 0.78 |
| 新智元 | `aiera.com.cn` | 主路由 / 高置信 | `tech_dev` | `ai_news_signal` | 0.50 | 0.34 | 0.78 |
| 晚点 LatePost | `latepost.com` | 主路由 / 高置信 | `business` | `industry_report` | 0.58 | 0.30 | 0.72 |
| InfoQ 中国 | `infoq.cn` | 主路由 / 高置信 | `tech_dev` | `technical_context` | 0.56 | 0.42 | 0.68 |
| ReadHub | `readhub.cn` | 垂类增强 / 中高置信 | `tech_dev` | `topic_discovery` | 0.42 | 0.50 | 0.82 |
| Solidot | `solidot.org` | 垂类增强 / 中高置信 | `tech_dev` | `developer_news_signal` | 0.48 | 0.42 | 0.72 |

## 财经与市场信源包 `finance_research`

| 信源 | 域名 | 分层 | 进入 scope | 证据角色 | 权威 | 样本 | 时效 |
| --- | --- | --- | --- | --- | ---: | ---: | ---: |
| 财联社 | `cls.cn` | 主路由 / 高置信 | `finance_news` | `market_news` | 0.62 | 0.25 | 0.92 |
| 证券时报 | `stcn.com` | 主路由 / 高置信 | `finance_news` | `market_news` | 0.64 | 0.22 | 0.84 |
| 上海证券报 | `cnstock.com` | 主路由 / 高置信 | `finance_news` | `market_news` | 0.64 | 0.22 | 0.82 |
| 中国证券报 | `cs.com.cn` | 主路由 / 高置信 | `finance_news` | `market_news` | 0.64 | 0.22 | 0.82 |
| 第一财经 | `yicai.com` | 主路由 / 高置信 | `finance_news` | `market_news` | 0.60 | 0.28 | 0.82 |
| 21财经 | `21jingji.com` | 主路由 / 高置信 | `finance_news` | `market_news` | 0.58 | 0.28 | 0.80 |
| 华尔街见闻 | `wallstreetcn.com` | 主路由 / 高置信 | `finance_news` | `market_timeline` | 0.54 | 0.30 | 0.88 |
| 经济观察网 | `eeo.com.cn` | 主路由 / 高置信 | `finance_news` | `industry_report` | 0.56 | 0.28 | 0.72 |
| 每日经济新闻 | `nbd.com.cn` | 主路由 / 高置信 | `finance_news` | `market_news` | 0.56 | 0.28 | 0.78 |
| 财新 | `caixin.com` | 主路由 / 高置信 | `finance_news` | `investigative_report` | 0.62 | 0.24 | 0.72 |
| 东方财富 | `eastmoney.com` | 垂类增强 / 中高置信 | `finance_quote` | `market_quote` | 0.48 | 0.48 | 0.88 |
| 雪球 | `xueqiu.com` | 发现补充 / 样本 | `finance_sentiment` | `sentiment_sample` | 0.28 | 0.88 | 0.90 |
| 股吧 | `guba.eastmoney.com` | 发现补充 / 样本 | `finance_sentiment` | `sentiment_sample` | 0.20 | 0.88 | 0.90 |
| 格隆汇 | `gelonghui.com` | 垂类增强 / 中高置信 | `finance_research` | `market_opinion` | 0.46 | 0.36 | 0.82 |

## 文娱与游戏信源包 `entertainment_research`

| 信源 | 域名 | 分层 | 进入 scope | 证据角色 | 权威 | 样本 | 时效 |
| --- | --- | --- | --- | --- | ---: | ---: | ---: |
| 豆瓣电影 | `movie.douban.com` | 主路由 / 高置信 | `entertainment` | `rating_sample` | 0.36 | 0.88 | 0.68 |
| 豆瓣 | `douban.com` | 主路由 / 高置信 | `entertainment` | `review_sample` | 0.34 | 0.86 | 0.62 |
| 猫眼 | `maoyan.com` | 主路由 / 高置信 | `entertainment` | `box_office` | 0.50 | 0.72 | 0.90 |
| 猫眼专业版 | `piaofang.maoyan.com` | 主路由 / 高置信 | `entertainment` | `box_office` | 0.52 | 0.68 | 0.92 |
| 灯塔专业版 | `lighthouse.alibaba.com` | 主路由 / 高置信 | `entertainment` | `box_office` | 0.50 | 0.64 | 0.90 |
| 1905电影网 | `1905.com` | 主路由 / 高置信 | `entertainment` | `film_news` | 0.54 | 0.30 | 0.74 |
| 时光网 | `mtime.com` | 主路由 / 高置信 | `entertainment` | `film_news` | 0.44 | 0.52 | 0.68 |
| B站 | `bilibili.com` | 发现补充 / 样本 | `entertainment` | `video_attention_signal` | 0.34 | 0.78 | 0.88 |
| 微博 | `weibo.com` | 发现补充 / 样本 | `entertainment` | `public_discussion_signal` | 0.28 | 0.90 | 0.90 |
| TapTap | `taptap.com` | 主路由 / 高置信 | `entertainment` | `game_rating_sample` | 0.36 | 0.82 | 0.74 |
| 游民星空 | `gamersky.com` | 垂类增强 / 中高置信 | `entertainment` | `game_news` | 0.42 | 0.50 | 0.72 |
| 3DM | `3dmgame.com` | 垂类增强 / 中高置信 | `entertainment` | `game_news` | 0.40 | 0.50 | 0.72 |
| 机核 | `gcores.com` | 垂类增强 / 中高置信 | `entertainment` | `game_culture` | 0.46 | 0.58 | 0.70 |
| 游研社 | `yystv.cn` | 垂类增强 / 中高置信 | `entertainment` | `game_culture` | 0.46 | 0.56 | 0.72 |

## 开发者与安全信源包 `developer_research`

| 信源 | 域名 | 分层 | 进入 scope | 证据角色 | 权威 | 样本 | 时效 |
| --- | --- | --- | --- | --- | ---: | ---: | ---: |
| GitHub | `github.com` | 主路由 / 高置信 | `developer` | `code_host` | 0.82 | 0.42 | 0.82 |
| V2EX | `v2ex.com` | 发现补充 / 样本 | `tech_dev` | `developer_discussion` | 0.34 | 0.88 | 0.86 |
| 掘金 | `juejin.cn` | 主路由 / 高置信 | `tech_dev` | `developer_article` | 0.46 | 0.68 | 0.78 |
| SegmentFault | `segmentfault.com` | 主路由 / 高置信 | `tech_dev` | `developer_article` | 0.46 | 0.62 | 0.72 |
| 开源中国 | `oschina.net` | 主路由 / 高置信 | `tech_dev` | `opensource_news` | 0.48 | 0.55 | 0.74 |
| 博客园 | `cnblogs.com` | 主路由 / 高置信 | `tech_dev` | `developer_article` | 0.42 | 0.62 | 0.64 |
| CSDN | `csdn.net` | 垂类增强 / 中高置信 | `tech_dev` | `developer_article` | 0.34 | 0.66 | 0.70 |
| InfoQ | `infoq.cn` | 主路由 / 高置信 | `tech_dev` | `technical_context` | 0.56 | 0.42 | 0.68 |
| HelloGitHub | `hellogithub.com` | 主路由 / 高置信 | `developer` | `opensource_discovery` | 0.54 | 0.58 | 0.70 |
| TesterHome | `testerhome.com` | 垂类增强 / 中高置信 | `tech_dev` | `qa_engineering_discussion` | 0.42 | 0.66 | 0.68 |
| 看雪 | `bbs.kanxue.com` | 垂类增强 / 中高置信 | `cybersecurity` | `security_community_signal` | 0.50 | 0.62 | 0.72 |

## 高校官方信源包 `university_official`

| 信源 | 域名 | 分层 | 进入 scope | 证据角色 | 权威 | 样本 | 时效 |
| --- | --- | --- | --- | --- | ---: | ---: | ---: |
| 清华大学 | `tsinghua.edu.cn` | 主路由 / 高置信 | `university` | `university_official` | 0.90 | 0.12 | 0.58 |
| 北京大学 | `pku.edu.cn` | 主路由 / 高置信 | `university` | `university_official` | 0.90 | 0.12 | 0.58 |
| 复旦大学 | `fudan.edu.cn` | 主路由 / 高置信 | `university` | `university_official` | 0.88 | 0.12 | 0.56 |
| 上海交通大学 | `sjtu.edu.cn` | 主路由 / 高置信 | `university` | `university_official` | 0.88 | 0.12 | 0.56 |
| 浙江大学 | `zju.edu.cn` | 主路由 / 高置信 | `university` | `university_official` | 0.88 | 0.12 | 0.56 |
| 南京大学 | `nju.edu.cn` | 主路由 / 高置信 | `university` | `university_official` | 0.88 | 0.12 | 0.56 |
| 中国科学技术大学 | `ustc.edu.cn` | 主路由 / 高置信 | `university` | `university_official` | 0.88 | 0.12 | 0.56 |
| 哈尔滨工业大学 | `hit.edu.cn` | 主路由 / 高置信 | `university` | `university_official` | 0.86 | 0.12 | 0.54 |
| 武汉大学 | `whu.edu.cn` | 主路由 / 高置信 | `university` | `university_official` | 0.86 | 0.12 | 0.54 |
| 北京航空航天大学 | `buaa.edu.cn` | 主路由 / 高置信 | `university` | `university_official` | 0.86 | 0.12 | 0.54 |

## Scope 注入关系

| Scope | 使用的 Source Pack | 纳入层级 | Scope 过滤 |
| --- | --- | --- | --- |
| `party_central` | policy_research | core | party_central |
| `gov` | policy_research | core | gov |
| `business` | tech_research | core/vertical | business |
| `ecommerce` | tech_research | core | ecommerce |
| `tech_dev` | tech_research, developer_research | core/vertical, core/vertical/sample | tech_dev |
| `developer` | developer_research | core/vertical | developer |
| `cybersecurity` | developer_research | vertical | cybersecurity |
| `finance` | finance_research | core/vertical | finance_news, finance_quote, finance_research |
| `finance_news` | finance_research | core | finance_news |
| `finance_quote` | finance_research | vertical | finance_quote |
| `finance_sentiment` | finance_research | sample | finance_sentiment |
| `finance_research` | finance_research | core/vertical | finance_research |
| `entertainment` | entertainment_research | core/vertical/sample | entertainment |
| `social_web` | entertainment_research, developer_research | sample, sample | entertainment, finance_sentiment, tech_dev |
| `university` | university_official | core | university |

## Intent 路由关系

| Intent | 推荐 Source Pack |
| --- | --- |
| `career` | developer_research |
| `cybersecurity` | developer_research |
| `ecommerce` | tech_research |
| `entertainment` | entertainment_research |
| `finance` | finance_research |
| `finance_disclosure` | finance_research |
| `finance_macro` | finance_research |
| `finance_news` | finance_research |
| `finance_quote` | finance_research |
| `finance_research` | finance_research |
| `finance_sentiment` | finance_research |
| `industry` | tech_research, finance_research |
| `official_position` | policy_research |
| `policy` | policy_research |
| `purchase_advice` | entertainment_research, developer_research |
| `reputation` | entertainment_research, developer_research |
| `tech` | tech_research, developer_research |
| `university_admissions` | university_official |

## 验收保护

- `tests/test_source_packs.py` 校验精选信源不盲塞、scope 注入不漂移、样本源不抢主路由。
- `tests/test_router.py` 校验路由推荐会使用热点目录作为入口，但不会替代 scope/search/research 主证据链。
- `tests/test_hotboard_catalog.py` 校验本地热点目录完整、无需 key 可检索、且不携带敏感配置。
- `tests/test_hotnews.py` 校验 `hotboard:*` 本地目录、快照和显式详情读取行为。
