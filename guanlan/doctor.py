# -*- coding: utf-8 -*-
"""Environment health checker — powered by channels.

Each channel knows how to check itself. Doctor just collects the results.
"""

import os
import re
from contextlib import contextmanager
from typing import Any, Dict

from guanlan.channel_catalog import get_channel_metadata
from guanlan.channels import get_all_channels
from guanlan.config import Config
from guanlan.profiles import get_profile


@contextmanager
def _sensitive_probe_mode(skip_sensitive: bool):
    key = "GUANLAN_SKIP_SENSITIVE_PROBES"
    prev = os.environ.get(key)
    if skip_sensitive:
        os.environ[key] = "1"
    try:
        yield
    finally:
        if prev is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = prev


def check_all(
    config: Config,
    profile: str | None = None,
    skip_sensitive: bool = False,
) -> Dict[str, dict]:
    """Check all channels and return status dict."""
    active_profile = get_profile(config, profile)
    results = {}
    with _sensitive_probe_mode(skip_sensitive):
        for ch in get_all_channels(active_profile):
            status, message = ch.check(config)
            metadata = get_channel_metadata(ch.name)
            readiness = _readiness(status, metadata)
            results[ch.name] = {
                "status": status,
                "name": ch.description,
                "message": message,
                "tier": ch.tier,
                "backends": ch.backends,
                "readiness": readiness,
                "verification": metadata["verification"],
                "stability": metadata["stability"],
                "risk_level": metadata["risk_level"],
                "auth": metadata["auth"],
                "batch": metadata["batch"],
                "category": metadata["category"],
                "expectation": metadata.get("expectation", ""),
            }
    return results


def _readiness(status: str, metadata: dict[str, Any]) -> str:
    """Separate backend presence from end-to-end verification."""
    if status in {"off", "error"}:
        return "unavailable"
    if status == "ok" and metadata.get("verification") == "verified":
        return "verified"
    if status in {"ok", "warn"} and metadata.get("verification") == "unverified":
        return "backend-ready"
    if status in {"ok", "warn"}:
        return "best-effort"
    return "unknown"


_SENSITIVE_KEY_SEGMENTS = {
    "auth",
    "cookie",
    "cookies",
    "key",
    "passwd",
    "password",
    "proxy",
    "secret",
    "session",
    "token",
}

_SENSITIVE_VALUE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("GitHub token", r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    ("OpenAI-style API key", r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    ("Groq API key", r"\bgsk_[A-Za-z0-9_-]{16,}\b"),
    ("Slack token", r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    ("JWT token", r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    ("URL credentials", r"https?://[^/\s:@]+:[^@\s/]+@"),
)


def scan_config(config: Config) -> dict[str, Any]:
    """Scan config.yaml for likely plaintext credentials without revealing values."""
    findings_by_path: dict[str, dict[str, Any]] = {}

    def add_finding(path: str, severity: str, reason: str) -> None:
        finding = findings_by_path.setdefault(
            path,
            {
                "path": path,
                "severity": severity,
                "reasons": [],
            },
        )
        if _severity_rank(severity) > _severity_rank(str(finding["severity"])):
            finding["severity"] = severity
        if reason not in finding["reasons"]:
            finding["reasons"].append(reason)

    def visit(value: Any, path: str, sensitive_context: bool = False) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                key_text = str(key)
                child_path = f"{path}.{key_text}" if path else key_text
                key_sensitive = _looks_sensitive_key(key_text)
                visit(child, child_path, sensitive_context or key_sensitive)
            return
        if isinstance(value, list):
            for idx, child in enumerate(value):
                visit(child, f"{path}[{idx}]", sensitive_context)
            return
        if value in (None, ""):
            return

        text = str(value)
        if sensitive_context:
            add_finding(path, "high", "key name suggests a credential or private endpoint")
        if _looks_like_cookie_header(text):
            add_finding(path, "high", "value looks like a Cookie header")
        for label, pattern in _SENSITIVE_VALUE_PATTERNS:
            if re.search(pattern, text):
                add_finding(path, "high", f"value matches {label} pattern")

    visit(config.data, "")
    return {
        "path": str(config.config_path),
        "exists": config.config_path.exists(),
        "findings": list(findings_by_path.values()),
    }


def format_config_scan(scan: dict[str, Any]) -> str:
    """Format a config scan result without printing sensitive values."""
    try:
        from rich.markup import escape
    except ImportError:
        def escape(value):
            return value

    lines = ["", "[bold cyan]配置安全扫描 / Config Check[/bold cyan]"]
    path = escape(str(scan.get("path") or "~/.guanlan/config.yaml"))
    if not scan.get("exists"):
        lines.append(f"[green]未发现配置文件：{path}[/green]")
        return "\n".join(lines)

    findings = scan.get("findings") or []
    if not findings:
        lines.append(f"[green]未发现明显明文敏感项：{path}[/green]")
        return "\n".join(lines)

    lines.append(f"[bold red][!]  发现 {len(findings)} 个可能的明文敏感配置项[/bold red]")
    lines.append(f"配置文件：{path}")
    for finding in findings:
        item_path = escape(str(finding.get("path") or "<root>"))
        severity = escape(str(finding.get("severity") or "warn"))
        reasons = "；".join(escape(str(reason)) for reason in finding.get("reasons", []))
        lines.append(f"- [{severity}] {item_path}: {reasons}")
    lines.append("建议：不要提交 ~/.guanlan/config.yaml；确认 .gitignore 覆盖本地配置；共享电脑上使用 chmod 600。")
    lines.append("说明：扫描只显示配置路径和风险类型，不输出具体 Cookie、Token 或 Key。")
    return "\n".join(lines)


def _looks_sensitive_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")
    if not normalized:
        return False
    segments = set(normalized.split("_"))
    if segments & _SENSITIVE_KEY_SEGMENTS:
        return True
    return normalized.endswith("_key") or "api_key" in normalized


def _looks_like_cookie_header(value: str) -> bool:
    if ";" not in value or "=" not in value:
        return False
    pairs = re.findall(r"(?:^|;\s*)[A-Za-z0-9_.%-]{2,}=[^;]{3,}", value)
    return len(pairs) >= 2


def _severity_rank(severity: str) -> int:
    return {"info": 0, "warn": 1, "high": 2}.get(severity, 1)


def format_report(results: Dict[str, dict], profile: str | None = None) -> str:
    """Format results as a readable text report (with Rich markup)."""
    try:
        from rich.markup import escape
    except ImportError:
        def escape(value):
            return value

    lines = []
    lines.append("[bold cyan]观澜 / Guanlan 状态[/bold cyan]")
    if profile:
        profile_name = {"global": "全球默认", "china": "中文场景", "hybrid": "混合"}.get(
            profile, profile
        )
        lines.append(f"[cyan]Profile: {escape(profile_name)}[/cyan]")
    lines.append("[cyan]" + "=" * 40 + "[/cyan]")

    ok_count = sum(1 for r in results.values() if r["status"] == "ok")
    total = len(results)

    # Tier 0 — zero config
    lines.append("")
    lines.append("[bold]✅ 装好即用：[/bold]")
    for key, r in results.items():
        if r["tier"] == 0:
            name_msg = (
                f"[bold]{escape(r['name'])}[/bold] "
                f"[dim]{escape(_status_label(r))}[/dim] — {escape(r['message'])}"
            )
            if r["status"] == "ok":
                lines.append(f"  [green]✅[/green] {name_msg}")
            elif r["status"] == "warn":
                lines.append(f"  [yellow][!][/yellow]  {name_msg}")
            elif r["status"] in ("off", "error"):
                lines.append(f"  [red][X][/red]  {name_msg}")

    # Tier 1 — needs free key / login
    tier1 = {k: r for k, r in results.items() if r["tier"] == 1}
    tier1_active = {k: r for k, r in tier1.items() if r["status"] == "ok"}
    tier1_inactive = {k: r for k, r in tier1.items() if r["status"] != "ok"}
    if tier1_active:
        lines.append("")
        lines.append("[bold]可选渠道（已安装）：[/bold]")
        for key, r in tier1_active.items():
            name_msg = (
                f"[bold]{escape(r['name'])}[/bold] "
                f"[dim]{escape(_status_label(r))}[/dim] — {escape(r['message'])}"
            )
            lines.append(f"  [green]✅[/green] {name_msg}")

    # Tier 2 — optional complex setup
    tier2 = {k: r for k, r in results.items() if r["tier"] == 2}
    tier2_active = {k: r for k, r in tier2.items() if r["status"] == "ok"}
    tier2_inactive = {k: r for k, r in tier2.items() if r["status"] != "ok"}
    if tier2_active:
        if not tier1_active:
            lines.append("")
            lines.append("[bold]可选渠道（已安装）：[/bold]")
        for key, r in tier2_active.items():
            name_msg = (
                f"[bold]{escape(r['name'])}[/bold] "
                f"[dim]{escape(_status_label(r))}[/dim] — {escape(r['message'])}"
            )
            lines.append(f"  [green]✅[/green] {name_msg}")

    lines.append("")
    status_color = "green" if ok_count == total else ("yellow" if ok_count > 0 else "red")
    lines.append(f"状态：[{status_color}]{ok_count}/{total}[/{status_color}] 个渠道可用")

    # Summarize inactive optional channels in one line instead of listing each
    all_inactive = list(tier1_inactive.values()) + list(tier2_inactive.values())
    if all_inactive:
        names = [r["name"] for r in all_inactive]
        lines.append(
            f"还有 {len(names)} 个可选渠道可以解锁（{'、'.join(names)}），"
            "告诉你的 Agent「帮我装 XXX」即可"
        )

    # Security check: config file permissions (Unix only)
    import stat
    import sys

    config_path = Config.CONFIG_DIR / "config.yaml"
    if config_path.exists() and sys.platform != "win32":
        try:
            mode = config_path.stat().st_mode
            if mode & (stat.S_IRGRP | stat.S_IROTH):
                lines.append("")
                lines.append(
                    "[bold red][!]  安全提示：config.yaml 权限过宽（其他用户可读）[/bold red]"
                )
                lines.append("   修复：chmod 600 ~/.guanlan/config.yaml")
        except OSError:
            pass

    return "\n".join(lines)


def _status_label(result: dict[str, Any]) -> str:
    return (
        f"{result.get('readiness', 'unknown')}/"
        f"{result.get('verification', 'unverified')}/"
        f"{result.get('stability', 'best-effort')}"
    )


def format_trace(results: Dict[str, dict], skip_sensitive: bool = True) -> str:
    """Format a compact diagnostic trace for channel checks."""
    try:
        from rich.markup import escape
    except ImportError:
        def escape(value):
            return value

    probe_mode = "skipped" if skip_sensitive else "enabled"
    probe_label = "已跳过" if skip_sensitive else "已启用"
    lines = [
        "",
        "[bold cyan]诊断追踪 / Trace[/bold cyan]",
        f"敏感探测: {probe_mode}（{probe_label}认证、Cookie 与登录态深度检查）",
    ]

    for key, r in results.items():
        backends = ", ".join(r.get("backends") or []) or "-"
        lines.append(
            "- "
            f"{escape(key)}: "
            f"status={escape(str(r.get('status', 'unknown')))}, "
            f"readiness={escape(str(r.get('readiness', 'unknown')))}, "
            f"verification={escape(str(r.get('verification', 'unverified')))}, "
            f"stability={escape(str(r.get('stability', 'best-effort')))}, "
            f"risk={escape(str(r.get('risk_level', 'medium')))}, "
            f"auth={escape(str(r.get('auth', 'unknown')))}, "
            f"batch={escape(str(r.get('batch', 'limited')))}, "
            f"tier={escape(str(r.get('tier', '-')))}, "
            f"backends={escape(backends)}"
        )

    return "\n".join(lines)
