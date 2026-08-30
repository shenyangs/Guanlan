# Guanlan 信源扩展与同类项目相似性审计（2026-08-28）

## 结论

- 本轮新增的是此前覆盖薄弱、且能显著提高证据质量的入口：标准规范原文、开放学术元数据、供应链漏洞、官方灾害预警，以及中英文开发者社区信号。
- 原生热榜实现只读取公开一方端点：Hacker News RSS、Linux.do RSS、CISA KEV JSON、USGS GeoJSON。没有复制同类项目代码，也没有引入 Cookie、登录态或私有接口。
- 暂未发现足以认定其它项目抄袭 Guanlan 的证据。存在两个值得持续观察的发布后项目，但目前只能称为同类收敛或命名碰撞，不能称为抄袭。

## 本轮落地

| 层级 | 新增内容 | 证据角色/价值 |
| --- | --- | --- |
| 原生 hotnews | `hackernews` | Hacker News 一方 RSS；全球开发者/创业社区讨论样本。 |
| 原生 hotnews | `linuxdo` | Linux.do 一方 RSS；中文开发者、AI 工具和开源社区讨论样本。站点要求 HTTP/2，JSON 受限时自动走 RSS。 |
| 原生 hotnews | `cisa-kev` | CISA 已知在野利用漏洞官方目录；补丁优先级与真实利用风险信号。 |
| 原生 hotnews | `usgs-earthquakes` | USGS 显著地震官方 GeoJSON；震级、位置、海啸标记和复核状态。 |
| 聚合 hotnews | `alerts` | CISA KEV + USGS 的官方安全/灾害快照；单源失败不拖垮另一来源。 |
| 聚合 hotnews | `tech` 扩展 | 加入 Linux.do 与 Hacker News 一方源，保留原有 V2EX、IT之家、新智元和补充聚合源。 |
| 搜索 scope | `standards` | 国家标准全文公开系统、TC260、ISO、IEC、NIST、W3C、IETF、RFC Editor、OASIS、IEEE Standards、ETSI、ITU。 |
| 学术发现 | `academic_discovery` | Crossref、DataCite、OpenAlex、PubMed/NCBI、Europe PMC、Zenodo、DOAJ、Semantic Scholar、CORE、Unpaywall。 |
| 安全 scope | 供应链/发行版公告 | OSV、Debian Security Tracker、Ubuntu Security、Red Hat Security、CERT-EU。 |
| 开发者 scope | 包生态与规范 | crates.io、RubyGems、Packagist、Maven Central、pkg.go.dev、OSV、IETF/RFC/W3C/OASIS。 |
| 评价 scope | 游戏与替代品样本 | Steam、SteamDB、AlternativeTo、AppBrain。 |
| 中文开发者 scope | 社区补充 | Linux.do、NodeSeek、吾爱破解；只作社区/样本信号，不作主事实源。 |

## 同类项目时间线

| 项目 | 公开时间 | 主要形态 | 与 Guanlan 的关系判断 |
| --- | --- | --- | --- |
| [DailyHotApi](https://github.com/imsyy/DailyHotApi) | 2023-03-14 | 多平台热榜 API | 明显早于 Guanlan；用于发现公开平台类型，不构成对 Guanlan 的复制嫌疑。 |
| [NewsNow](https://github.com/ourongxing/newsnow) | 2024-09-23 | 热榜聚合器 | 明显早于 Guanlan；Guanlan 已把它标为可选外部后端。 |
| [TrendRadar](https://github.com/sansan0/TrendRadar) | 2025-04-28 | 热点监控、RSS、报告 | 明显早于 Guanlan；GPL 项目，本轮没有复制其实现。 |
| [SeeSea](https://github.com/nostalgiatan/SeeSea) | 2025-11-22 | 多引擎搜索 | 早于 Guanlan；覆盖搜索引擎较多，但缺少 Guanlan 的证据角色与中国信源路由契约。 |
| [trendsonar](https://github.com/aicezam/trendsonar) | 2025-12-25 | 热点雷达 | 早于 Guanlan；属于常见热点监控形态。 |
| [Agent-Reach](https://github.com/Panniantong/Agent-Reach) | 2026-02-24 | Agent 多平台访问 CLI | 早于 Guanlan；Guanlan 的 `LICENSE` 与 `docs/SOURCE_ATTRIBUTION.md` 已明确列为上游来源。 |
| [Guanlan](https://github.com/shenyangs/Guanlan) | 2026-05-01 首个公开提交 | 中文互联网证据路由、搜索/read/hotnews/feeds/archive | 本项目基线。 |
| [financial-analyst](https://github.com/jesson-hh/financial-analyst) | 仓库 2026-05-24；首个提交 2026-06-17 | 名为“觀瀾”的 A 股多 Agent 工作台 | 发布时间晚且同名，但领域、目录结构、提示词和实现不同；目前是命名碰撞，证据不足以称为抄袭。 |
| [Argo](https://github.com/taxueseek/argo) | 2026-07-18 | Agent 搜索、语义路由、证据管线 | 晚于 Guanlan 且产品形态最接近；精确标识和代码扫描未发现 Guanlan 特有实现，暂列观察，不作抄袭判断。 |

## 相似性检查方法与结果

1. 对公开仓库检索 Guanlan 的高辨识度标识和文案，包括 `OpenGuanlan`、`source_mix_guard`、`agent_plan_v2`、`只读、低扰、明源`、`中文互联网证据路由器`、`quality_gate.reason=partial_salvage`。
2. 对同类仓库与 Guanlan 做规范化长行精确重合扫描，过滤空行、短行和常见语法。
3. 核对仓库创建时间与首个 Git 提交时间，区分上游、同代项目和 Guanlan 发布后项目。
4. 对 Agent-Reach 的大量重合单独核对 attribution；其重合来自已声明的上游继承，不属于他人复制 Guanlan。

结果：

- 没有项目命中 `OpenGuanlan`、`source_mix_guard`、核心中文定位文案等高辨识度标识。
- Argo、financial-analyst、nanobot-webui、trendsonar 等与 Guanlan 的精确重合仅为 JSON 输出、HTTP headers、MCP/SQLite 等通用样板。
- `evidence_bundle_v1` 在多个互不相关项目中出现，属于通用版本化 schema 命名，单独不能作为复制证据。
- 因此当前结论是“没有已核实的抄袭证据”。若未来发现连续的独特字段组合、同序错误、专有文案或大段实现重合，再升级为逐提交取证。

## 有意未纳入

- 图片搜索、购物榜、娱乐噪声榜：与 Guanlan 当前“证据路由”主线不够匹配，已有可选聚合目录可作发现层。
- 需要登录、Cookie、浏览器存储或私有 token 的社区端点：违反默认只读、低扰边界。
- 航班、列车等实时垂直数据：价值高，但需要单独的实体、时区、实时性和官方接口契约，不应混进本轮通用 source scope。
- 仅在同类项目配置中出现、但没有可验证一方公开入口的来源：先保留候选，不把第三方聚合结果包装成原生事实源。

## 复核命令

```bash
guanlan hotnews hackernews --limit 5 --json
guanlan hotnews linuxdo --limit 5 --json
guanlan hotnews cisa-kev --limit 5 --json
guanlan hotnews usgs-earthquakes --limit 5 --json
guanlan hotnews alerts --limit 5 --json
guanlan search "RFC 9110 HTTP Semantics" --profile hybrid --scope standards --limit 80 --trace
guanlan search "DataCite DOI Zenodo OpenAlex dataset citation metadata" --profile hybrid --scope academic --limit 80 --trace
guanlan sources audit
```
