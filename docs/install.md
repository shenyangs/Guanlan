# 观澜安装指南

本文档写给正在执行安装任务的 Agent。目标是先把观澜 CLI 装到当前机器上，完成基础自检，并在用户明确需要时再安装可选渠道。MCP 是给 Agent/平台集成用的可选路径，不是普通用户的默认入口。

观澜第一版优先以 GitHub 源码发布。请先克隆可信仓库，再在仓库根目录执行本地安装；不要从来历不明的远程脚本直接安装。

## 安装边界

- 不在用户的项目工作区里克隆仓库或生成临时文件。
- 不主动读取浏览器 Cookie、钥匙串、Token 或登录态。
- 不自动执行发帖、评论、点赞、私信等写操作。
- 不使用 `sudo`，除非用户明确批准。
- 可选渠道按用户需要安装，不把“全部装好”当成默认目标。

推荐目录：

| 用途 | 目录 |
| --- | --- |
| 配置、Token、Cookie | `~/.guanlan/` |
| 可选工具和脚本 | `~/.guanlan/tools/` |
| 临时文件 | `/tmp/` |
| Agent skill | `~/.agents/skills/guanlan/`、`~/.claude/skills/guanlan/`、`~/.openclaw/skills/guanlan/` |

## 基础安装

推荐使用 `uv` 从 GitHub 一条命令安装：

```bash
uv tool install git+https://github.com/shenyangs/Guanlan.git
guanlan doctor
```

如果你使用 `pipx`：

```bash
pipx install git+https://github.com/shenyangs/Guanlan.git
guanlan doctor
```

如果只是临时试运行：

```bash
uvx --from git+https://github.com/shenyangs/Guanlan.git guanlan version
```

如果用户明确要求用 Homebrew，必须先刷新 tap，并在安装后校验版本：

```bash
brew update
brew tap shenyangs/tap
brew reinstall shenyangs/tap/guanlan
guanlan version
guanlan doctor
```

如果 `guanlan version` 低于 README 或发布说明中的当前版本，不要继续配置 MCP、可选渠道或登录态。先尝试：

```bash
brew update
brew reinstall shenyangs/tap/guanlan
guanlan version
```

如果仍然拿到旧版本，说明 Homebrew tap 尚未同步到最新发布；改用 GitHub/uv 安装路径：

```bash
uv tool install --force git+https://github.com/shenyangs/Guanlan.git
guanlan version
```

如果已经克隆 GitHub 仓库，也可以在仓库根目录执行：

```bash
pipx install .
guanlan install --env=auto
guanlan doctor
```

如果当前 Python 环境受到 PEP 668 限制，使用虚拟环境：

```bash
python3 -m venv ~/.guanlan-venv
source ~/.guanlan-venv/bin/activate
pip install .
guanlan install --env=auto
guanlan doctor
```

安装前想先看会做什么：

```bash
guanlan install --env=auto --dry-run
guanlan install --env=auto --safe
```

`--dry-run` 只预演步骤；`--safe` 只检查并给出提示，不主动改系统依赖。

## 基础自检

普通自检不读取敏感登录态：

```bash
guanlan doctor
```

查看诊断路径：

```bash
guanlan doctor --trace
```

切到中文场景画像：

```bash
guanlan profile set china
guanlan doctor --profile china
```

只有用户明确要求检查登录态时，才使用：

```bash
guanlan doctor --auth-check
```

## 可选渠道

基础安装完成后，再询问用户需要哪些渠道。常见选择：

| 渠道 | 安装命令 | 说明 |
| --- | --- | --- |
| Twitter/X | `guanlan install --env=auto --channels=twitter` | 需要 Cookie 或外部 CLI 配置。 |
| 微博 | `guanlan install --env=auto --channels=weibo` | 用于热搜、搜索和公开内容读取。 |
| 微信公众号 | `guanlan install --env=auto --channels=wechat` | 安装后只代表 backend-ready，端到端稳定性仍需按文章验证。 |
| 小红书 | `guanlan install --env=auto --channels=xiaohongshu` | 通常需要登录态。 |
| Reddit | `guanlan install --env=auto --channels=reddit` | 部分网络环境需要认证或代理。 |
| B站增强 | `guanlan install --env=auto --channels=bilibili` | 在基础视频能力上补热门、排行、搜索。 |
| 小宇宙 | `guanlan install --env=auto --channels=xiaoyuzhou` | 转录需要 Groq API Key。 |

用户明确要全部可选渠道时：

```bash
guanlan install --env=auto --channels=all
```

即使使用 `--channels=all`，Cookie、登录态和浏览器权限也不会自动读取。

## Cookie 与登录态

优先让用户自己确认是否需要登录态。需要时有两条路：

```bash
guanlan configure --from-browser chrome
```

这会在读取前显示安全提示，可能触发 macOS 钥匙串或浏览器权限弹窗。用户拒绝后，观澜仍会保留公开搜索、网页阅读和热榜能力。

也可以让用户通过 Cookie-Editor 导出 Cookie 后手动配置：

```bash
guanlan configure twitter-cookies "auth_token=...; ct0=..."
guanlan configure xhs-cookies "key1=value1; key2=value2; ..."
```

建议使用专用小号。Cookie 等同登录权限，主账号不适合作为自动化工具的默认凭据。

## 常用配置

配置代理：

```bash
guanlan configure proxy http://user:pass@host:port
```

配置 Groq Key，用于小宇宙或无字幕音频转录：

```bash
guanlan configure groq-key gsk_xxxxx
```

安装 Agent skill：

```bash
guanlan skill --install
```

## MCP 安装（可选）

优先保证 CLI 可用；只有当用户使用的 Agent、IDE 或平台支持 MCP 时，再配置这一节。观澜提供 `guanlan-mcp` console script。支持 JSON 配置的 MCP 客户端可以使用：

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

如果已经通过 `uv tool install` 或 `pipx install` 持久安装，也可以把 MCP command 直接写成：

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

## 完成检查

最后运行：

```bash
guanlan version
guanlan doctor --trace
```

发布前或维护者环境可以运行安装 smoke：

```bash
scripts/release_smoke.sh
```

向用户报告：

- 当前哪些基础渠道可用。
- 当前 `guanlan version` 是否与 README/发布说明一致。
- 哪些可选渠道需要登录、Cookie、代理或 API Key。
- 是否触发过敏感权限提示。
- 后续最适合使用的命令，例如 `search`、`read`、`hotnews`、`research`。

## 快速命令

| 命令 | 用途 |
| --- | --- |
| `guanlan install --env=auto` | 安装基础能力。 |
| `guanlan install --env=auto --dry-run` | 预演安装步骤。 |
| `guanlan install --env=auto --safe` | 安全模式检查。 |
| `guanlan doctor` | 普通健康检查。 |
| `guanlan doctor --trace` | 显示诊断路径。 |
| `guanlan profile set china` | 使用中文场景画像。 |
| `guanlan configure --from-browser chrome` | 显式读取浏览器 Cookie。 |
| `guanlan skill --install` | 安装 Agent skill。 |
