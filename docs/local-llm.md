# 本地大模型联网指南

观澜可以作为无联网本地模型的“联网前置器”。本地模型不需要内置浏览器，也不需要读取浏览器 Cookie；由观澜先完成公开搜索、网页阅读、证据压缩和来源保留，再把上下文交给模型。

适用对象：

- Ollama
- LM Studio
- Open WebUI
- llama.cpp / Jan
- 本地 Agent 框架
- 任何只能吃 prompt、但不能自己联网的模型

## 一、最简单：直接生成 Prompt

```bash
guanlan prompt "最近 AI 眼镜在中国市场的主要趋势是什么？" --profile china > prompt.md
ollama run qwen3:latest < prompt.md
```

`guanlan context` 是 `prompt` 的别名，适合脚本或 Agent 工作流：

```bash
guanlan context "今天中文互联网有哪些 AI 技术文章值得读？" --profile china --read-top 1 > context.md
ollama run qwen3:latest < context.md
```

可以按任务选择 Prompt 风格：

```bash
guanlan prompt "这个产品现在值不值得买？" --preset reputation --style decision > prompt.md
guanlan prompt "新质生产力 最新政策影响" --preset policy --style evidence > prompt.md
guanlan prompt "今天中文互联网 AI 相关热点" --style concise > prompt.md
```

`decision` 偏行动建议，`evidence` 偏证据表和来源，`concise` 适合上下文较小的模型，默认 `deep` 适合完整调研。

`guanlan prompt` 默认会：

- 使用较大的候选池，默认 `--limit 80`。
- 精选 8 条代表证据。
- 摘读 2 条代表 URL。
- 加入助理视角规则，提醒模型保留证据边界。
- 加入查询策略和信源诊断，帮助模型区分官方、媒体、社区、用户样本和近期进展。

如果只想看公开搜索，不读正文：

```bash
guanlan prompt "某产品 用户评价" --preset reputation --read-top 0 > prompt.md
ollama run qwen3:latest < prompt.md
```

## 二、给已有命令加 `--format prompt`

搜索：

```bash
guanlan search "低空经济 广东 政策" --profile china --scope local_official --format prompt > prompt.md
ollama run qwen3:latest < prompt.md
```

研究证据包：

```bash
guanlan research "跨境电商 AI 工具" --preset ecommerce --limit 80 --format prompt > prompt.md
ollama run qwen3:latest < prompt.md
```

高阶研究工作流也可以直接给本地模型做前置联网：

```bash
guanlan compare "产品A" "产品B" --focus "价格 口碑 风险" --limit 80 --format context > context.md
guanlan timeline "某事件 最新进展" --limit 80 --format context > context.md
guanlan dossier "某公司" --focus "业务 口碑 风险" --limit 80 --format context > context.md
ollama run qwen3:latest < context.md
```

`compare` 适合让本地模型写“怎么选/差异在哪”，`timeline` 适合写“发生顺序/最新进展”，`dossier` 适合写“对象档案/待核验问题”。三者都保留来源链接和边界，不要求模型自己联网。

读单篇网页：

```bash
guanlan read "https://example.com/article" --format prompt --question "这篇文章的核心信息是什么？" > prompt.md
ollama run qwen3:latest < prompt.md
```

批量读网页：

```bash
guanlan read batch urls.txt --format prompt --question "请综合这些材料，判断共同趋势。" > prompt.md
ollama run qwen3:latest < prompt.md
```

## 三、接入支持 MCP 的本地 Agent

先生成配置：

```bash
guanlan mcp config --client codex
guanlan mcp config --client claude --format json
guanlan mcp config --client openwebui --format json
```

默认配置只启动只读 MCP server：

```json
{
  "mcpServers": {
    "guanlan": {
      "command": "guanlan-mcp",
      "args": []
    }
  }
}
```

接入后，Agent 应优先使用：

- `guanlan_search`
- `guanlan_research`
- `guanlan_read`
- `guanlan_hotnews`
- `guanlan_feeds`
- `guanlan_pulse`
- `guanlan_archive_search`
- `guanlan_status`

复杂研究建议让 Agent 使用 `limit=50-100`，再从观澜返回的精选代表证据中组织回答。

## 四、不支持 MCP：使用本地只读 HTTP

```bash
guanlan serve --host 127.0.0.1 --port 8765
```

默认只建议监听本机。如果必须让 Open WebUI、局域网机器或服务器上的其它进程访问，使用 token：

```bash
export GUANLAN_SERVE_TOKEN="change-me"
guanlan serve --host 0.0.0.0 --port 8765
```

请求侧添加 `Authorization: Bearer change-me` 或 `X-Guanlan-Token: change-me`。

常用接口：

- `GET /health`
- `POST /route`
- `POST /search`
- `POST /research`
- `POST /compare`
- `POST /timeline`
- `POST /dossier`
- `POST /context`
- `POST /prompt`
- `POST /read`
- `GET /feeds?source=curated&limit=80`
- `GET /hotnews?source=today&limit=50&trends=1`
- `POST /archive/search`

示例：

```bash
curl -s http://127.0.0.1:8765/research \
  -H 'content-type: application/json' \
  -d '{"query":"AI 眼镜 中国市场 趋势","profile":"china","limit":80,"advisor":true}'
```

直接取本地模型 Prompt：

```bash
curl -s http://127.0.0.1:8765/context \
  -H 'content-type: application/json' \
  -d '{"query":"AI Agent 在中国的产品化进展","profile":"china","read_top":1}' \
  | python -c 'import json,sys; print(json.load(sys.stdin)["prompt"])'
```

RSS / feeds 是公开外部源，可能因源站或网络抖动超时。观澜会优先返回最近成功缓存，并在结果里标记 `feed_status=stale_cache`；本地模型回答时应把这类结果当作阅读线索，而不是实时排名。

## 五、把搜过的材料变成本地知识库

如果你希望本地模型反复使用同一批中文资料，可以先把观澜 research 的代表证据沉淀到本地 archive：

```bash
guanlan archive ingest-research "人工智能 政策 原文" --limit 80
guanlan archive search "人工智能 政策" --format context --trace
guanlan archive verify
guanlan archive context "人工智能 政策" --limit 20
```

导出给 RAG、向量库或个人知识库：

```bash
guanlan archive export --format rag-jsonl > guanlan-rag.jsonl
guanlan archive export --format llamaindex-jsonl > guanlan-llamaindex.jsonl
guanlan archive export --format langchain-jsonl > guanlan-langchain.jsonl
guanlan archive export --format openwebui-jsonl > guanlan-openwebui.jsonl
guanlan archive pack "人工智能 政策" --format langchain-jsonl --output policy-pack.jsonl
```

`rag-jsonl` 只包含 RAG 常用字段，便于导入；如果你的系统需要完整来源诊断、路线计划、阅读质量和原始元数据，请改用：

```bash
guanlan archive export --format jsonl > guanlan-full.jsonl
```

Archive 保存在本机 `~/.guanlan/archive.db`，不会自动上传，也不会绕过高风险社交平台的批量保护。
如果本地模型需要解释“为什么召回这条材料”，让 Agent 使用 `archive search --trace`；如果怀疑正文没有入库，用 `archive inspect 1`；如果迁移或升级后索引异常，用 `archive reindex` 或 `archive verify`。

如果你想把这批资料变成 AI Agent Wiki，而不是只导出 JSONL：

```bash
guanlan archive wiki build --output ./guanlan-wiki --format both
guanlan archive wiki context "人工智能 政策"
```

Wiki 只反映本地 archive 中已有资料，不代表全网知识。低质量或正文较薄的材料会被标为 candidate，本地模型回答时应先说明证据边界。

## 六、安全边界

- 默认只读。
- 默认不读取浏览器 Cookie。
- 默认不触发登录态平台动作。
- 不发布、评论、点赞、关注或私信。
- 涉及授权能力时，必须由用户显式触发。

本地模型拿到的是观澜整理后的证据包，不是对用户环境的静默访问。
