# 观澜排障手册

先从低扰诊断开始：

```bash
guanlan doctor --trace
```

它会显示每个渠道的状态、后端和敏感探测是否被跳过。除非用户明确需要，排障时不要主动读取 Cookie、钥匙串或登录态。

## macOS 钥匙串弹窗

普通诊断：

```bash
guanlan doctor
```

默认跳过认证和登录态深度探测。下面这些操作可能触发钥匙串或浏览器权限提示：

- `guanlan doctor --auth-check`
- `guanlan configure --from-browser chrome`
- 第三方工具自己的登录检查，例如 `gh auth status`、`xhs status`

需要检查认证时再运行：

```bash
guanlan doctor --auth-check
```

如果用户拒绝授权，观澜应继续使用公开搜索、网页阅读和热榜能力。

## 命令不存在

如果 `guanlan` 不存在，先确认安装方式：

```bash
pipx list
```

本地仓库阶段可在仓库根目录重装：

```bash
pipx install --force .
```

虚拟环境安装时，需要先激活环境：

```bash
source ~/.guanlan-venv/bin/activate
guanlan doctor
```

## 搜索结果不理想

中文资料优先使用中文场景画像：

```bash
guanlan search "关键词" --profile china --limit 8
```

需要更明确的信源范围时使用 scope：

```bash
guanlan search "人工智能 新质生产力" --scope party_central
guanlan search "跨境电商 AI" --scope ecommerce
guanlan search "某地 政策" --scope local_official
```

如果用户要的是“查清楚并给依据”，优先用研究证据包：

```bash
guanlan research "关键词" --profile china --read-top 2
```

## 网页读取失败

默认读取：

```bash
guanlan read "URL"
```

如果 Jina Reader 读取不完整或失败，尝试直连原网页：

```bash
guanlan read "URL" --backend direct
```

如果用户要求严格只读原文，不希望搜索兜底：

```bash
guanlan read "URL" --no-fallback-search
```

遇到登录墙、验证码、付费墙或强风控页面时，不要硬撞。先用公开搜索找同题来源，再向用户说明原文读取限制。

## Cookie 或登录态问题

观澜不会在安装或普通诊断中自动读取 Cookie。用户明确授权后再运行：

```bash
guanlan configure --from-browser chrome
```

手动导入 Cookie 时，建议用户使用 Cookie-Editor 导出 Header String 或 JSON，再交给 Agent 配置：

```bash
guanlan configure twitter-cookies "auth_token=...; ct0=..."
guanlan configure xhs-cookies "key1=value1; key2=value2; ..."
```

建议使用专用小号，不建议把主账号 Cookie 交给自动化工具。

## 可选渠道不可用

先看诊断：

```bash
guanlan doctor --trace
```

常见原因：

| 渠道 | 常见问题 | 处理方式 |
| --- | --- | --- |
| Twitter/X | 缺 Cookie、网络无法访问 x.com、外部 CLI 未安装 | 配置 Cookie 或代理，按需安装 `twitter-cli`。 |
| 小红书 | 缺登录态、Cookie 过期、外部后端不可用 | 重新登录或手动导入 Cookie。 |
| Reddit | 网络环境限制、认证状态失效 | 检查 `rdt-cli` 和代理。 |
| B站 | 服务器 IP 受限、字幕或视频信息缺失 | 本地运行优先，服务器环境按需配置代理。 |
| 小宇宙 | 缺 Groq API Key 或 ffmpeg | 配置 `guanlan configure groq-key ...`，安装 ffmpeg。 |

## 更新检查失败

第一版早期如果维护者还没有创建 GitHub Release，远程更新检查失败不一定代表安装损坏。

GitHub 源码安装的更新方式：

```bash
git pull --ff-only
pipx install --force .
guanlan doctor --trace
```

## 仍然无法判断

把下面三项发给维护者或记录到 issue：

```bash
guanlan version
guanlan doctor --trace
guanlan profile show
```

不要附带 Cookie、Token、完整代理地址或浏览器导出的登录态。
