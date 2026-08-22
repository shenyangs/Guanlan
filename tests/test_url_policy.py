# -*- coding: utf-8 -*-
"""Security and compatibility matrix for layered URL policies."""

import pytest

import guanlan.url_policy as url_policy
from guanlan.url_policy import (
    ConfiguredEndpointPolicy,
    PublicURLPolicy,
    URLPolicyError,
    validate_public_response,
)


def _public_resolver(_host: str, _port: int):
    return ["93.184.216.34", "2606:2800:220:1:248:1893:25c8:1946"]


@pytest.mark.parametrize(
    "url, reason",
    [
        ("file:///etc/passwd", "unsupported_scheme"),
        ("https://user:secret@example.com/a", "embedded_credentials"),
        ("http://127.0.0.1/admin", "non_public_address"),
        ("http://[::1]/admin", "non_public_address"),
        ("http://169.254.169.254/latest/meta-data", "non_public_address"),
        ("http://10.0.0.1/a", "non_public_address"),
        ("http://metadata.google.internal/a", "local_or_metadata_hostname"),
        ("http://service.local/a", "local_or_metadata_hostname"),
    ],
)
def test_public_policy_rejects_non_public_targets(url, reason):
    with pytest.raises(URLPolicyError) as caught:
        PublicURLPolicy(resolver=_public_resolver).validate(url)
    assert caught.value.reason == reason
    assert "secret" not in str(caught.value)


def test_public_policy_accepts_only_when_every_dns_answer_is_global():
    decision = PublicURLPolicy(resolver=_public_resolver).validate("https://example.com/a")
    assert decision["status"] == "allowed"
    assert decision["policy"] == "public_web"
    assert len(decision["resolved_addresses"]) == 2

    with pytest.raises(URLPolicyError, match="non_public_address"):
        PublicURLPolicy(resolver=lambda *_args: ["93.184.216.34", "192.168.1.9"]).validate(
            "https://rebind.example/a"
        )


def test_public_policy_accepts_proxy_fake_ip_for_hostname_only():
    decision = PublicURLPolicy(
        resolver=lambda *_args: ["198.18.0.96", "::ffff:198.18.0.96"],
        proxy_detector=lambda host: host == "example.com",
    ).validate("https://example.com/a")

    assert decision["status"] == "allowed"
    assert decision["resolution_mode"] == "loopback_proxy_fake_ip"
    assert decision["proxy_fake_ip_compatibility"] is True


def test_public_policy_accepts_mixed_public_and_fake_ip_behind_loopback_proxy():
    decision = PublicURLPolicy(
        resolver=lambda *_args: ["93.184.216.34", "198.18.0.96"],
        proxy_detector=lambda _host: True,
    ).validate("https://example.com/a")

    assert decision["resolution_mode"] == "loopback_proxy_mixed_dns"
    assert decision["loopback_proxy_compatibility"] is True


def test_public_policy_delegates_dns_failure_to_matching_loopback_proxy():
    def failing_resolver(*_args):
        raise OSError("local DNS unavailable")

    decision = PublicURLPolicy(
        resolver=failing_resolver,
        proxy_detector=lambda _host: True,
    ).validate("https://example.com/a")

    assert decision["resolved_addresses"] == []
    assert decision["resolution_mode"] == "loopback_proxy_remote_dns"
    assert decision["loopback_proxy_compatibility"] is True


def test_public_policy_rejects_fake_ip_without_matching_loopback_proxy():
    with pytest.raises(URLPolicyError, match="non_public_address"):
        PublicURLPolicy(
            resolver=lambda *_args: ["198.18.0.96"],
            proxy_detector=lambda _host: False,
        ).validate("https://example.com/a")


def test_public_policy_never_accepts_fake_ip_literal_or_mixed_private_dns():
    def proxy_enabled(_host: str) -> bool:
        return True

    with pytest.raises(URLPolicyError, match="non_public_address"):
        PublicURLPolicy(proxy_detector=proxy_enabled).validate("http://198.18.0.96/admin")

    with pytest.raises(URLPolicyError, match="non_public_address"):
        PublicURLPolicy(
            resolver=lambda *_args: ["198.18.0.96", "192.168.1.9"],
            proxy_detector=proxy_enabled,
        ).validate("https://rebind.example/a")


def test_proxy_detector_requires_non_bypassed_loopback_http_proxy(monkeypatch):
    monkeypatch.setattr("urllib.request.proxy_bypass", lambda _host: False)
    monkeypatch.setattr("urllib.request.getproxies", lambda: {"https": "http://127.0.0.1:1082"})
    assert url_policy._loopback_proxy_handles_host("example.com") is True
    assert url_policy._loopback_proxy_handles_host("example.com", scheme="http") is False

    monkeypatch.setattr("urllib.request.getproxies", lambda: {"https": "http://192.168.1.8:1082"})
    assert url_policy._loopback_proxy_handles_host("example.com") is False

    monkeypatch.setattr("urllib.request.getproxies", lambda: {"https": "http://127.0.0.1:1082"})
    monkeypatch.setattr("urllib.request.proxy_bypass", lambda _host: True)
    assert url_policy._loopback_proxy_handles_host("example.com") is False


def test_redirect_target_is_revalidated_before_response_body_is_used():
    class Response:
        def geturl(self):
            return "http://127.0.0.1/private"

    with pytest.raises(URLPolicyError, match="non_public_address"):
        validate_public_response("https://example.com/start", Response(), resolver=_public_resolver)


def test_configured_endpoint_policy_allows_exact_private_host_only():
    policy = ConfiguredEndpointPolicy(allowed_hosts=frozenset({"127.0.0.1", "newsnow.internal"}))
    decision = policy.validate("http://127.0.0.1:4444/api")
    assert decision["policy"] == "configured_endpoint"
    assert decision["explicit_configuration_required"] is True

    with pytest.raises(URLPolicyError, match="host_not_explicitly_configured"):
        policy.validate("http://192.168.1.8/api")
    with pytest.raises(URLPolicyError, match="embedded_credentials"):
        policy.validate("http://token:secret@127.0.0.1:4444/api")


def test_public_read_rejects_private_literal_before_network(monkeypatch):
    from guanlan.web.read import read_url_with_trace

    called = False

    def fake_urlopen(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("network should not be called")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    with pytest.raises(URLPolicyError, match="non_public_address"):
        read_url_with_trace("http://127.0.0.1/private", backend="direct")
    assert called is False
