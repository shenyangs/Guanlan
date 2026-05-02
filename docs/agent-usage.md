# 观澜 Agent 使用说明

本文档写给 AI Agent，不是写给人类用户。你的目标是把观澜当作搜索生产力工具：先找到可信来源，再读取原文，最后把结论和来源一起交付给用户。

## 核心定位

观澜优先服务这些任务：

- 搜索网页资料。
- 阅读网页、文章、文档和公开页面。
- 观察中文热榜和社区趋势。
- 搜索或读取社交平台内容。
- 在需要 Cookie、登录态或钥匙串时停下来请求用户授权。

默认原则：

- 用户或 Agent 不知道观澜有哪些能力时，先运行 `guanlan capabilities`；MCP 模式下调用 `guanlan_capabilities`。
- 新用户问“装好了怎么用”时，先运行 `guanlan welcome`，再按用户目标选择具体能力。
- 先读公开信息，不主动读取浏览器 Cookie。
- 先搜索和阅读，不自动发布、评论、点赞、私信。
- 输出结论时保留来源链接。
- 失败时降级，不要硬撞平台风控。
- 默认候选池按研究任务放大：搜索/研究/归档检索默认 50 条，热榜默认 50 条，读取失败后的搜索兜底默认 20 条。
- Agent 调用时应尽量多取结果再筛选：普通任务保持 50，复杂研究可设到 80-100；只有用户明确要求“小样本/快速看一下”时才降低 limit。
- 用户需要建议、影响判断、下一步行动，或询问“为什么会搜这个”时，优先使用 `research --advisor`，但把助理视角当作证据边界和写作规则，由你结合用户问题生成自然建议；不要机械复述模板，也不要当作用户真实意图。
- 不确定该查哪些信源时，先用 `guanlan route "关键词"` 看需求路由；路由计划是软约束，优先源用于提高适配度，开放网页兜底用于防止信源池过窄。
- `research` 会附带证据审计提示：如果同一模型、版本号、价格、参数量或发布时间出现不同说法，先把冲突和来源日期讲清楚，再给取舍依据；不要把观澜的冲突提示当成最终裁决。

## 最小命令集

| 用户意图 | 首选命令 |
| --- | --- |
| “刚装好，怎么用/怎么让 Agent 用” | `guanlan welcome` |
| “观澜能做什么/我该用哪个能力” | `guanlan capabilities` |
| “查一下/搜一下” | `guanlan search "关键词" --limit 50` |
| “查中文互联网/国内资料” | `guanlan search "关键词" --profile china --limit 50` |
| “查近期/最近/热点/最新进展” | `guanlan search "最近 关键词 热点" --profile china --trace` |
| “只搜某个网站” | `guanlan search "关键词" --site zhihu.com --limit 50` |
| “搜微信公众号文章” | `guanlan search "关键词" --site mp.weixin.qq.com --profile china --limit 50`，结果按 best-effort 处理 |
| “查官方/央媒表述” | `guanlan search "关键词" --profile china --scope party_central` |
| “查地方官媒/区域政策” | `guanlan search "关键词" --profile china --scope local_official` |
| “查电商/零售/产业带” | `guanlan search "关键词" --profile china --scope ecommerce` |
| “我该去哪搜/怎么分信源/该跑哪个命令” | `guanlan route "关键词"`，先看 `recommended_commands` |
| “帮我查清楚并给依据” | `guanlan research "关键词" --profile china` |
| “查完后给建议/下一步/可能原因” | `guanlan research "关键词" --profile china --advisor` |
| “查政策/监管/官方通知” | `guanlan research "关键词" --preset policy` |
| “查产品口碑/用户评价” | `guanlan research "关键词" --preset reputation` |
| “查产品口碑并给购买/处理建议” | `guanlan research "关键词" --preset reputation --read-top 0 --advisor` |
| “指定多个平台查口碑” | `guanlan research "关键词" --preset reputation --sites zhihu.com,weibo.com,xiaohongshu.com` |
| “看话题是被夸还是被骂” | `guanlan pulse "关键词" --format context` |
| “查技术选型/开发者反馈” | `guanlan research "关键词" --preset tech` |
| “只要证据包，不读原文” | `guanlan research "关键词" --read-top 0` |
| “读这个链接” | `guanlan read "URL"` |
| “Jina 读不了/读取不完整” | `guanlan read "URL" --backend direct` |
| “页面噪声太多，宁可少给” | `guanlan read "URL" --strict --trace` |
| “只核验标题/发布时间/链接” | `guanlan read "URL" --backend direct --extract metadata` 或 `--extract links` |
| “只读原文，不要兜底搜索” | `guanlan read "URL" --no-fallback-search` |
| “今天有什么热点” | `guanlan hotnews today --limit 50` |
| “技术社区在讨论什么” | `guanlan hotnews v2ex --limit 50` |
| “今天有什么值得读的技术/AI 文章” | `guanlan feeds curated --limit 80` |
| “今天微信/公众号有什么热文” | `guanlan feeds wechat-rss --limit 80` |
| “补一个百度热点 RSS 视角” | `guanlan feeds baidu-rss --limit 80` |
| “找精品 RSS 源目录” | `guanlan feeds curated-sources --keyword AI --limit 80` |
| “这些 RSS 源怎么路由” | `guanlan feeds list` |
| “输出结构化结果” | 给命令加 `--json` |
| “检查哪些渠道可用” | `guanlan doctor --trace` |
| “看渠道稳定性/授权边界/缓存概况” | `guanlan status`，重点看 `就绪` 和 `验证` 列 |
| “解释为什么这条排第一” | `guanlan search "关键词" --trace` |
| “重复查同一题，减少请求” | `guanlan search "关键词" --cache-ttl 3600` |
| “把搜索结果直接塞进 prompt” | `guanlan search "关键词" --format context` |
| “给没有联网能力的本地模型准备输入” | `guanlan prompt "关键词" --profile china --style evidence` |
| “把研究证据包直接喂给本地模型” | `guanlan research "关键词" --format prompt` |
| “生成 MCP 客户端配置” | `guanlan mcp config --client codex` |
| “本地工具不支持 MCP，但能调 HTTP” | `guanlan serve --host 127.0.0.1 --port 8765` |
| “查企业内部只读搜索后端” | `guanlan search "关键词" --backend plugin:my_company_api` |
| “注册企业内部只读搜索 connector” | `guanlan plugin register my_company_api ./backend.py` |
| “批量读一组链接” | `guanlan read batch urls.txt --format context` |
| “追踪网页内容变化” | `guanlan read "URL" --watch` |
| “看来源是否偏斜” | `guanlan search "关键词" --source-chart` |
| “把链接存入本地知识库” | `guanlan archive add "URL"` |
| “把一次研究沉淀成本地知识” | `guanlan archive ingest-search "关键词" --limit 80` |
| “搜索本地知识库” | `guanlan archive search "关键词" --format context` |
| “导出给 RAG 系统” | `guanlan archive export --format jsonl` |
| “看跨源热点趋势” | `guanlan hotnews today --trends` |
| “拿评估集比较搜索质量” | `guanlan eval scenarios --format jsonl` |

CLI 是默认主路径；命令选择不确定时先跑 `guanlan route "用户需求"`，按 `recommended_commands` 起手。若当前 Agent 或平台明确支持 MCP，再使用观澜 MCP 工具面：`guanlan_capabilities`、`guanlan_search`、`guanlan_route`、`guanlan_read`、`guanlan_research`、`guanlan_pulse`、`guanlan_hotnews`、`guanlan_feeds`、`guanlan_archive_search`、`guanlan_status`。这些 MCP 工具保持只读，不提供发布、评论、点赞、私信等写操作。

MCP 客户端安装入口：

```json
{
  "mcpServers": {
    "guanlan": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/shenyangs/Guanlan.git", "guanlan-mcp"]
    }
  }
}
```

## 推荐工作流

### 网页搜索

用户说：

```text
查一下某个主题。
```

执行：

```bash
guanlan search "某个主题" --limit 50
```

中文互联网任务优先使用中文场景画像：

```bash
guanlan search "某个主题" --profile china --limit 50
```

需要更可信的中文信源时使用白名单 scope：

```bash
# 党央媒与中央重点媒体
guanlan search "人工智能 新质生产力" --profile china --scope party_central

# 政府与部委网站
guanlan search "人工智能 政策" --profile china --scope gov

# 核心地方官媒
guanlan search "低空经济 广东" --profile china --scope local_official

# 电商与零售垂类，包含亿邦动力等
guanlan search "跨境电商 AI" --profile china --scope ecommerce
```

公众号文章搜索优先使用站内定向搜索；当公开搜索结果不足且已安装可选依赖时，
观澜会把 `wechat-sogou` 作为备份后端追加到末尾。搜狗微信反爬较强，后端遇到验证码会直接降级，
不会自动打码或读取浏览器 Cookie：

```bash
guanlan search "关键词" --site mp.weixin.qq.com --profile china --limit 50
guanlan search "关键词" --backend wechat-sogou --limit 50
```

查看全部白名单：

```bash
guanlan search --list-scopes
```

观澜会对搜索结果做质量层处理：

- 多后端聚合，不把结论押在单一搜索引擎上。
- URL 去重，合并来自多个后端的重复结果。
- 标注 `source_type`、`matched_scope`、`trust_level` 和 `score`。
- 标注 `query_quality`，按政策、电商、财经、技术、口碑等意图调整信源偏好。
- 标注 `topic_key`、`topic_size` 和 `topic_role`，帮助识别同题转载、镜像和重复报道。
- 按 `source_type` 交错展示同题代表结果，优先形成多侧面证据组合。
- 当用户指定 `--scope` 时，优先按该研究语境解释重叠域名。
- 当用户使用 `近期`、`最近`、`热点`、`最新`、`快讯` 等时效词时，自动收束时间窗口，优先近期结果，降权明显陈旧内容。

如果 Markdown 中出现 `topic=representative/2`，表示这条是同题簇代表结果，该 topic 共有 2 条相关结果。回答用户时优先选不同 topic 的代表结果做依据，不要把同题转载当成多个独立证据。

如果前几条结果来自不同 `source_type`，这是观澜为了交叉验证刻意做的排序。回答时优先混合使用官方、垂类、社区、财经等不同类型信源；不要只拿同一种信源类型的高分结果。

如果用户需要直观看到这轮信息是否偏斜，追加来源分布图：

```bash
guanlan search "某主题" --profile china --source-chart
guanlan research "某主题" --preset industry --source-chart
```

`--source-chart` 会输出 ASCII 来源类型和域名分布。它不代表结论真假，只用于提醒 Agent：这轮证据主要来自哪里，是否需要补官方、垂类、社交或开发者社区视角。

### 话题回响

用户说：

```text
看看这个产品现在是被骂还是被夸。
```

优先使用安全版回响分析：

```bash
guanlan pulse "产品名 用户评价" --format context
```

指定公开平台样本：

```bash
guanlan pulse "产品名 用户评价" --sites zhihu.com,weibo.com,xiaohongshu.com --format context
```

需要少量原文增强时，才显式开启摘读：

```bash
guanlan pulse "产品名 用户评价" --read-top 2 --format context
```

`pulse` 只输出“基于当前公开样本的讨论倾向”，不是全网舆情结论。回答用户时必须保留置信度、样本来源、关键词信号和边界提醒。不要把 `偏正向` / `偏负向` 写成绝对事实。

如果用户希望你直接形成回答依据，而不是只列链接，优先使用研究证据包：

```bash
guanlan route "某主题"
guanlan research "某主题" --profile china --limit 50 --read-top 2
```

`research` 会自动整合搜索质量层、同题聚类、信源多样性和原文摘读。输出仍然不是最终答案，Agent 需要基于证据包再组织结论、依据和不确定性。

`route` 会输出主要意图、证据角色、优先 scope、推荐站点、兜底 scope、查询改写和边界提醒。不要把 route 当成硬过滤：除非用户显式指定 `--scope` 或 `--site`，否则 `research` 会同时保留开放网页兜底，避免只在白名单里打转。

如果用户需要你在证据包之外给一个谨慎的“助理视角”，加 `--advisor`：

```bash
guanlan research "某主题" --profile china --limit 50 --read-top 2 --advisor
guanlan research "某产品 用户评价" --preset reputation --read-top 0 --advisor
```

助理视角会返回证据约束、可展开角度和写作规则。Agent 应据此生成自己的建议，而不是机械复述固定小标题；建议必须保留“可能/建议/仅供参考”的边界，不能写成用户真实目的，也不能替代医疗、法律、金融等高风险专业判断。

Preset 会自动选择一个或多个 scope，并可包含平台定向站点。用户显式传入 `--scope` 时，只查用户指定 scope；显式传入 `--site` 或 `--sites` 时，优先做站内/平台定向研究。

常用 preset：

| Preset | 默认信源策略 | 适合任务 |
| --- | --- |
| `policy` | `gov` + `party_central` | 政策、监管、部委通知、法规原文和权威解读。 |
| `official` | `party_central` + `gov` | 党央媒、中央重点媒体、宏观表述。 |
| `industry` | `business` + `ecommerce` + `finance`；36氪、虎嗅、一财 | 产业趋势、商业模式、公司动态。 |
| `ecommerce` | `ecommerce` + `business`；亿邦动力、网经社、雨果跨境 | 电商、零售、跨境、品牌和产业带。 |
| `reputation` | `social_web` + `tech_dev` + `business`；知乎、微博、小红书、B站 | 产品口碑、用户评价、社交平台公开讨论。 |
| `tech` | `tech_dev` + `social_web`；V2EX、掘金、SegmentFault、GitHub | 技术选型、开发者社区、工程实践。 |
| `finance` | `finance` + `business`；财联社、东方财富、雪球 | 财经、资本市场、公司和宏观金融。 |
| `local` | `local_official` + `gov` + `party_central` | 地方政策、区域产业、城市治理。 |

然后选择 2-4 个高质量结果继续读原文：

```bash
guanlan read "https://example.com/article" --max-chars 12000
```

如果默认读取失败或正文明显不完整，改用直连后端：

```bash
guanlan read "https://example.com/article" --backend direct --max-chars 12000
```

默认 `guanlan read` 在 `auto` 模式下会做三段降级：

```text
Jina Reader -> Direct HTML -> Search-as-context
```

最后一段会返回“观澜阅读兜底”上下文包，包括原始 URL、失败原因和同域公开搜索线索。它只用于继续核验，不能当作原文全文。用户如果明确要求只读原文，用：

```bash
guanlan read "https://example.com/article" --no-fallback-search
```

回答用户时给出：

- 简短结论。
- 关键证据。
- 来源链接。
- 不确定性或需要进一步验证的点。

### 中文热点

用户说：

```text
今天国内 AI 圈有什么热点？
```

优先：

```bash
guanlan hotnews today --limit 50
guanlan hotnews weibo --limit 50
guanlan hotnews bilibili --limit 50
guanlan hotnews ithome --limit 50
guanlan hotnews v2ex --limit 50
```

`today` 会混合百度热搜、微博热搜、B站热门视频、IT之家 RSS 和 V2EX 热门，适合作为“今天发生了什么”的默认入口。单个公开源失败时，观澜会保留其它源的结果。

如果需要更多来源，可以使用 NewsNow 可选增强后端，例如：

```bash
guanlan hotnews newsnow:36kr-quick --limit 50
guanlan hotnews newsnow:ithome --limit 50
guanlan hotnews newsnow:bilibili-hot-search --limit 50
```

NewsNow 源覆盖面更广，但稳定性取决于 `BASE_URL`、Cloudflare 和上游抓取状态；公共站不稳时可先配置自有或可用 endpoint：

```bash
guanlan configure newsnow-base-url https://your-newsnow.example
```

`zhihu` 热榜是 experimental 源，不要当作稳定热榜入口。需要知乎视角时可尝试：

```bash
guanlan hotnews zhihu --limit 50
guanlan search "热点关键词" --site zhihu.com --profile china --limit 50
```

如果需要更深入，再对热点关键词做搜索：

```bash
guanlan search "热点关键词" --limit 50
```

### 站内搜索

用户说：

```text
看看知乎上有没有讨论这个产品。
```

优先用站内搜索：

```bash
guanlan search "产品名 评价" --site zhihu.com --limit 50
```

如果用户明确要求微博、小红书、Twitter 等平台，再先检查可用性：

```bash
guanlan doctor --profile china --trace
```

如果配置里可能粘贴过 Cookie、Token、API key 或代理地址，先做本地配置扫描：

```bash
guanlan doctor --check-config
```

需要解释搜索排序时，使用 `--trace`。它会展示评分因子、query_quality、query_strategy、topic 信息、缓存状态、后端顺序和时效性判断，适合排查“为什么 A 在 B 前面”。

```bash
guanlan search "最新 AI 政策" --profile china --trace
```

严肃研究不要只依赖一个宽泛 query。`research` 会按路由计划把问题拆成官方原文、权威报道、用户样本、行业材料、近期进展等 query variant，再按 scope/site/open web 合并去重；Agent 回答时应保留这些证据角色差异。

同一个 query 需要反复查时，可以加 TTL 缓存，默认缓存落在 `~/.guanlan/cache/`：

```bash
guanlan search "AI 政策" --cache-ttl 3600
```

多 URL 读取时，优先用批量模式；社交平台、登录态平台仍然遵循显式授权和低频原则：

```bash
guanlan read batch urls.txt --format context
```

### 本地知识库

用户说：

```text
把这篇文章存起来，以后查资料时能用。
```

执行：

```bash
guanlan archive add "https://example.com/article"
```

已有 URL 列表时：

```bash
guanlan archive add batch urls.txt
```

查询本地沉淀材料：

```bash
guanlan archive search "人工智能 政策" --format context
```

导出给 RAG、向量库或其他本地系统：

```bash
guanlan archive export --format jsonl
```

Archive 默认保存在 `~/.guanlan/archive.db`。它只保存本机归档内容，不自动上传。批量归档仍遵守高风险社交域名保护；遇到微博、小红书、抖音、Twitter/X、LinkedIn 等平台时，不要绕过授权边界批量读取。

自定义 backend 只在显式调用时启用。配置示例：

```yaml
backends:
  my_company_api:
    type: plugin
    path: ./backends/my_api.py
```

插件脚本接收 `query limit` 两个参数，输出 JSON 数组，字段至少包含 `title` 和 `url`。

### 社交平台

社交平台能力分三类：

| 类型 | 处理方式 |
| --- | --- |
| 公开可读 | 直接搜索或读取公开页面。 |
| 需要外部 CLI/MCP | 先 `doctor --trace` 判断是否可用。 |
| 需要 Cookie/登录态 | 必须向用户说明风险并请求授权。 |

不要自动执行：

- `guanlan configure --from-browser ...`
- 登录命令。
- 发帖、评论、点赞、关注、私信。

除非用户明确要求，并且你已经说明风险。

## 降级策略

| 失败场景 | 降级路径 |
| --- | --- |
| `guanlan search` 失败 | 尝试缩短关键词，或改用具体站点搜索。 |
| 中文搜索质量不够 | 加 `--profile china`，或用 `--scope` 选择官方/地方/垂类信源池。 |
| `guanlan read` 失败 | 默认会先尝试 `--backend direct`，仍失败则返回搜索兜底上下文。 |
| Jina Reader 读不到正文 | 这是大陆中文站点常见情况，改用 `--backend direct`，或换同题公开信源。 |
| 热榜源失败 | 先换 `today`、`baidu`、`weibo`、`bilibili`、`ithome` 或 `v2ex`，不要强行读取登录平台。 |
| 社交平台不可用 | 用 `guanlan search "关键词 site:平台域名"` 或普通站内搜索替代。 |
| 命令提示需要认证 | 停下来问用户是否授权，不要自动读取 Cookie。 |

## 输出格式建议

面向用户的回答应尽量这样组织：

```text
结论：
...

依据：
1. 来源标题 — URL
2. 来源标题 — URL

需要注意：
...
```

如果来源互相矛盾，要明确说明“不同来源说法不一致”，不要把搜索结果硬揉成一个确定结论。

## 安全边界

观澜默认不会触碰钥匙串。你也不要主动触发敏感动作。

安全命令：

```bash
guanlan doctor
guanlan doctor --trace
guanlan search "关键词"
guanlan read "URL"
guanlan read "URL" --backend direct
guanlan read "URL" --no-fallback-search
guanlan hotnews today
```

敏感命令：

```bash
guanlan doctor --auth-check
guanlan configure --from-browser chrome
```

只有在用户明确同意后，才运行敏感命令。
