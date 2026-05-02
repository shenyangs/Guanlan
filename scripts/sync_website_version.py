#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sync website footer version from pyproject.toml."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
INDEX_HTML = ROOT / "website" / "index.html"


def read_project_version() -> str:
    content = PYPROJECT.read_text(encoding="utf-8")
    match = re.search(r'(?m)^version\s*=\s*"([^"]+)"\s*$', content)
    if not match:
        raise RuntimeError("version not found in pyproject.toml")
    return match.group(1).strip()


def sync_footer(version: str) -> bool:
    content = INDEX_HTML.read_text(encoding="utf-8")
    updated = re.sub(
        r"(?m)(<span>\s*Guanlan v)([^<]+)(</span>)",
        rf"\g<1>{version}\3",
        content,
    )
    if updated == content:
        return False
    INDEX_HTML.write_text(updated, encoding="utf-8")
    return True


def main() -> None:
    version = read_project_version()
    changed = sync_footer(version)
    status = "updated" if changed else "already"
    print(f"[sync-website-version] {status}: Guanlan v{version}")


if __name__ == "__main__":
    main()
