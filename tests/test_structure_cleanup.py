# -*- coding: utf-8 -*-
"""Structural regression checks for the cleanup refactor."""

from pathlib import Path

import guanlan
from guanlan import webtools
from guanlan.web import _impl, _search_quality_impl, read, renderers, research, search

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_removed_runtime_test_helpers_stay_out_of_production_package():
    assert not (REPO_ROOT / "guanlan/channel_runtime.py").exists()
    assert not (REPO_ROOT / "guanlan/stress_replay.py").exists()
    assert (REPO_ROOT / "tests/support/channel_runtime_trial.py").exists()
    assert (REPO_ROOT / "scripts/stress_replay.py").exists()


def test_legacy_python_facade_is_not_exported():
    assert not hasattr(guanlan, "Guanlan")


def test_read_entrypoints_are_owned_by_read_subsystem():
    assert read.read_url.__module__ == "guanlan.web._read_impl"
    assert _impl.read_url.__module__ == "guanlan.web._read_impl"
    assert _impl.read_batch.__module__ == "guanlan.web._read_impl"
    assert webtools.read_url.__module__ == "guanlan.webtools"


def test_search_quality_entrypoints_are_owned_by_search_quality_subsystem():
    assert _search_quality_impl.detect_search_quality_profile.__module__ == "guanlan.web._search_quality_impl"
    assert _impl.detect_search_quality_profile.__module__ == "guanlan.web._search_quality_impl"
    assert _impl.build_query_strategy.__module__ == "guanlan.web._search_quality_impl"
    assert _impl.search_quality_summary.__module__ == "guanlan.web._search_quality_impl"


def test_public_web_modules_own_runtime_entrypoints():
    assert search.search_web.__module__ == "guanlan.web.search_service"
    assert research.build_research_packet.__module__ == "guanlan.web.research_service"
    assert renderers.format_search_trace.__module__ == "guanlan.web.renderers"


def test_facade_files_stay_small():
    assert _line_count(REPO_ROOT / "guanlan/web/_impl.py") <= 800
    assert _line_count(REPO_ROOT / "guanlan/webtools.py") <= 800
    assert _line_count(REPO_ROOT / "guanlan/cli.py") <= 1500
    assert _line_count(REPO_ROOT / "guanlan/commands/_legacy_impl.py") <= 300


def test_webtools_tests_stay_split():
    for path in sorted((REPO_ROOT / "tests").glob("test_webtools*.py")):
        assert _line_count(path) <= 1500, path.name


def test_production_code_uses_split_web_modules_internally():
    forbidden = ("from guanlan import webtools", "import guanlan.webtools", "from guanlan.webtools")
    for path in sorted((REPO_ROOT / "guanlan").rglob("*.py")):
        if path.name == "webtools.py":
            continue
        text = path.read_text(encoding="utf-8")
        assert not any(pattern in text for pattern in forbidden), path.relative_to(REPO_ROOT)


def test_search_quality_has_no_transitional_global_sync():
    text = (REPO_ROOT / "guanlan/web/_search_quality_impl.py").read_text(encoding="utf-8")
    assert "_sync_base_globals" not in text
    assert "ruff: noqa: F821" not in text


def test_direct_legacy_runtime_import_is_limited_to_type_identity_bridge():
    direct_imports = []
    for path in sorted((REPO_ROOT / "guanlan" / "web").glob("*.py")):
        text = path.read_text(encoding="utf-8")
        if "guanlan.web._legacy_web_impl" in text:
            direct_imports.append(path.relative_to(REPO_ROOT).as_posix())

    assert direct_imports == ["guanlan/web/_impl.py", "guanlan/web/search_types.py"]


def test_tool_registry_projects_canonical_surface_fields():
    from guanlan.tool_registry import mcp_projection_defaults

    projections = mcp_projection_defaults()
    for name in ("guanlan_search", "guanlan_read", "guanlan_research"):
        projection = projections[name]
        assert projection["cli_handler"]
        assert projection["service_entrypoint"]
        assert isinstance(projection["request_schema"], dict)


def test_mcp_and_http_surfaces_are_registry_projections():
    from guanlan.integrations.mcp_server import _tool_definitions
    from guanlan.serve import declared_http_tool_routes
    from guanlan.tool_registry import core_agent_tool_names, http_routes

    mcp_names = {tool["name"] for tool in _tool_definitions()}
    assert mcp_names == core_agent_tool_names()
    assert declared_http_tool_routes() == http_routes()
    assert {"/research", "/prompt", "/context"} <= http_routes()
    for tool in _tool_definitions():
        schema = tool.get("inputSchema") or {}
        assert schema.get("type") == "object", tool["name"]
        assert isinstance(schema.get("properties"), dict), tool["name"]


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())
