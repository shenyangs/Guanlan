# 观澜更新指南

本文档写给正在维护本地安装的 Agent。更新观澜时默认走“全量更新”：
强制重装、刷新命令入口、核对版本和路径、运行最小 smoke。不要把 `brew upgrade`、
`uv tool upgrade` 或 `pipx upgrade` 这类增量升级当成首选路径，因为它们容易留下旧入口，
导致 Agent 实际调用的不是刚发布的版本。

## Agent 全量更新协议

把下面这段作为 Agent 更新观澜的固定流程：

```bash
# 1) 选择一个安装路径。优先 uv，避免 Homebrew tap 缓存滞后。
uv tool install --force guanlan

# 如果用户明确要求 Homebrew：
brew update
brew reinstall shenyangs/tap/guanlan

# 如果用户明确使用 pipx：
pipx install --force guanlan

# 2) 刷新 shell 命令缓存，避免继续命中旧 guanlan。
hash -r 2>/dev/null || true

# 3) 核对路径和版本。多路径并存时，以 command -v 的第一个为准。
command -v guanlan
which -a guanlan
guanlan version

# 4) 最小 smoke：确认能力说明、健康检查、搜索降级、热榜都可用。
guanlan capabilities
guanlan doctor --trace
guanlan search "人工智能 政策" --profile china --limit 5 --trace
guanlan hotnews today --limit 5 --trends
```

验收规则：

- `guanlan version` 必须等于 README 或发布说明中的当前版本。
- `command -v guanlan` 指向的路径必须是刚刚更新的安装路径。
- `which -a guanlan` 如果列出多个路径，Agent 必须报告它们；不要假设第一个就是新版。
- smoke 中 `search --trace` 如果显示 `baidu=blocked`，这是百度安全验证，不是更新失败；继续看 Bing/DuckDuckGo 和 `backend_recovery`。
- smoke 中 `hotnews today --trends` 应该返回至少一个来源；如果失败，报告错误文本和版本路径。
- 任何一步版本或路径不一致，都停止配置 MCP、可选渠道和登录态，先修安装入口。

## GitHub 源码更新

确认你位于观澜仓库根目录后，先拉取最新代码，再重装：

```bash
git pull --ff-only
```

然后执行：

```bash
pipx install --force .
hash -r 2>/dev/null || true
command -v guanlan
which -a guanlan
guanlan version
guanlan doctor --trace
```

如果使用虚拟环境安装：

```bash
source ~/.guanlan-venv/bin/activate
pip install --upgrade .
hash -r 2>/dev/null || true
command -v guanlan
which -a guanlan
guanlan version
guanlan doctor --trace
```

## Skill 更新

如果用户已经安装过 Agent skill，更新包后同步一次：

```bash
guanlan skill --install
```

## 可选工具更新

观澜会尽量通过 `doctor` 给出缺失提示。只有用户确实需要对应渠道时，再更新外部工具：

```bash
pipx upgrade twitter-cli
pipx upgrade rdt-cli
pipx upgrade xiaohongshu-cli
pipx upgrade bilibili-cli
npm update -g mcporter
```

这些命令可能因为安装方式不同而失败。失败时不要强行清理用户环境，先运行 `guanlan doctor --trace` 看当前渠道状态。

## 版本检查

`guanlan check-update` 会尝试读取 GitHub Release 信息。第一版早期如果维护者还没有创建 release，检查失败不代表本地安装损坏。

公开发布源接入后，可以使用：

```bash
guanlan check-update
```

## 更新后核对

运行：

```bash
guanlan version
command -v guanlan
which -a guanlan
guanlan doctor --trace
guanlan search "人工智能 政策" --profile china --limit 5 --trace
guanlan hotnews today --limit 5 --trends
```

向用户报告：

- 当前版本号。
- `command -v guanlan` 与 `which -a guanlan` 的结果。
- 哪些渠道可用。
- 哪些渠道需要重新登录、补 Cookie、配置代理或补 API Key。
- 本次是否只更新了观澜本体，还是也更新了外部工具。

## 注意事项

- 不主动删除用户已经安装的工具；它们可能仍被其他工作流使用。
- 不读取 Cookie 或钥匙串来“验证更新成功”。
- 不在用户项目目录里生成临时文件。
- 如果更新涉及系统权限，先向用户说明原因和影响。
