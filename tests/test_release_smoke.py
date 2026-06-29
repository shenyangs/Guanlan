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
    assert "returned unknown version" in script
    assert "guanlan doctor --install-check || true" not in script


def test_publish_release_skip_sync_does_not_claim_complete_release():
    script = (ROOT / "scripts" / "publish_release.sh").read_text(encoding="utf-8")

    assert "push/tag complete; release sync skipped" in script
    assert "release incomplete: GUANLAN_RELEASE_SKIP_SYNC=1" in script


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
