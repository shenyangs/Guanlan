# 网页搜索与阅读

通用网页搜索、网页阅读、微信公众号、RSS。

## 通用网页搜索 (Guanlan)

```bash
# 通用网页搜索
guanlan search "关键词" --limit 50

# 中国大陆中文资料优先
guanlan search "关键词" --profile china --limit 50

# 党央媒、政府、地方官媒、垂类媒体等白名单
guanlan search "人工智能 新质生产力" --profile china --scope party_central
guanlan search "跨境电商 AI" --profile china --scope ecommerce
```

**适用场景**: 用户让你“查一下/搜一下/看看国内有没有资料”。观澜会聚合搜索后端、去重、标注信源类型和可信度评分。

搜索结果可能出现 `topic=representative/2` 这样的标识，表示这条是同题簇代表结果，同题相关结果共有 2 条。回答用户时优先选不同 topic 的代表结果，不要把同题转载当成多个独立证据。

观澜也会按 `source_type` 交错展示代表结果。前几条如果混合了官方、垂类、社区、财经等信源，这是为了帮助你做交叉验证，不是简单的分数倒序。

## 研究证据包 (Guanlan)

```bash
# 直接生成 Agent 回答前可用的证据上下文
guanlan research "关键词" --profile china --limit 50 --read-top 2

# 需要建议、下一步、影响判断或“用户可能为什么搜这个”时
guanlan research "关键词" --profile china --limit 50 --read-top 2 --advisor

# 只要搜索证据，不读取原文
guanlan research "关键词" --profile china --read-top 0

# 按场景选择研究模板
guanlan research "关键词" --preset policy
guanlan research "关键词" --preset reputation
guanlan research "关键词" --preset tech

# 指定多个平台做定向证据块
guanlan research "关键词" --preset reputation --sites zhihu.com,weibo.com,xiaohongshu.com

# 查看全部模板
guanlan research --list-presets
```

**适用场景**: 用户要你“查清楚”“给依据”“做一个判断”。`research` 会整合搜索质量层、同题聚类、信源多样性和代表结果摘读。输出不是最终答案，你仍需要基于证据包组织结论、依据和不确定性。

**助理视角规则**: 当用户希望你给建议、下一步、风险提醒、可能意图或“这意味着什么”时，使用 `--advisor`。它输出的是证据边界、可展开角度和写作约束；你需要据此生成自然建议，不要机械复述固定小标题，不要把它写成用户真实目的，也不要把搜索样本写成总体结论。

常用模板：`policy` 政策监管、`official` 官方表述、`industry` 产业研究、`ecommerce` 电商零售、`reputation` 产品口碑、`tech` 技术选型、`finance` 财经研究、`local` 地方研究。

模板会自动选择一个或多个 scope，也可以包含平台定向站点。例如 `policy` 会查 `gov + party_central`，`reputation` 会查 `social_web + tech_dev + business`，并补充知乎、微博、小红书、B站等公开页证据块。如果用户明确指定 `--scope`、`--site` 或 `--sites`，以用户指定范围为准。

## 通用网页阅读 (Guanlan)

```bash
# 默认：先 Jina Reader，失败后直连原网页
guanlan read "https://example.com/article"

# Jina 不稳或正文不完整时，直接读原网页
guanlan read "https://example.com/article" --backend direct

# 严格只读原 URL，不要返回搜索兜底
guanlan read "https://example.com/article" --no-fallback-search

# 批量读取普通网页 URL 列表，输出适合 prompt 的上下文
guanlan read batch urls.txt --format context

# 保存或比较本地快照，输出内容变化 diff
guanlan read "https://example.com/article" --watch
```

**适用场景**: 已经有 URL，需要给 Agent 上下文。中国大陆站点常见 JS 渲染、登录墙、验证码、地域访问差异和反爬策略；Jina Reader 只能作为第一读取入口，不要当成唯一依赖。默认 `auto` 会按 `Jina Reader -> Direct HTML -> Search-as-context` 降级，最后一段只提供公开搜索线索，不等同于原文全文。

批量读取只适合普通网页、公开文章、文档和 RSS 链接。对小红书、微博、Twitter/X、LinkedIn、抖音等高风险或登录态平台，批量模式会拒绝读取；需要时应让用户明确授权，再使用对应平台工具或单条读取路径。

## 本地知识库 (Guanlan Archive)

```bash
# 读取 URL 并保存为本地 Markdown 归档
guanlan archive add "https://example.com/article"

# 批量归档普通网页
guanlan archive add batch urls.txt

# 检索本地归档，输出适合 prompt 的上下文
guanlan archive search "关键词" --format context

# 查看本地知识库状态
guanlan archive stats

# 导出给 RAG、向量库或其他本地系统
guanlan archive export --format jsonl
```

**适用场景**: 用户希望把查过、读过、核验过的中文材料沉淀下来，后续快速复用。Archive 默认保存在 `~/.guanlan/archive.db`，使用 SQLite + FTS/LIKE 检索，不自动上传。批量归档仍遵守高风险社交域名保护。

## 直接 Jina Reader

```bash
# 读取任意网页内容
curl -s "https://r.jina.ai/URL"

# 示例
curl -s "https://r.jina.ai/https://example.com/article"
```

**适用场景**: 需要快速验证 Jina 原始输出，或在没有观澜 CLI 的环境中临时读取。

## Web Reader (MCP，可选)

```bash
# 读取网页内容 (Markdown 格式)
mcporter call 'web-reader.webReader(url: "https://example.com")'

# 保留图片
mcporter call 'web-reader.webReader(url: "https://example.com", retain_images: true)'

# 纯文本格式
mcporter call 'web-reader.webReader(url: "https://example.com", return_format: "text")'
```

**适用场景**: 需要更精确控制输出格式时使用。

## 微信公众号 / WeChat Articles

### 搜索公众号文章（backend-ready，不等于 verified）

```bash
# 搜索微信公众号文章
mcporter call 'exa.web_search_exa(query: "搜索关键词", numResults: 50, includeDomains: ["mp.weixin.qq.com"])'

# 观澜统一搜索：公开搜索优先，必要时把 WechatSogou 作为 best-effort 备份
guanlan search "搜索关键词" --site mp.weixin.qq.com --profile china --limit 50

# 显式使用实验性搜狗微信后端（需安装可选依赖）
guanlan search "搜索关键词" --backend wechat-sogou --limit 50
```

公众号能力口径必须诚实：Exa、WechatSogou 或 Camoufox 安装成功只代表 `backend-ready`，不代表端到端 `verified`。遇到搜狗验证码、反爬、登录墙、正文缺失或超时时应降级，不要自动打码、不要读取浏览器 Cookie。

### 阅读公众号文章全文（通过 Exa）

```bash
# 抓取文章全文
mcporter call 'exa.crawling_exa(urls: ["https://mp.weixin.qq.com/s/ARTICLE_ID"], maxCharacters: 10000)'
```

### 可选：Camoufox 阅读（反爬更强）

```bash
cd ~/.guanlan/tools/wechat-article-for-ai && python3 main.py "https://mp.weixin.qq.com/s/ARTICLE_ID"
```

> **注意**: Jina Reader 经常无法稳定读取微信文章，常见原因包括 CAPTCHA、登录态、JS 渲染和反爬策略。优先搜索同题公开信源；确需读原文时再使用可选后端，并向用户说明可能需要授权。

## RSS (feedparser)

```python
python3 -c "
import feedparser
for e in feedparser.parse('FEED_URL').entries[:5]:
    print(f'{e.title} — {e.link}')
"
```

**适用场景**: 订阅博客、新闻源、播客等 RSS feed。

## 选择指南

| 场景 | 推荐工具 |
|-----|---------|
| 通用搜索 | `guanlan search` |
| 中国中文搜索 | `guanlan search --profile china --scope ...` |
| 通用网页阅读 | `guanlan read` |
| Jina 不稳或正文缺失 | `guanlan read --backend direct` |
| 只读原 URL | `guanlan read --no-fallback-search` |
| 快速验证 Jina 输出 | Jina Reader (`curl r.jina.ai`) |
| 需要图片/格式控制 | web-reader MCP |
| 微信公众号 | 搜索公开转载/同题信源，必要时 Exa/Camoufox 可选阅读 |
| RSS 订阅 | feedparser |
| 微博/知乎等 | 先搜索公开页，再尝试 `guanlan read`，不要硬撞登录墙 |
