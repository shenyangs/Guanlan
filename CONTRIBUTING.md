# 贡献指南

观澜 / Guanlan 是面向 AI Agent 的中文互联网研究工具。贡献时请把“功能稳定、证据边界清楚、Agent 可长期依赖”放在第一位；新增能力必须能优雅降级，不能让基础搜索、阅读、热榜、archive 或 Agent 输出契约变脆。

## 开发环境

```bash
git clone https://github.com/YOUR_USERNAME/Guanlan.git
cd Guanlan
uv sync --all-extras --dev
uv run guanlan version
```

如果不用 `uv`，也可以：

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
```

## 提交前检查

小改动至少运行与改动相关的测试；涉及搜索、路由、浏览器补证、archive、MCP、HTTP、安装或发版时，优先使用项目内的质量命令。

```bash
uv run ruff check guanlan tests
uv run pytest
scripts/pre_release_status.sh
guanlan quality foundational
guanlan quality coverage
guanlan quality regression
guanlan quality robustness
guanlan quality backend-fixtures
guanlan eval benchmark
```

完整发版门禁以 `scripts/release_gate.sh` 为准。新版本不能静默缩小默认结果池，不能删除 Agent 依赖的证据字段，也不能把污染或低质量后端结果无诊断地返回。

## 贡献原则

- **中文优先**：commit subject、CHANGELOG、release notes 使用中文表达；可保留 `feat:` / `fix:` / `docs:` 等常规前缀。
- **稳定优先**：不要为了高级工作流破坏基础 `search -> read` 路径。复杂能力应作为上层工作流增强，而不是让简单搜索过度思考。
- **证据优先**：搜索、研究、热榜、archive 输出要保留来源、证据角色、风险标签、质量诊断和可追溯字段。
- **候选池优先**：普通研究默认保留足够大的结果池；不要把默认 limit 调小来掩盖超时或上游不稳定。
- **只读优先**：默认公开搜索和读取；涉及登录态、Cookie、钥匙串、私信、订单、后台或个人资料的路径必须显式授权并清楚写出边界。
- **优雅降级**：上游被验证码、WAF、动态渲染或限流影响时，要返回诊断、缓存状态、fallback 建议或外部补读策略，不要假装“没有结果”。

## 浏览器辅助补证

浏览器补证是用户授权后的补充证据路径，不是默认爬虫，也不是自动接管浏览器。

- 默认路径是 `guanlan diagnose page` 判断页面问题，再由 `guanlan browser-assist plan "URL" --json` 生成宿主 Agent 浏览器任务。
- 宿主 Agent 只读取目标页面的浏览器可见内容；如需登录、验证或切换账号，由用户在浏览器里自行完成。
- 可见页补证默认不读取 Cookie、Token、密码、钥匙串、浏览器存储、私信、订单、后台或无关个人资料。
- 如果确实需要 Cookie，必须另行说明目标平台、用途、风险和只读范围，并获得用户单独明确授权；不要把 Cookie 读取混在普通可见页授权里。
- 不要新增基于 Playwright 独立浏览器 profile、`browser-cookie3` 扫描本机浏览器、钥匙串读取或隐式 Cookie 抽取的默认路径。
- 用户授权后的可见页结果优先用 `guanlan archive add-browser-note --from-json browser-notes.jsonl` 入库；`--url ... --text-file` 只是无浏览器提取能力时的手动兜底。

## 修改文档和 Agent 记忆面

以下文件是 Agent 操作观澜的耐久记忆面，相关行为变化需要同步：

- `AGENTS.md`
- `docs/agent-playbook.md`
- `docs/agent-usage.md`
- `guanlan/skill/SKILL.md`
- `README.md`
- `llms.txt`

涉及安装、版本、发布、凭据或安全边界时，也要检查：

- `CHANGELOG.md`
- `SECURITY.md`
- `.env.example`
- `constraints.txt`
- `docs/install.md`
- `docs/update.md`
- `docs/release-automation.md`

## PR 建议

- 保持改动聚焦，一次 PR 解决一个明确问题。
- 新增 source pack、路由、preset、recipe 或质量门控时，必须配套测试，防止路由越增强越乱。
- 新增命令或输出字段时，同步 Agent 文档和契约测试。
- 修 bug 时尽量加入回归测试，尤其是中文复合词、近期热点、平台动态页、低质量后端误杀和 archive 入库链路。
- 不要 revert 其他进程或用户的未关联改动；先确认再处理。

## 问题反馈

提交 issue 时请尽量包含：

- `guanlan version`
- `command -v guanlan` 与 `which -a guanlan`
- 操作系统和 Python 版本
- 触发命令、参数、trace 或质量摘要
- 是否使用代理、MCP、Homebrew、uv 或 pipx
- 如果是网络问题，请说明超时时间和是否使用缓存

如果反馈涉及安全、授权、凭据或不适合公开的复现材料，也可以发到 `shenyangsun@gmail.com`。
