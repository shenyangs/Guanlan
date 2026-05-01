# Guanlan

> Observe the current, trace the source, keep the boundary clear.

Guanlan is an agent-first search and source-routing tool for the Chinese internet. It helps AI agents search public web pages, read URLs, inspect Chinese hot lists, and reason about source type before summarizing information for users.

The canonical documentation is maintained in Chinese:

- [中文 README](../README.md)
- [Agent usage guide](agent-usage.md)
- [Chinese web design notes](chinese-web-design.md)
- [Troubleshooting](troubleshooting.md)
- [Source attribution](SOURCE_ATTRIBUTION.md)

## Core Commands

```bash
guanlan search "keyword" --profile china --limit 8
guanlan search "keyword" --profile china --scope party_central
guanlan search "keyword" --profile china --scope ecommerce
guanlan read "https://example.com/article"
guanlan read "https://example.com/article" --backend direct
guanlan hotnews baidu --limit 10
guanlan doctor --trace
```

## Design Notes

Guanlan is not a stealth crawler and not an account automation framework. It is designed to be read-first, low-disturbance, source-aware, and explicit about authentication. Public sources are preferred. Cookie, browser, Keychain, and login-state access must be requested by the user.

Search results include source classification and quality scoring where possible. Jina Reader is used as a first reading path, with direct HTML fallback for mainland China realities such as cross-border latency, anti-crawling rules, JavaScript-heavy pages, login walls, and partial page rendering.
