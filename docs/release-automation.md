# 发布自动化（PyPI + Homebrew Tap）

本项目已经配置以下自动发布链路：

1. 推送 `v*` tag 后自动构建并发布到 PyPI。
2. PyPI 发布成功后，自动更新 `shenyangs/homebrew-tap` 中的 `Formula/guanlan.rb`。

对应 workflow：`.github/workflows/release-pypi.yml`

## 一次性配置

### 1) 配置 PyPI Trusted Publisher

在 PyPI 项目 `guanlan` 的 Publishing 页面添加 GitHub Trusted Publisher：

- Owner: `shenyangs`
- Repository: `Guanlan`
- Workflow: `release-pypi.yml`
- Environment: `pypi`

GitHub 侧 workflow 已使用 OIDC（`id-token: write`），无需保存 PyPI API token。

### 2) 配置 Homebrew tap 推送 token

在 `shenyangs/Guanlan` 仓库设置一个 secret：

- Name: `HOMEBREW_TAP_GITHUB_TOKEN`

推荐使用 fine-grained PAT，并只授予 `shenyangs/homebrew-tap` 的 `Contents: Read and write` 权限（以及默认 metadata 读取权限）。

## 发版流程

版本约定：

- 默认每次发布/推送功能改动时递增 patch 版本，即 `+0.0.1`。
- 版本号需要同时更新 `pyproject.toml` 和 `guanlan/__init__.py`。
- 每次发版前同步更新 `CHANGELOG.md`，把已完成内容放入对应版本，把下一版计划保留在 `Unreleased`。
- 默认直接推送到 `main`，不走长期 release 分支。

流程：

1. 更新版本号，例如 `0.1.12 -> 0.1.13`。
2. 更新 `CHANGELOG.md`。
3. 运行基础质量检查和安装 smoke，例如 `ruff`、`pytest`、`uv build`、`scripts/release_smoke.sh`。
4. 提交代码并推送到 `main`。
5. 打 tag 并推送，例如：

```bash
git tag v0.1.13
git push origin main
git push origin v0.1.13
```

6. 等待 `release` workflow 完成：
   - Job `publish-pypi`：发布到 PyPI。
   - Job `update-homebrew-tap`：更新 tap 仓库公式。

## 用户安装方式

PyPI：

```bash
uv tool install guanlan
```

Homebrew：

```bash
brew tap shenyangs/tap
brew install guanlan
```

## 故障排查

- `publish-pypi` 失败：
  - 检查 PyPI Trusted Publisher 配置中的 repo/workflow/environment 是否完全匹配。
- `update-homebrew-tap` 失败：
  - 检查 `HOMEBREW_TAP_GITHUB_TOKEN` 是否有效，且对 `homebrew-tap` 具有写权限。
  - 检查 `shenyangs/homebrew-tap` 是否存在、默认分支是否正常。
