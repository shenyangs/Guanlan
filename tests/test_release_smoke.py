# -*- coding: utf-8 -*-
"""Release smoke guards for package metadata and install scripts."""

import pathlib
import re

import guanlan

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_pyproject_version_matches_runtime_version():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'(?m)^version = "([^"]+)"$', pyproject)

    assert match is not None
    assert match.group(1) == guanlan.__version__


def test_console_scripts_are_declared():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert 'guanlan = "guanlan.cli:main"' in pyproject
    assert 'guanlan-mcp = "guanlan.integrations.mcp_server:cli_main"' in pyproject


def test_release_smoke_script_covers_install_paths():
    script = (ROOT / "scripts" / "release_smoke.sh").read_text(encoding="utf-8")

    assert "pip install" in script
    assert "pipx install" in script
    assert "guanlan\" --version" in script
    assert "install --env=auto" in script
    assert "guanlan\" status" in script


def test_release_gate_runs_full_quality_ladder():
    script = (ROOT / "scripts" / "release_gate.sh").read_text(encoding="utf-8")

    assert "ruff check" in script
    assert "pytest -q" in script
    assert "quality coverage" in script
    assert "quality regression" in script
    assert "quality robustness" in script
    assert "eval benchmark" in script
    assert "uv build" in script
    assert "release_smoke.sh" in script
    assert "guanlan version" in script


def test_pre_release_status_checks_security_supported_line():
    script = (ROOT / "scripts" / "pre_release_status.sh").read_text(encoding="utf-8")

    assert "SECURITY.md" in script
    assert "supported_line" in script
    assert "Latest $supported_line" in script


def test_post_release_sync_script_handles_github_rate_limit_and_uv_version_verification():
    script = (ROOT / "scripts" / "post_release_sync.sh").read_text(encoding="utf-8")

    assert "HTTP_STATUS:%{http_code}" in script
    assert "github workflow probe hit API 403/rate-limit" in script
    assert "uv tool install --force --upgrade --reinstall-package guanlan" in script
    assert "--no-sources --default-index https://pypi.org/simple guanlan" in script
    assert "uv tool path resolved v" in script
    assert "verify_single_bin_version \"uv tool\"" in script
    assert "https://guanlan.xin/" in script
    assert "https://www.guanlan.xin/" in script
    assert "http://101.37.70.222/" in script
    assert "source_deployed_but_public_site_blocked" in script
    assert "release incomplete: source-only website validation used" in script
    assert "GUANLAN_RELEASE_SKIP_WEBSITE" in script
    assert "website deploy and version checks skipped" in script
    assert "returned unknown version" in script
    assert "guanlan doctor --install-check || true" not in script


def test_publish_release_skip_sync_does_not_claim_complete_release():
    script = (ROOT / "scripts" / "publish_release.sh").read_text(encoding="utf-8")

    assert "push/tag complete; release sync skipped" in script
    assert "release incomplete: GUANLAN_RELEASE_SKIP_SYNC=1" in script


def test_quality_gate_workflow_runs_full_release_quality_ladder():
    workflow = (ROOT / ".github" / "workflows" / "quality-gate.yml").read_text(encoding="utf-8")

    assert "scripts/pre_release_status.sh" in workflow
    assert "ruff check ." in workflow
    assert "pytest -q" in workflow
    assert "quality foundational" in workflow
    assert "quality coverage" in workflow
    assert "quality regression" in workflow
    assert "quality robustness" in workflow
    assert "quality backend-fixtures" in workflow
    assert "eval benchmark" in workflow
    assert "eval suite run chinese-web-v1" in workflow
    assert "uv build" in workflow
    assert "scripts/generate_quality_report.py" in workflow
    assert "scripts/reliability_guard.py" in workflow


def test_release_workflow_captures_distribution_status_artifact():
    workflow = (ROOT / ".github" / "workflows" / "release-pypi.yml").read_text(encoding="utf-8")

    assert "scripts/pre_release_status.sh" in workflow
    assert "scripts/distribution_status.py" in workflow
    assert "distribution-status.json" in workflow
    assert "distribution-status.md" in workflow
    assert "actions/upload-artifact" in workflow


def test_release_workflow_runs_the_same_quality_gate_before_building():
    workflow = (ROOT / ".github" / "workflows" / "release-pypi.yml").read_text(encoding="utf-8")

    assert "needs: quality" in workflow
    assert "scripts/release_gate.sh" in workflow
    assert "scripts/generate_quality_report.py" in workflow
    assert "name: quality-report" in workflow


def test_deploy_script_validates_before_switching_and_can_restore_previous_release():
    script = (ROOT / "scripts" / "deploy_website_ecs.sh").read_text(encoding="utf-8")

    assert "ConnectTimeout=12" in script
    assert "Cloud Assistant fallback" in script
    assert "deploy_website_cloud_assistant.py" in script
    assert "GUANLAN_ALIYUN_ACCESS_KEY_SECRET" in script
    assert '"$ARCHIVE" "$TARGET":/tmp/guanlan-site.tar.gz || return 1' in script
    assert "server-side deployment succeeded, but this machine could not probe the public IP" in script
    assert "scripts/post_release_sync.sh ${VERSION}" in script
    assert 'test -s "$release/index.html"' in script
    assert "previous=" in script
    assert "if ! systemctl reload nginx; then" in script


def test_security_doc_supported_line_matches_current_minor():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'(?m)^version = "([0-9]+)\.([0-9]+)\.[0-9]+"$', pyproject)
    security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")

    assert match is not None
    assert f"Latest {match.group(1)}.{match.group(2)}.x" in security


def test_agent_update_docs_require_full_reinstall_and_smoke():
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    update_doc = (ROOT / "docs" / "update.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    combined = "\n".join([agents, update_doc, readme])

    assert "uv tool install --force --upgrade --refresh --default-index https://pypi.org/simple guanlan" in combined
    assert "只写 `uv tool install --force guanlan`" in combined or "only --force" in combined
    assert "brew reinstall shenyangs/tap/guanlan" in combined
    assert "pipx install --force guanlan" in combined
    assert "which -a guanlan" in combined
    assert 'guanlan search "人工智能 政策" --profile china --limit 5 --trace' in combined
    assert "guanlan hotnews today --limit 5 --trends" in combined
