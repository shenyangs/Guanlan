# -*- coding: utf-8 -*-
"""Tests for distribution surface status classification."""

from __future__ import annotations

import json
import urllib.error

from scripts import distribution_status as ds


def _resp(body: str, *, ok: bool = True, status: int = 200, error: str = "") -> ds.HttpResponse:
    return ds.HttpResponse(ok=ok, status_code=status, body=body, error=error)


def test_pypi_json_reports_stale_version():
    payload = json.dumps({"info": {"version": "0.6.13"}})

    result = ds.check_pypi_json("0.7.7", fetch=lambda _url: _resp(payload))

    assert result["status"] == "stale"
    assert result["actual"] == "0.6.13"


def test_pypi_json_reports_current_version():
    payload = json.dumps({"info": {"version": "0.7.7"}})

    result = ds.check_pypi_json("0.7.7", fetch=lambda _url: _resp(payload))

    assert result["status"] == "ok"


def test_pip_index_certificate_failure_is_local_tls_error():
    def fake_run(_args):
        return {
            "returncode": 1,
            "stdout": "",
            "stderr": "Could not fetch URL because CERTIFICATE_VERIFY_FAILED",
        }

    result = ds.check_pip_index("0.7.7", run=fake_run)

    assert result["status"] == "local_tls_error"
    assert result["expected"] == "0.7.7"


def test_fetch_url_uses_verified_system_curl_when_python_ca_is_stale(monkeypatch):
    def raise_tls(*_args, **_kwargs):
        raise urllib.error.URLError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")

    monkeypatch.setattr(ds.urllib.request, "urlopen", raise_tls)
    monkeypatch.setattr(
        ds,
        "_fetch_url_with_curl",
        lambda _url, *, timeout: _resp('{"info":{"version":"0.7.7"}}'),
    )

    result = ds.fetch_url("https://pypi.org/pypi/guanlan/json")

    assert result.ok is True
    assert '"version"' in result.body


def test_json_simple_and_tap_classify_local_tls_without_calling_it_stale():
    response = _resp("", ok=False, error="CERTIFICATE_VERIFY_FAILED")

    assert ds.check_pypi_json("0.7.7", fetch=lambda _url: response)["status"] == "local_tls_error"
    assert ds.check_pypi_simple("0.7.7", fetch=lambda _url: response)["status"] == "local_tls_error"
    assert ds.check_homebrew_tap("0.7.7", fetch=lambda _url: response)["status"] == "local_tls_error"


def test_homebrew_old_formula_is_stale():
    formula = 'url "https://files.pythonhosted.org/packages/source/g/guanlan/guanlan-0.7.6.tar.gz"'

    result = ds.check_homebrew_tap("0.7.7", fetch=lambda _url: _resp(formula))

    assert result["status"] == "stale"
    assert result["actual"] == "0.7.6"


def test_website_source_ok_public_blocked_is_incomplete():
    def fake_fetch(url: str) -> ds.HttpResponse:
        if url == "http://101.37.70.222/":
            return _resp("<span>Guanlan v0.7.7</span>")
        return _resp("备案 non-compliance ICP", ok=False, status=403, error="HTTP 403")

    result = ds.check_websites("0.7.7", fetch=fake_fetch)

    assert result["status"] == "source_deployed_but_public_site_blocked"
    assert {item["status"] for item in result["entries"]} == {"blocked_icp", "ok"}


def test_distribution_report_treats_local_tls_as_non_stale(monkeypatch):
    monkeypatch.setattr(ds, "check_github_tag", lambda version: ds._status("github_tag", "ok", expected=version))
    monkeypatch.setattr(ds, "check_pypi_json", lambda version: ds._status("pypi_json", "ok", expected=version))
    monkeypatch.setattr(ds, "check_pypi_simple", lambda version: ds._status("pypi_simple", "ok", expected=version))
    monkeypatch.setattr(ds, "check_pip_index", lambda version: ds._status("pip_index", "local_tls_error", expected=version))
    monkeypatch.setattr(ds, "check_homebrew_tap", lambda version: ds._status("homebrew_tap", "ok", expected=version))
    monkeypatch.setattr(ds, "check_websites", lambda version: ds._status("website", "ok", expected=version))
    monkeypatch.setattr(ds, "check_local_entrypoints", lambda version: ds._status("local_entrypoints", "ok", expected=version))

    report = ds.build_distribution_report("0.7.7")

    assert report["status"] == "ok"
    assert any(item["status"] == "local_tls_error" for item in report["checks"])


def test_markdown_includes_unavailable_error_details():
    report = {
        "expected_version": "0.7.7",
        "status": "fail",
        "generated_at": "2026-07-01T00:00:00Z",
        "checks": [
            ds._status(
                "pypi_json",
                "unavailable",
                expected="0.7.7",
                http_status=0,
                error="<urlopen error Tunnel connection failed: 503 Service Unavailable>",
            ),
            ds._status(
                "website",
                "incomplete",
                expected="0.7.7",
                entries=[
                    {
                        "url": "https://guanlan.xin/",
                        "status": "unavailable",
                        "http_status": 0,
                        "error": "timed out",
                    }
                ],
            ),
        ],
    }

    markdown = ds.format_markdown(report)

    assert "Tunnel connection failed: 503 Service Unavailable" in markdown
    assert "https://guanlan.xin/=unavailable (timed out)" in markdown
