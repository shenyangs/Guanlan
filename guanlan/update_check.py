# -*- coding: utf-8 -*-
"""Best-effort update checks for Guanlan.

Update checks must never block core search/read workflows. They are used only
by human-facing entrypoints such as welcome, doctor, and check-update.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import requests

PYPI_JSON_URL = "https://pypi.org/pypi/guanlan/json"
PYPI_SIMPLE_URL = "https://pypi.org/simple/guanlan/"
DEFAULT_TIMEOUT_SECONDS = 1.2
DEFAULT_CACHE_TTL_SECONDS = 24 * 60 * 60


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


def _highest_version(versions: list[str]) -> str | None:
    cleaned = [version.strip().lstrip("v") for version in versions if version and version.strip()]
    if not cleaned:
        return None
    return max(cleaned, key=_version_key)


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


def latest_pypi_json_version(timeout: float = DEFAULT_TIMEOUT_SECONDS) -> str | None:
    """Fetch the latest Guanlan version from PyPI JSON. Return None on failure."""
    if not update_checks_enabled():
        return None
    try:
        resp = requests.get(PYPI_JSON_URL, headers=_no_cache_headers(), timeout=timeout)
        if resp.status_code != 200:
            return None
        data = resp.json()
        latest = str(data.get("info", {}).get("version", "")).strip()
        return latest or None
    except Exception:
        return None


def latest_pypi_simple_version(timeout: float = DEFAULT_TIMEOUT_SECONDS) -> str | None:
    """Fetch the highest Guanlan version visible in the PyPI simple index."""
    if not update_checks_enabled():
        return None
    try:
        resp = requests.get(PYPI_SIMPLE_URL, headers=_no_cache_headers(), timeout=timeout)
        if resp.status_code != 200:
            return None
        versions = re.findall(r"guanlan-([0-9][A-Za-z0-9.]*)(?:-py3-none-any\.whl|\.tar\.gz)", resp.text or "")
        return _highest_version(versions)
    except Exception:
        return None


def latest_pypi_version(timeout: float = DEFAULT_TIMEOUT_SECONDS) -> str | None:
    """Fetch the latest Guanlan version from PyPI release surfaces.

    PyPI JSON is the primary source, but the simple index is the source pip/uv
    resolve from. Taking the highest visible version avoids stale JSON/cache
    reads or fragile HTML snippets being mistaken for the current public latest.
    """
    per_surface_timeout = _per_surface_timeout(timeout)
    json_latest = latest_pypi_json_version(timeout=per_surface_timeout)
    simple_latest = latest_pypi_simple_version(timeout=per_surface_timeout)
    return _highest_version([item for item in [json_latest, simple_latest] if item])


def pypi_version_surfaces(timeout: float = DEFAULT_TIMEOUT_SECONDS) -> dict[str, str]:
    """Return a small public-version report for humans and agents."""
    per_surface_timeout = _per_surface_timeout(timeout)
    json_latest = latest_pypi_json_version(timeout=per_surface_timeout)
    simple_latest = latest_pypi_simple_version(timeout=per_surface_timeout)
    latest = _highest_version([item for item in [json_latest, simple_latest] if item])
    return {
        "pypi_json": json_latest or "",
        "pypi_simple": simple_latest or "",
        "latest": latest or "",
    }


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
            "  rm -f ~/.guanlan/cache/update-check.json",
            "  uv tool install --force --upgrade --refresh --default-index https://pypi.org/simple guanlan",
            "  # uv 必须带 --upgrade 和 --refresh；只有 --force 可能重装旧锁定版本。",
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


def format_compact_update_notice(info: UpdateInfo) -> str:
    """Render a short stderr-safe update notice for routine commands."""
    return "\n".join(
        [
            f"版本提醒：当前 v{info.current}，{info.source} 最新 v{info.latest}。",
            "建议更新：uv tool install --force --upgrade --refresh --default-index https://pypi.org/simple guanlan",
            "可运行 `guanlan doctor --install-check` 检查路径和版本漂移。",
        ]
    )


def cached_update_info(
    current: str,
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ttl_seconds: int | None = None,
) -> UpdateInfo | None:
    """Return update info using a small local cache to avoid per-command latency."""
    if not update_checks_enabled():
        return None
    ttl = _cache_ttl_seconds(ttl_seconds)
    cached = _load_update_cache()
    now = time.time()
    cached_latest = str((cached or {}).get("latest") or "").strip()
    cached_source = str((cached or {}).get("source") or "PyPI")
    checked_at = float((cached or {}).get("checked_at") or 0)
    if cached and checked_at > 0 and now - checked_at <= ttl:
        if cached_latest and is_newer_version(cached_latest, current):
            return UpdateInfo(current=current, latest=cached_latest, source=cached_source)
        return None

    latest = latest_pypi_version(timeout=timeout)
    _save_update_cache(latest, source="PyPI", checked_at=now)
    if latest and is_newer_version(latest, current):
        return UpdateInfo(current=current, latest=latest, source="PyPI")
    if latest is None and cached_latest and is_newer_version(cached_latest, current):
        return UpdateInfo(current=current, latest=cached_latest, source=cached_source)
    return None


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
    unique_paths = _unique_paths(resolved_paths)
    latest_version = latest if latest is not None else latest_pypi_version(timeout=timeout)
    stale = bool(latest_version and is_newer_version(latest_version, current))
    multiple_paths = len(unique_paths) > 1
    executable = bool(resolved_path)
    path_details = _path_details(unique_paths, active_path=resolved_path or "", timeout=min(timeout, 1.0))
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
        recommendations.append(f"当前 shell 优先调用：{resolved_path or unique_paths[0]}。")
        recommendations.append("发现多个 guanlan 路径，可能存在 pipx/Homebrew/uv 混装导致的旧版本优先。")
        shadowed = [
            str(item.get("path"))
            for item in path_details
            if item.get("shadowed_by")
        ]
        if shadowed:
            recommendations.append("以下安装入口被 PATH 前面的 guanlan shadow：" + "、".join(shadowed))
        stale_paths = [
            str(item.get("path"))
            for item in path_details
            if item.get("version") and latest_version and is_newer_version(str(latest_version), str(item.get("version")))
        ]
        if stale_paths:
            recommendations.append("以下路径看起来不是公开最新版本：" + "、".join(stale_paths))
        recommendations.append("升级后运行 `hash -r`，再核对 `command -v guanlan`、`which -a guanlan`、`guanlan version`。")
        recommendations.append("建议只保留一个主安装入口；若 Homebrew 滞后，先切到 `uv tool install --force --upgrade --refresh --default-index https://pypi.org/simple guanlan`。")
    if not recommendations:
        recommendations.append("安装路径和版本未发现明显风险，可以继续配置 MCP 或 Agent。")

    return {
        "status": status,
        "current_version": current,
        "latest_version": latest_version or "",
        "command_path": resolved_path or "",
        "all_paths": unique_paths,
        "path_count": len(unique_paths),
        "path_details": path_details,
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
        details = report.get("path_details") or []
        if isinstance(details, list) and details:
            for item in details:
                marker = " <= 当前优先" if item.get("active") else ""
                version = item.get("version") or "未知"
                source = item.get("source_hint") or "unknown"
                risk = item.get("risk") or ""
                if item.get("shadowed_by"):
                    shadow_risk = f"被 {item.get('shadowed_by')} shadow"
                    risk = shadow_risk if not risk else f"{risk}；{shadow_risk}"
                suffix = f"；{risk}" if risk else ""
                lines.append(f"- {item.get('path')}{marker}（版本: {version}；来源: {source}{suffix}）")
        else:
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
            "rm -f ~/.guanlan/cache/update-check.json",
            "uv tool install --force --upgrade --refresh --default-index https://pypi.org/simple guanlan",
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


def _path_details(paths: list[str], *, active_path: str = "", timeout: float = 1.0) -> list[dict[str, object]]:
    active_real = os.path.realpath(active_path) if active_path else ""
    details: list[dict[str, object]] = []
    for path in paths:
        version, error = _path_version(path, timeout=timeout)
        details.append(
            {
                "path": path,
                "active": bool(active_real and os.path.realpath(path) == active_real),
                "version": version,
                "version_error": error,
                "source_hint": _install_source_hint(path),
                "shadowed_by": _shadowing_path(path, paths, active_real=active_real),
                "risk": _path_risk(path, active_real=active_real, version=version, error=error),
            }
        )
    return details


def _path_version(path: str, *, timeout: float = 1.0) -> tuple[str, str]:
    if not path:
        return "", "path_empty"
    try:
        result = subprocess.run(
            [path, "version"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(timeout, 0.2),
            check=False,
        )
    except Exception as exc:
        return "", type(exc).__name__
    if result.returncode != 0:
        return "", (result.stderr or f"exit={result.returncode}").strip()[:120]
    match = re.search(r"v?(\d+(?:\.\d+){1,3}[A-Za-z0-9.-]*)", result.stdout or "")
    return (match.group(1) if match else "", "" if match else "version_not_found")


def _install_source_hint(path: str) -> str:
    normalized = path.lower()
    if "homebrew" in normalized or normalized.startswith("/opt/homebrew/") or normalized.startswith("/usr/local/cellar/"):
        return "homebrew"
    if "pipx" in normalized:
        return "pipx"
    if ".local/bin" in normalized or ".local/share/uv" in normalized or "/uv/tools/" in normalized:
        return "uv_or_user_local"
    if ".venv" in normalized:
        return "project_venv"
    return "path"


def _path_risk(path: str, *, active_real: str, version: str, error: str) -> str:
    if error:
        return f"版本探测失败: {error}"
    if active_real and os.path.realpath(path) != active_real:
        return "非当前优先路径"
    if not version:
        return "未识别版本"
    return ""


def _shadowing_path(path: str, paths: list[str], *, active_real: str) -> str:
    if not active_real:
        return ""
    current_real = os.path.realpath(path)
    if current_real == active_real:
        return ""
    for candidate in paths:
        candidate_real = os.path.realpath(candidate)
        if candidate_real == current_real:
            return ""
        if candidate_real == active_real:
            return candidate
    return ""


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


def _cache_ttl_seconds(ttl_seconds: int | None = None) -> int:
    if ttl_seconds is not None:
        return max(int(ttl_seconds), 0)
    raw = os.environ.get("GUANLAN_UPDATE_CHECK_TTL_SECONDS", "").strip()
    if raw:
        try:
            return max(int(raw), 0)
        except ValueError:
            return DEFAULT_CACHE_TTL_SECONDS
    return DEFAULT_CACHE_TTL_SECONDS


def _no_cache_headers() -> dict[str, str]:
    return {
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "User-Agent": "guanlan-update-check",
    }


def _per_surface_timeout(timeout: float) -> float:
    try:
        return max(float(timeout) / 2, 0.2)
    except Exception:
        return DEFAULT_TIMEOUT_SECONDS / 2


def _update_cache_path() -> Path:
    raw = os.environ.get("GUANLAN_UPDATE_CHECK_CACHE", "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".guanlan" / "cache" / "update-check.json"


def _load_update_cache() -> dict[str, object] | None:
    path = _update_cache_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _save_update_cache(latest: str | None, *, source: str, checked_at: float) -> None:
    path = _update_cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "checked_at": checked_at,
            "latest": latest or "",
            "source": source,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        return
