# -*- coding: utf-8 -*-
"""Experimental plugin registry for read-only Guanlan search backends."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from guanlan.config import Config


def list_plugins(config: Config | None = None) -> dict[str, Any]:
    """Return registered experimental read-only plugin backends."""
    cfg = config or Config()
    backends = cfg.get("backends", {}) or {}
    return {
        name: value for name, value in backends.items()
        if isinstance(value, dict) and value.get("type") == "plugin"
    } if isinstance(backends, dict) else {}


def register_plugin(name: str, path: str, config: Config | None = None) -> dict[str, Any]:
    """Register a local experimental script as `guanlan search --backend plugin:name`."""
    clean_name = _clean_name(name)
    script = Path(path).expanduser()
    if not script.is_file():
        raise ValueError(f"plugin backend path does not exist: {script}")
    cfg = config or Config()
    backends = cfg.get("backends", {}) or {}
    if not isinstance(backends, dict):
        backends = {}
    backends[clean_name] = {
        "type": "plugin",
        "path": str(script),
        "mode": "read-only",
        "stability": "experimental",
        "contract": "script query limit -> JSON array or {'results': [...]}",
    }
    cfg.set("backends", backends)
    return {clean_name: backends[clean_name]}


def plugin_template(name: str = "my_company_api") -> str:
    """Return a minimal experimental read-only enterprise connector template."""
    clean_name = _clean_name(name)
    return f'''# -*- coding: utf-8 -*-
"""Experimental read-only Guanlan plugin backend: {clean_name}.

Contract:
    python {clean_name}.py "query" 50

Return JSON array or {{"results": [...]}} with title/url/snippet fields.
Do not write, mutate, post, comment, or read browser cookies here.
"""

import json
import sys


def search(query: str, limit: int) -> list[dict]:
    # Replace this with your internal read-only API call.
    return [
        {{
            "title": f"Internal result for {{query}}",
            "url": "https://internal.example/search",
            "snippet": "Read-only enterprise connector placeholder.",
        }}
    ][:limit]


if __name__ == "__main__":
    query = sys.argv[1] if len(sys.argv) > 1 else ""
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    print(json.dumps({{"results": search(query, limit)}}, ensure_ascii=False))
'''


def _clean_name(name: str) -> str:
    clean = (name or "").strip().lower().replace(" ", "_")
    if not clean:
        raise ValueError("plugin name is required")
    if not all(ch.isalnum() or ch in {"_", "-"} for ch in clean):
        raise ValueError("plugin name may only contain letters, numbers, underscore, or dash")
    return clean
