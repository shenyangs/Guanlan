# Source Attribution / 开源来源说明

Guanlan is released under the MIT License. This file centralizes third-party
notices for open-source projects that informed Guanlan's design, code, adapters,
or source-routing model.

## Guanlan

- Project: Guanlan
- License: MIT License
- Copyright: Copyright (c) 2026 Guanlan Team
- License file: [LICENSE](../LICENSE)

## Agent-Reach

- Project: Agent-Reach
- Role in Guanlan: agent-facing CLI patterns, channel routing, installer flow,
  diagnostics, and related implementation references.
- License: MIT License
- Copyright: Copyright (c) 2025 Agent Eyes
- Source: <https://github.com/Panniantong/Agent-Reach>
- License: <https://github.com/Panniantong/Agent-Reach/blob/main/LICENSE>

## NewsNow

- Project: NewsNow
- Role in Guanlan: source catalog thinking, hotnews normalization, and optional
  backend design references.
- License: MIT License
- Copyright: Copyright (c) 2024 ourongxing
- Source: <https://github.com/ourongxing/newsnow>
- License: <https://github.com/ourongxing/newsnow/blob/main/LICENSE>

## CyberTomato Skills

- Project: cybertomato-skills
- Role in Guanlan: design reference for read-only arXiv lookups, WeChat article
  extraction fallbacks, and explicit RSS watchlist workflows.
- Code copied into Guanlan: none; Guanlan implements these capabilities with
  native public API/RSS/HTML readers and keeps the read-only boundary.
- Source: <https://github.com/TomatoCodeBase/cybertomato-skills>
- License note: repository documentation described MIT licensing at review time;
  Guanlan does not vendor its skill text or code.

## Distribution

Guanlan release artifacts should include:

- [LICENSE](../LICENSE)
- [NOTICE](../NOTICE)
- this source attribution file

Attribution is intentionally centralized here so product docs can stay focused
on Guanlan itself.
