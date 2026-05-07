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
- 提交信息和 GitHub Release note 中文优先；commit 可保留 `feat/fix/docs/test/refactor/chore:` 前缀，但冒号后使用中文说明，例如 `feat: 扩展垂直路由和搜索质量反馈`。

流程：

1. 更新版本号，例如 `0.5.0 -> 0.5.1`。
2. 更新 `CHANGELOG.md`。
3. 运行完整本地发布闸门：`scripts/release_gate.sh`。它会先执行 `scripts/pre_release_status.sh`，确认版本、changelog、文档版本和工作区状态没有漂移；随后依次执行 `ruff`、全量 `pytest`、`guanlan quality foundational`、`guanlan quality coverage`、`guanlan quality regression`、`guanlan quality robustness`、`guanlan quality backend-fixtures`、`guanlan quality performance`、`guanlan eval benchmark`、`guanlan eval suite run chinese-web-v1`、`uv build`、安装 smoke 和版本核对。
4. 如果 `pre_release_status` 报告存在未提交文件，先判断这些文件是否属于本次发版；不要自动 revert 其他进程改动，也不要把未知半成品混入 release。只有本地诊断需要临时放行时，才使用 `GUANLAN_RELEASE_ALLOW_DIRTY=1 scripts/pre_release_status.sh`，正式发版不得依赖该放行。
5. 提交代码。
6. 使用发布脚本推送 `main` 并创建同版本 tag：

```bash
scripts/publish_release.sh
```

如果只想做本地诊断而不跑完整闸门，可以临时使用 `GUANLAN_RELEASE_SKIP_GATE=1 scripts/publish_release.sh`；正式发布不要跳过完整闸门。

7. `scripts/publish_release.sh` 推送成功后会自动执行 `scripts/post_release_sync.sh`，默认完成以下同步动作：
   - 轮询 GitHub `release-pypi` workflow（tag 分支）直到成功。
   - 轮询 PyPI，确认目标版本已可见。
   - 轮询 Homebrew tap 公式，确认已指向目标版本 tarball。
   - 默认执行官网部署脚本并校验站点版本。
   - 自动刷新本机 `uv` / `brew` / `pipx` 安装并核验 `which -a guanlan` 下的所有可执行入口版本（`uv` 默认携带 `--refresh --index-url https://pypi.org/simple`，降低索引滞后导致的旧版回装）。
8. 等待 `release` workflow 完成：
   - Job `publish-pypi`：发布到 PyPI。
   - Job `update-homebrew-tap`：更新 tap 仓库公式，并从 tap 真实安装一次确认版本。

注意：PyPI 发布由 `v*` tag 触发。只推 `main` 不会发布 PyPI，也不会让 `uv tool install --upgrade guanlan` 拿到新版本。

## 同步开关

- `GUANLAN_RELEASE_SKIP_SYNC=1`：跳过 `publish_release` 里的发布后同步步骤（仅用于紧急场景）。
- `GUANLAN_RELEASE_DEPLOY_WEBSITE=0`：跳过官网部署，但仍会做站点版本校验。
- `GUANLAN_SYNC_LOCAL_INSTALLS=0`：跳过本机 `uv/brew/pipx` 刷新，仅做分发就绪校验。
- `GUANLAN_SYNC_SKIP_DISTRIBUTION_WAIT=1`：跳过 GitHub/PyPI/Homebrew 轮询等待。
- `GUANLAN_RELEASE_SITE_URL=...`：自定义官网版本校验地址（默认 `http://101.37.70.222`）。
- `GUANLAN_RELEASE_WORKFLOW_PATH=...`：自定义发布工作流路径（默认 `.github/workflows/release-pypi.yml`）。

## 用户安装方式

PyPI：

```bash
uv tool install guanlan
```

Homebrew：

```bash
brew update
brew tap shenyangs/tap
brew reinstall shenyangs/tap/guanlan
guanlan version
```

如果 Homebrew 安装出的版本低于本次 tag，说明 tap 没同步或用户本地 tap 缓存滞后。不要把这类结果当作成功安装；先刷新 tap，仍失败时临时建议用户使用 PyPI/uv。

## 故障排查

- `publish-pypi` 失败：
  - 检查 PyPI Trusted Publisher 配置中的 repo/workflow/environment 是否完全匹配。
- `update-homebrew-tap` 失败：
  - 检查 `HOMEBREW_TAP_GITHUB_TOKEN` 是否有效，且对 `homebrew-tap` 具有写权限。
  - 检查 `shenyangs/homebrew-tap` 是否存在、默认分支是否正常。
  - 检查 workflow 末尾的 Homebrew 真实安装验证；它会捕捉“公式提交成功但用户实际装到旧版本”的问题。
