# -*- coding: utf-8 -*-
"""Region profile helpers for 观澜 / Guanlan."""

from __future__ import annotations

from typing import Optional

from guanlan.config import Config

DEFAULT_PROFILE = "global"
VALID_PROFILES = ("global", "china", "hybrid")


def normalize_profile(profile: Optional[str]) -> str:
    """Return a valid profile name, falling back to the global profile."""
    if not profile:
        return DEFAULT_PROFILE
    value = profile.strip().lower()
    if value not in VALID_PROFILES:
        raise ValueError(f"unknown profile: {profile}")
    return value


def get_profile(config: Config, override: Optional[str] = None) -> str:
    """Resolve the active profile from an override or saved config."""
    if override:
        return normalize_profile(override)
    return normalize_profile(config.get("profile", DEFAULT_PROFILE))


def set_profile(config: Config, profile: str) -> str:
    """Persist a region profile in the user config."""
    value = normalize_profile(profile)
    config.set("profile", value)
    return value
