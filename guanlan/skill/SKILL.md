---
name: guanlan
description: >
  观澜是面向 AI Agent 的中文互联网信源与平台路由器。
  默认只读、低扰、明源，覆盖搜索、热榜、社交、视频、开发者社区与网页阅读。

  【路由方式】SKILL.md 包含路由表和常用命令，复杂场景需按需阅读对应分类的 references/*.md。
  分类：search / hotnews / social (小红书/抖音/微博/推特/B站/V2EX/Reddit) / career(LinkedIn) / dev(github) / web(网页/文章/公众号/RSS) / video(YouTube/B站/播客).

  Use when user asks to search, read, or interact on any supported platform,
  shares a URL, or asks to search the web.
triggers:
  - search: 搜/查/找/search/搜索/查一下/帮我搜
  - hotnews: 热榜/热点/今日热点/快讯/趋势/舆情
  - social:
    - 小红书: xiaohongshu/xhs/小红书/红书
    - 抖音: douyin/抖音
    - Twitter: twitter/推特/x.com/推文
    - 微博: weibo/微博
    - B站: bilibili/b站/哔哩哔哩
    - V2EX: v2ex
    - Reddit: reddit
  - career: 招聘/职位/求职/linkedin/领英/找工作
  - dev: github/代码/仓库/gh/issue/pr/分支/commit
  - web: 网页/链接/文章/公众号/微信文章/rss/读一下/打开这个
  - video: youtube/视频/播客/字幕/小宇宙/转录/yt
  - finance: 雪球/股票/stock/xueqiu/行情/基金
metadata:
  openclaw:
    homepage: local-repo
---

# 观澜 / Guanlan — 路由器

面向 AI Agent 的中文互联网信源与平台路由器。根据用户意图选择对应分类。

## Agent 运行规则

- 搜索、研究、热榜、回响和本地知识库检索时，默认使用 50 条以上候选池；复杂调研可提高到 80-100。
- 只有用户明确要“少量样本”“快速试一下”“只看前几条”时，才主动降低 limit。
- 如果新用户问“装好了怎么用/怎么让 Agent 用观澜”，先运行 `guanlan welcome`。
- 如果用户或 Agent 不知道观澜有哪些功能、该用哪个命令，先运行 `guanlan capabilities`；MCP 模式下调用 `guanlan_capabilities`。
- `--advisor` 输出的是证据边界和写作规则，Agent 需要据此生成自然建议，不要机械复述固定小标题。
- `research` 证据包会附带证据审计提示；遇到版本号、价格、参数量、发布日期冲突时，先说明不同来源分别怎么说，再给取舍依据。
- 更新观澜时必须全量更新，不要只跑增量 upgrade：优先 `uv tool install --force --upgrade guanlan`，注意 uv 只有 `--force` 可能重装旧锁定版本；Homebrew 用 `brew update && brew reinstall shenyangs/tap/guanlan`；pipx 用 `pipx install --force guanlan`。更新后运行 `hash -r`、`command -v guanlan`、`which -a guanlan`、`guanlan version`，再跑 `guanlan capabilities`、`guanlan doctor --install-check`、`guanlan doctor --trace`、`guanlan search "人工智能 政策" --profile china --limit 5 --trace`、`guanlan hotnews today --limit 5 --trends`。版本或路径不一致时停止配置 MCP。

## 路由表

| 用户意图 | 分类 | 详细文档 |
|---------|------|---------|
| 网页搜索/代码搜索 | search | [references/search.md](references/search.md) |
| 中文热榜/今日热点/快讯 | hotnews | [references/search.md](references/search.md) |
| 小红书/抖音/微博/推特/B站/V2EX/Reddit | social | [references/social.md](references/social.md) |
| 招聘/职位/LinkedIn | career | [references/career.md](references/career.md) |
| GitHub/代码 | dev | [references/dev.md](references/dev.md) |
| 网页/文章/公众号/RSS | web | [references/web.md](references/web.md) |
| YouTube/B站/播客字幕 | video | [references/video.md](references/video.md) |

## 零配置快速命令

```bash
# Exa 网页搜索
mcporter call 'exa.web_search_exa(query: "query", numResults: 50)'

# 观澜统一网页搜索（默认公开搜索，不需要 Cookie）
guanlan welcome
guanlan capabilities
guanlan search "query" --limit 50
guanlan search "EI会议 投稿 检索" --profile china --scope academic
guanlan search "最近 query 热点" --profile china --trace
guanlan search "中文问题" --profile china --limit 50 --trace  # 查看 Baidu/Bing/DDG 状态与 backend_recovery
guanlan search "query" --site zhihu.com --limit 50
guanlan search "query" --trace
guanlan search "query" --cache-ttl 3600
guanlan search "query" --format context
guanlan search "query" --format prompt
guanlan search "query" --source-chart
guanlan route "query"
guanlan research "query" --profile china --advisor
guanlan research "query" --profile china --format prompt
guanlan research "EI会议 投稿 检索 要求" --preset academic --read-top 0
guanlan prompt "query" --profile china --style evidence
guanlan context "query" --profile china --style evidence
guanlan research "product 用户评价" --preset reputation --read-top 0 --advisor
guanlan pulse "query" --format context

# 通用网页阅读
guanlan read "URL" --max-chars 12000
guanlan read "URL" --strict --trace
guanlan read "URL" --backend direct --extract metadata
guanlan read batch urls.txt --format context
guanlan read "URL" --watch
guanlan feeds curated --limit 80
guanlan feeds curated --category ai --min-score 85 --limit 80
guanlan feeds baidu-rss --limit 80
guanlan feeds wechat-rss --limit 80
guanlan feeds curated-sources --keyword AI --limit 80
guanlan feeds list

# 本地知识库
guanlan archive add "URL"
guanlan archive ingest-research "query" --limit 80
guanlan archive search "query" --format context
guanlan archive export --format rag-jsonl
guanlan mcp config --client codex
guanlan serve --host 127.0.0.1 --port 8765
guanlan plugin template my_company_api
guanlan eval benchmark
guanlan eval scenarios --format jsonl

# GitHub 搜索
gh search repos "query" --sort stars --limit 50

# 中文热榜（原生公开源，不需要 Cookie）
guanlan hotnews today --limit 50
guanlan hotnews today --limit 50 --trends
guanlan hotnews weibo --limit 50
guanlan hotnews bilibili --limit 50
guanlan hotnews ithome --limit 50
guanlan hotnews zhihu --json  # experimental，失败时改用 site:zhihu.com 搜索
guanlan hotnews list

# 助理视角：用户要建议、影响、下一步、或“可能为什么搜这个”时使用
guanlan research "query" --profile china --advisor

# Twitter 搜索
twitter search "query" --limit 50

# YouTube/B站字幕
yt-dlp --write-sub --skip-download -o "/tmp/%(id)s" "URL"

# Reddit 搜索
rdt search "query" --limit 50

# Reddit 读帖 + 评论
rdt read POST_ID

# V2EX 热门
curl -s "https://www.v2ex.com/api/topics/hot.json" -H "User-Agent: guanlan/1.0"
```

## 环境检查

```bash
# 检查可用 channel
guanlan doctor

# 查看诊断路径，确认是否跳过认证/Cookie/登录态探测
guanlan doctor --trace

# 扫描本地配置中的明文 Cookie、Token、Key 或代理凭据
guanlan doctor --check-config

# 查看 channel 稳定性、授权边界、批量边界和缓存概览
guanlan status

# 查看所有 MCP 服务
mcporter_list_servers()
```

## 工作区规则

**不要在 agent workspace 创建文件。** 使用 `/tmp/` 存放临时输出，`~/.guanlan/` 存放持久数据。

## 详细文档

根据用户需求，阅读对应的详细文档：

- [搜索工具](references/search.md) — Exa AI 搜索
- [社交媒体](references/social.md) — 小红书, 抖音, Twitter, B站, V2EX, Reddit
- [职场招聘](references/career.md) — LinkedIn
- [开发工具](references/dev.md) — GitHub CLI
- [网页阅读](references/web.md) — Jina Reader, 微信公众号, RSS
- [视频播客](references/video.md) — YouTube, B站, 小宇宙

## 配置渠道

如果某个 channel 需要配置，获取安装指南：
docs/install.md

用户只需提供 cookies，其他配置由 agent 完成。
