# 观澜 v0.5.10 改动报告

日期：2026-05-05

## 一、版本定位

v0.5.10 是一次以“浏览器辅助补证可执行化”和“断点后稳定性复核”为核心的小版本更新。

它不改变观澜的基础搜索、阅读、热榜、研究和归档主路径，而是在公开读取不足、平台动态页、登录墙或验证页场景下，把原先的浏览器补证计划进一步变成 Agent 可以理解和执行的稳定契约。

## 二、核心变化

### 1. 浏览器辅助补证从 plan 升级为 adapters/run

新增命令：

```bash
guanlan browser-assist adapters
guanlan browser-assist run "URL" --adapter host-browser --json
```

`host-browser` 是默认稳定路径：观澜只生成执行契约，由宿主 Agent 已有浏览器、Computer Use 或 WebView 打开目标页，并在用户授权后读取目标页面可见内容。

`open-cli` 是 best-effort 桥接：只负责打开页面，正文仍由宿主 Agent 读取。

`xhs-cli` 是 experimental 外部适配器：只有用户已经安装并配置命令模板时才可用；未配置时返回清楚的 `adapter_config_required`，不会让 Agent 临时下载 Playwright 或读取浏览器 profile。

### 2. MCP / HTTP / 工具注册表同步

新增 MCP 工具：

```text
guanlan_browser_assist_run
```

新增 HTTP 只读服务入口：

```text
POST /browser-assist/run
```

`guanlan/tool_registry.py` 同步注册该能力，`quality robustness` 已覆盖 CLI、MCP、HTTP 的工具面一致性。

### 3. 安全边界进一步明确

本轮再次收紧 Agent 口径：

- 默认只读取用户授权后的目标页可见内容。
- 不读取 Cookie、Token、密码、钥匙串、浏览器 profile、浏览器数据库、localStorage、sessionStorage、私信、订单、后台或无关个人资料。
- 不执行点赞、评论、关注、发帖、私信、下单、提交表单等写操作。
- 如果确实需要 Cookie，必须单独说明目标平台、用途、风险和只读范围，并获得用户单独明确授权。
- 手动复制正文只是宿主 Agent 没有浏览器提取能力时的兜底，不是默认路径。

### 4. Archive 长链路耐心提示

`archive ingest-search` / `archive ingest-research` 增加 `timeout_recommendation`，摘要输出会提醒 Agent：

- 搜索并自动归档是多阶段链路，不应用 10-30 秒过早判定超时。
- 如果 `phase_log` 仍在推进，应保持耐心。
- 弱网络下优先重试、用缓存或降低 `read_top`，不要为了速度缩小正常候选池。

### 5. Agent 文档和 Skill 同步

已同步：

- `AGENTS.md`
- `docs/agent-playbook.md`
- `docs/agent-usage.md`
- `guanlan/skill/SKILL.md`
- `llms.txt`
- `CONTRIBUTING.md`
- `SECURITY.md`
- `CLAUDE.md`
- `.env.example`
- `constraints.txt`

目标是让下游 Agent 明白：观澜规划补证路线，宿主浏览器读取可见证据，Cookie 访问必须单独授权。

## 三、验证结果

本轮发布前已完成以下检查：

```text
uv run pytest -q
554 passed, 1 warning

uv run ruff check .
All checks passed

git diff --check
pass

uv run guanlan quality robustness --format json
26/26 pass, score=100.0
```

额外烟测：

- `guanlan version` 返回 `观澜 / Guanlan v0.5.10`
- `guanlan browser-assist adapters` 正常列出 `host-browser` / `open-cli` / `xhs-cli`
- `guanlan browser-assist run ... --adapter host-browser --json` 返回宿主浏览器执行契约
- `guanlan browser-assist run ... --adapter open-cli --json` 返回 ready-to-open
- `guanlan browser-assist run ... --adapter xhs-cli --json` 在未配置时返回 `adapter_config_required`
- `guanlan browser-assist run ... --adapter xhs-cli --platform wechat --json` 正确拒绝不匹配平台
- `guanlan hotnews hotboard:catalog:*` 对外输出没有暴露底层供应商名
- `scripts/pre_release_status.sh` 在 dirty 模式下按设计阻止发布；`GUANLAN_RELEASE_ALLOW_DIRTY=1` 本地诊断通过

## 四、残余风险

- 本机仍存在多个 `guanlan` 可执行路径：仓库 venv、`~/.local/bin`、Homebrew。发布后安装验证时需要继续使用完整 reinstall 和 `which -a guanlan` 检查，避免旧版本优先。
- `xhs-cli` 只是预留外部适配器入口；是否真正可用取决于用户本机是否安装并配置命令模板。
- 浏览器辅助补证的可靠性仍取决于宿主 Agent 是否真的具备浏览器可见页提取能力。

## 五、结论

v0.5.10 可以作为 v0.5.9 浏览器辅助补证能力的稳健增强版发布。

它没有把基础搜索路径变重，也没有让 Agent 为普通搜索任务过度思考；只是在公开读取不足的场景下，给 Agent 一条更清楚、更安全、更可执行的补证路径。
