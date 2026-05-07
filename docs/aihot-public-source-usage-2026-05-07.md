# AIHOT 公开信源面接入判断（2026-05-07）

这份判断基于 `/Users/sam/Downloads/codex/test/docs/aihot_public_source_surface_2026-05-07.md`，只使用 AIHOT 公开页面暴露出来的信源身份，不复刻其内部评分、阈值、聚类或私有策略。

## 总体结论

AIHOT 公开面最值得借的是三类东西：

1. 官方/一手 AI 公司与研究入口：适合补强 `company_primary`、`developer`、`science`。
2. 高质量技术/研究 RSS：适合继续通过 `guanlan feeds curated --category ai --limit 80` 做发现，必要时再沉淀进既有信源池。
3. X 账号、公众号和媒体/KOL：只适合作为样本/线索，不应进入事实主证据层。

已先落一版保守接入：不新增用户需要感知的独立入口，而是把公开表里稳定的一手、研究、开发者和高质量评论域名融入既有 `tech_research`、`developer_research` 与对应 scope。

## 已融入的既有信源池

| 类型 | 进入位置 | 示例 | 使用方式 |
| --- | --- | --- | --- |
| AI 公司一手 | `tech_research` 里的 `company_primary` 增强 | OpenAI、Anthropic、Google DeepMind、Mistral、xAI、Cursor、OpenRouter、Runway、Midjourney、Apple ML Research | 继续走 `company_primary` scope；路由会自动推荐更强的一手站点 |
| 开发者/模型生态 | `developer_research` 里的 `developer` 增强 | Hugging Face、GitHub Blog、Cloudflare Blog、NVIDIA Developer | 继续走 `developer` / `tech` 路由；不需要新命令 |
| 研究/论文入口 | `tech_research` 里的 `science` 增强 | BAIR、CMU ML Blog、LMSYS、EleutherAI、arXiv | 继续走 `science` scope / preset |
| 产业/技术评论样本 | `tech_research` / `developer_research` 的垂类或样本增强 | SemiAnalysis、Simon Willison、Ethan Mollick、Interconnects、Karpathy、Sam Altman Blog | 只作观点或技术解读样本，必须回到官方/论文/代码交叉核验 |

## 暂不进主路由

| 信源面 | 原因 | 推荐使用 |
| --- | --- | --- |
| X 账号 | 登录/API/地区可用性不稳定，且转发和短帖容易重复/误导 | 通过 `twitter search` 或后续可选 channel 做样本，不抢官方源 |
| 公众号账号列表 | 公开全文读取经常受微信反爬、登录墙影响；账号本身不等于文章证据 | `guanlan feeds wechat-rss --limit 80` 做热文线索，定点文章再 `read/diagnose` |
| AIHOT `json_list`/`web_list` 的内部 source id | 公开表只有归一化 id 和样例，不等于可复用 API 契约 | 先沉淀域名和证据角色；只有确认公开、稳定、可审计 endpoint 后再写 fetcher |
| 泛 KOL/媒体二手信源 | 适合发现水势，不适合事实主证据 | 放在 `community_sample`、`social_web` 或 `feeds curated`，回答时标注样本边界 |

## 后续可做

- 给 `feeds` 增加一个显式的 `ai-watch` 聚合源，但前提是逐个核验 RSS/Atom endpoint，并给每个源保留 `feed_status` 与缓存兜底。
- 为 X/公众号做独立候选清单，不进入主证据路由；等用户授权或 channel 后端稳定时再启用。
- 维护一个回测样本：AI 产品发布、模型发布、论文 benchmark、事故复盘各 10 条，用来检查新信源是否提升召回而不是增加噪声。
