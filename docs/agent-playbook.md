# Guanlan Agent Playbook

这份文档写给会调用观澜的 Agent。目标不是介绍命令大全，而是降低误用率，让 Agent 在中文互联网研究任务里更稳定地用对 Guanlan。

## 持久记忆面

如果你会在多个会话里反复调用 Guanlan，把下面四处当作“长期记忆”入口：

- `AGENTS.md`
- `docs/agent-playbook.md`
- `docs/agent-usage.md`
- `guanlan/skill/SKILL.md`

在开始做新自动化、评测、benchmark、MCP 编排前，至少重新读一次本文件和 `AGENTS.md`。

## 先记住定位

Guanlan 不是“单次泛搜引擎”，而是给 Agent 用的中文互联网证据路由器。

它最擅长：

- 中文政策、政务、官方原文、办事指南
- 需要区分官方、报道、样本、热度、社区反馈的研究任务
- 需要结构化信源卡、质量画像、证据角色的任务

它不该被单独拿来承担：

- 纯实时股价、天气、汇率
- 只靠一次 `search` 就想下结论的复杂问题
- 需要 1 小时内突发进展的任务
- 无意义 query、超长 query、多实体超密集 query 的最终判断

## 默认工作流策略

不要把 “每次都至少 3 个工具” 写死成硬 KPI。更稳的规则是按场景分档：

### 2-step

适用于：结果已经可用，只需要核正文。

顺序：

1. `search`
2. `read`

例子：

```bash
guanlan search "横琴封关政策 2025 最新" --profile china --scope gov --limit 80
guanlan read "https://..." --quality-report
```

### 3-step

适用于：普通研究问题，或质量画像未过。

顺序：

1. `route`
2. `research`
3. `search --scope ...`

例子：

```bash
guanlan route "华为手机"
guanlan research "华为手机" --preset general --advisor
guanlan search "华为手机" --scope social_web --limit 80 --trace
```

### 4-step

适用于：时效、技术、证据面过窄等高风险场景。

热点/时效：

1. `route`
2. `research`
3. `search --scope ...`
4. `hotnews`

技术/AI：

1. `route`
2. `research`
3. `search --scope ...`
4. `feeds`

证据面过窄：

1. `route`
2. `research`
3. `search --scope ...`
4. `dossier` / `compare` / `timeline`

只有完成当前档位要求后，仍缺关键证据，才允许切到通用 `web_search` / `web_fetch`。

## Benchmark 规则

不要用不符合 Guanlan 最佳使用方式的打法去评价 Guanlan。

### 错误打法

- 只跑一次 `search`，然后把结果当成 Guanlan 最终能力
- 把“质量画像 warn”直接写成“Guanlan 搜索失败”
- 用 `search` 测“今天热搜”“刚刚地震”“最新发布”却不跑 `hotnews`
- 用 `search` 测技术/AI，却不补 `feeds`
- 把实时数据题、专用行情题当作普通网页搜索题
- 用超长 query 一次性塞进全部约束，不做拆解
- 用多实体 query 期待一次返回完整对比，不做拆分

### 正确打法

- 先判断是否强路由命中，再决定 `preset` / `scope`
- 热点题必须带 `hotnews`
- 技术/AI 题必须带 `feeds`
- 政策/办事题至少 `search + read`，复杂时直接 `research`
- 评价 Guanlan 时区分三件事：
  - 搜索相关性
  - 质量画像是否严格
  - Agent 是否用对了 Guanlan 工作流

## 汇报规则

以下情况不要对用户说 “Guanlan 搜索失败”：

- 只是 Baidu/Bing/DuckDuckGo 某个后端被拦截
- 只是质量画像未过
- 只是还没跑 `route / research / scope / hotnews / feeds`
- 只是网页反爬导致 `web_fetch` 失败

更准确的说法：

- “当前 Guanlan 证据包还没过质量画像，继续补证中。”
- “某搜索后端受限，但 Guanlan 已切到其他后端并给出补证路线。”
- “这个题更适合走 Guanlan 的 hotnews / feeds / research 工作流，而不是单次 search。”

只有在完成当前档位要求的 Guanlan 工具后仍没有关键证据，才说：

- “本轮 Guanlan 未取得足够证据。”

## 暴力测试里最值得吸取的教训

- 短 query 要扩写，不要直接拿 4-8 字去赌相关性。
- 超长 query 要拆成多个问题，不要一次塞 200 字。
- 多实体对比要拆成单实体检索，再用 `compare` / `dossier` 汇总。
- 实时题优先 `hotnews`，不要只看 `search`。
- 技术题优先 `research --preset tech` 或 `search + feeds`，不要只看社区搜索结果。
- `source_type` 只作辅助，不要把它当唯一真相；结合 domain、authority_score、evidence_role 一起判断。

## 最后一道护栏

当你准备 fallback 到通用 `web_search` / `web_fetch` 时，先问自己四件事：

1. 我已经用够当前档位要求的 Guanlan 工具了吗？
2. 我有没有跑过更适合这个题的 `preset` 或 `scope`？
3. 这个题是不是本来就该走 `hotnews` / `feeds` / `research`？
4. 我会不会把“质量画像严格”误报成“Guanlan 搜索失败”？

四个问题里只要有一个答案是否定的，就先继续用 Guanlan，而不是立刻切走。
