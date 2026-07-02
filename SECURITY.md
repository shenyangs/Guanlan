# Security Policy

观澜 / Guanlan 是 CLI-first、read-first 的中文互联网研究工具。安全策略的核心是：默认公开、只读、低扰；任何涉及登录态、Cookie、钥匙串或私密数据的动作，都必须有清楚的用户授权边界。

## Supported Versions

| Version | Supported |
| --- | --- |
| Latest 0.7.x | Yes |
| Older alpha releases | Best-effort |

## 默认安全边界

观澜默认不会：

- 读取浏览器 Cookie、Token、密码、钥匙串、浏览器数据库或本地私密配置。
- 读取私信、订单、后台、管理页或与任务无关的个人资料。
- 自动点赞、评论、关注、发帖、私信、下单、提交表单或执行其他写操作。
- 把 archive、Wiki、RAG 导出或本地 HTTP 服务当作云同步服务。

`doctor` 默认只做低扰诊断；深度授权检查必须由用户显式触发。

## 浏览器辅助补证

当公开读取遇到动态页壳、登录墙、WAF、安全验证或弱正文时，观澜可以生成浏览器辅助补证计划。这个计划只说明“宿主 Agent 应该如何在用户授权后读取目标页面的可见内容”。

- 可见页补证默认不读取 Cookie、Token、钥匙串、浏览器存储或无关个人数据。
- 如果页面需要登录、验证或切换账号，应由用户在可见浏览器里完成。
- 如果确实需要 Cookie，必须另行说明目标平台、用途、风险和只读范围，并获得用户单独明确授权。
- 即使获得 Cookie 授权，也不得读取密码、钥匙串、私信、订单、后台或无关个人资料，不得执行写操作。

## 本地服务和归档

- 本地 HTTP 服务默认应绑定 `127.0.0.1`。如果监听局域网或公网地址，必须设置 `--token` 或 `GUANLAN_SERVE_TOKEN`。
- Archive、Wiki、RAG 导出都是本地资料资产；分享前请确认其中没有用户授权页面、内部资料或敏感上下文。
- `guanlan doctor --check-config` 可扫描本地配置中疑似明文 Cookie、Token、API key 或代理凭据的路径，但不会泄露原值。

## Reporting a Vulnerability

If you discover a security vulnerability in Guanlan, please report it through a private maintainer channel. The project has not enabled a public GitHub security advisory endpoint yet.

You can also send security reports to `shenyangsun@gmail.com`.

Please do not disclose security vulnerabilities in a public issue, discussion, or social post before maintainers have had time to assess and respond.

## What to Include

- Description of the vulnerability
- Steps to reproduce
- Affected versions
- Potential impact
- Suggested fix, if any
- Whether credentials, browser state, local archive, MCP, HTTP service, or platform authorization are involved

## Response Timeline

- Acknowledgement within 48 hours
- Status update within 7 days
- Fix timeline communicated within 14 days

## In Scope

- Sensitive data exposure
- Unexpected Cookie / Token / Keychain / local file access
- Authorization bypass in browser-assisted evidence, MCP, HTTP service, or archive flows
- Remote code execution
- Path traversal or arbitrary file read
- SSRF or unsafe URL handling
- SQL, command, or prompt injection that affects evidence boundaries

## Out of Scope

- Vulnerabilities in third-party dependencies; report those to the dependency maintainer
- Social engineering attacks
- Denial of service via resource exhaustion against public upstream sites
- Public web pages changing structure, unless Guanlan handles the failure unsafely

## Credits

We appreciate responsible disclosure and will credit researchers in release notes unless anonymity is requested.
