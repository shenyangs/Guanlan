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
