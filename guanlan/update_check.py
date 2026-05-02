# -*- coding: utf-8 -*-
"""Best-effort update checks for Guanlan.

Update checks must never block core search/read workflows. They are used only
by human-facing entrypoints such as welcome, doctor, and check-update.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

import requests

PYPI_JSON_URL = "https://pypi.org/pypi/guanlan/json"
DEFAULT_TIMEOUT_SECONDS = 1.2


@dataclass(frozen=True)
class UpdateInfo:
    current: str
    latest: str
    source: str = "PyPI"


def _version_key(version: str) -> tuple[int, ...]:
    """Return a lightweight comparable key for public semver-ish versions."""
    parts = re.findall(r"\d+", version or "")
    if not parts:
        return (0,)
    return tuple(int(part) for part in parts[:4])


def is_newer_version(latest: str, current: str) -> bool:
    """Return whether latest appears newer than current."""
    return _version_key(latest) > _version_key(current)


def update_checks_enabled() -> bool:
    """Return whether background-safe update checks should run."""
    raw = os.environ.get("GUANLAN_UPDATE_CHECK", "").strip().lower()
    if raw in {"0", "false", "no", "off"}:
        return False
    # Keep tests deterministic unless a test explicitly opts in.
    if os.environ.get("PYTEST_CURRENT_TEST") and raw not in {"1", "true", "yes", "on"}:
        return False
    return True


def latest_pypi_version(timeout: float = DEFAULT_TIMEOUT_SECONDS) -> str | None:
    """Fetch the latest Guanlan version from PyPI. Return None on failure."""
    if not update_checks_enabled():
        return None
    try:
        resp = requests.get(PYPI_JSON_URL, timeout=timeout)
        if resp.status_code != 200:
            return None
        data = resp.json()
        latest = str(data.get("info", {}).get("version", "")).strip()
        return latest or None
    except Exception:
        return None


def get_update_info(current: str, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> UpdateInfo | None:
    """Return update info when a newer public version is available."""
    latest = latest_pypi_version(timeout=timeout)
    if latest and is_newer_version(latest, current):
        return UpdateInfo(current=current, latest=latest)
    return None


def format_update_notice(info: UpdateInfo) -> str:
    """Render a compact, copyable update notice."""
    return "\n".join(
        [
            f"版本提醒：当前 v{info.current}，{info.source} 最新 v{info.latest}。",
            "建议先升级再配置 MCP、可选渠道或登录态：",
            "  uv tool install --force guanlan",
            "  # 如果使用 Homebrew：",
            "  brew update && brew reinstall shenyangs/tap/guanlan",
            "  guanlan version",
            "如果 Homebrew 仍然装到旧版，请临时使用 uv 路径。",
        ]
    )
