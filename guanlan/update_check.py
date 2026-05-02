# -*- coding: utf-8 -*-
"""Best-effort update checks for Guanlan.

Update checks must never block core search/read workflows. They are used only
by human-facing entrypoints such as welcome, doctor, and check-update.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
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
            "建议先做全量更新，再配置 MCP、可选渠道或登录态。不要混用旧的全局 guanlan：",
            "  uv tool install --force --upgrade guanlan",
            "  # uv 必须带 --upgrade；只有 --force 可能重装旧锁定版本。",
            "  # 如果使用 Homebrew：",
            "  brew update && brew reinstall shenyangs/tap/guanlan",
            "  # 如果使用 pipx：",
            "  pipx install --force guanlan",
            "  hash -r  # 如果 shell 支持",
            "  command -v guanlan",
            "  which -a guanlan",
            "  guanlan version",
            "  guanlan capabilities",
            "  guanlan doctor --trace",
            "  guanlan search \"人工智能 政策\" --profile china --limit 5 --trace",
            "  guanlan hotnews today --limit 5 --trends",
            "如果版本号或路径不对，请停止配置 MCP；Homebrew 仍然装到旧版时，临时使用 uv 路径。",
        ]
    )


def run_install_check(
    current: str,
    *,
    latest: str | None = None,
    command_path: str | None = None,
    all_paths: list[str] | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, object]:
    """Inspect the active CLI install path and common version-drift risks.

    This is deliberately read-only. It does not install, upgrade, or inspect
    credentials; it only explains whether the shell is likely to call the same
    Guanlan version the user thinks they installed.
    """
    resolved_path = command_path if command_path is not None else shutil.which("guanlan")
    resolved_paths = all_paths if all_paths is not None else _all_command_paths("guanlan")
    latest_version = latest if latest is not None else latest_pypi_version(timeout=timeout)
    stale = bool(latest_version and is_newer_version(latest_version, current))
    multiple_paths = len(_unique_paths(resolved_paths)) > 1
    executable = bool(resolved_path)
    status = "ok"
    if not executable or stale:
        status = "fail"
    elif multiple_paths:
        status = "warn"

    recommendations: list[str] = []
    if not executable:
        recommendations.append("当前 shell 找不到 guanlan，请重新安装或检查 PATH。")
    if stale:
        recommendations.append(
            f"当前 v{current} 低于公开最新 v{latest_version}，先升级再配置 MCP 或可选渠道。"
        )
    if multiple_paths:
        recommendations.append("发现多个 guanlan 路径，可能存在 pipx/Homebrew/uv 混装导致的旧版本优先。")
    if not recommendations:
        recommendations.append("安装路径和版本未发现明显风险，可以继续配置 MCP 或 Agent。")

    return {
        "status": status,
        "current_version": current,
        "latest_version": latest_version or "",
        "command_path": resolved_path or "",
        "all_paths": _unique_paths(resolved_paths),
        "path_count": len(_unique_paths(resolved_paths)),
        "python": sys.executable,
        "stale": stale,
        "multiple_paths": multiple_paths,
        "recommendations": recommendations,
    }


def format_install_check(report: dict[str, object]) -> str:
    """Render install self-check output as Markdown."""
    lines = [
        "# 观澜安装自检",
        "",
        f"- 状态: {report.get('status', 'unknown')}",
        f"- 当前版本: v{report.get('current_version', '')}",
        f"- 公开最新: v{report.get('latest_version', '') or '未知'}",
        f"- 命令路径: {report.get('command_path', '') or '未找到'}",
        f"- Python: {report.get('python', '')}",
    ]
    paths = report.get("all_paths") or []
    if isinstance(paths, list) and paths:
        lines.extend(["", "## PATH 中的 guanlan"])
        for path in paths:
            lines.append(f"- {path}")
    lines.extend(["", "## 建议"])
    for item in report.get("recommendations") or []:
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## 常用修复命令",
            "```bash",
            "guanlan version",
            "which -a guanlan",
            "uv tool install --force --upgrade guanlan",
            "brew update && brew reinstall shenyangs/tap/guanlan",
            "pipx install --force guanlan",
            "hash -r",
            "```",
        ]
    )
    return "\n".join(lines)


def _all_command_paths(command: str) -> list[str]:
    executable = "where" if os.name == "nt" else "which"
    args = [executable, command] if os.name == "nt" else [executable, "-a", command]
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=2,
            check=False,
        )
    except Exception:
        found = shutil.which(command)
        return [found] if found else []
    return [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]


def _unique_paths(paths: list[str] | None) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for path in paths or []:
        normalized = os.path.realpath(path)
        if normalized in seen:
            continue
        seen.add(normalized)
        output.append(path)
    return output
