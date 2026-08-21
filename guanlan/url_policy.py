# -*- coding: utf-8 -*-
"""Layered URL policies for public reads and configured endpoints."""

from __future__ import annotations

import functools
import ipaddress
import socket
import urllib.parse
from dataclasses import dataclass
from typing import Any, Callable, Iterable

URL_POLICY_SCHEMA_VERSION = "url_policy_v1"
Resolver = Callable[[str, int], Iterable[str]]


class URLPolicyError(ValueError):
    """A URL failed a deterministic safety boundary."""

    def __init__(self, reason: str, *, url: str = "") -> None:
        self.reason = reason
        self.url = url
        super().__init__(f"public URL rejected: {reason}")


@dataclass(frozen=True)
class PublicURLPolicy:
    """Fail-closed policy for arbitrary public-web targets."""

    resolver: Resolver | None = None
    resolve_dns: bool = True

    def validate(self, url: str) -> dict[str, Any]:
        parsed, host, port = _parse_http_url(url)
        addresses: tuple[str, ...] = ()
        literal = _ip_literal(host)
        if literal is not None:
            _require_global_address(literal, url=url)
            addresses = (str(literal),)
        elif _blocked_hostname(host):
            raise URLPolicyError("local_or_metadata_hostname", url=url)
        elif self.resolve_dns:
            resolver = self.resolver or _resolve_host
            try:
                addresses = tuple(sorted(set(str(item) for item in resolver(host, port))))
            except URLPolicyError:
                raise
            except Exception as exc:
                raise URLPolicyError("dns_resolution_failed", url=url) from exc
            if not addresses:
                raise URLPolicyError("dns_resolution_empty", url=url)
            for address in addresses:
                try:
                    resolved = ipaddress.ip_address(address)
                except ValueError as exc:
                    raise URLPolicyError("dns_returned_invalid_address", url=url) from exc
                _require_global_address(resolved, url=url)
        return {
            "schema_version": URL_POLICY_SCHEMA_VERSION,
            "policy": "public_web",
            "status": "allowed",
            "scheme": parsed.scheme.lower(),
            "host": host,
            "port": port,
            "resolved_addresses": list(addresses),
            "redirect_revalidation": True,
            "credential_material_access_allowed": False,
        }


@dataclass(frozen=True)
class ConfiguredEndpointPolicy:
    """Policy for explicit user/application configured service endpoints.

    Private and loopback addresses are allowed only for an exact configured
    hostname.  This policy must never be used for arbitrary user-supplied URLs.
    """

    allowed_hosts: frozenset[str]
    resolver: Resolver | None = None
    resolve_dns: bool = False

    def validate(self, url: str) -> dict[str, Any]:
        parsed, host, port = _parse_http_url(url)
        allowed = {item.lower().rstrip(".") for item in self.allowed_hosts}
        if host not in allowed:
            raise URLPolicyError("host_not_explicitly_configured", url=url)
        addresses: tuple[str, ...] = ()
        if self.resolve_dns:
            resolver = self.resolver or _resolve_host
            try:
                addresses = tuple(sorted(set(str(item) for item in resolver(host, port))))
            except Exception as exc:
                raise URLPolicyError("configured_endpoint_dns_failed", url=url) from exc
        return {
            "schema_version": URL_POLICY_SCHEMA_VERSION,
            "policy": "configured_endpoint",
            "status": "allowed",
            "scheme": parsed.scheme.lower(),
            "host": host,
            "port": port,
            "resolved_addresses": list(addresses),
            "explicit_configuration_required": True,
            "credential_material_access_allowed": False,
        }


def validate_public_url(
    url: str, *, resolver: Resolver | None = None, resolve_dns: bool = True
) -> dict[str, Any]:
    return PublicURLPolicy(resolver=resolver, resolve_dns=resolve_dns).validate(url)


def validate_public_response(
    requested_url: str,
    response: Any,
    *,
    resolver: Resolver | None = None,
    resolve_dns: bool = True,
) -> dict[str, Any]:
    """Revalidate urllib's final redirect target before response bytes are used."""

    geturl = getattr(response, "geturl", None)
    final_url = str(geturl() or requested_url) if callable(geturl) else requested_url
    decision = validate_public_url(final_url, resolver=resolver, resolve_dns=resolve_dns)
    decision["requested_url"] = requested_url
    decision["final_url"] = final_url
    decision["redirected"] = final_url != requested_url
    return decision


def _parse_http_url(url: str) -> tuple[urllib.parse.SplitResult, str, int]:
    value = str(url or "").strip()
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    except ValueError as exc:
        raise URLPolicyError("invalid_url", url=value) from exc
    if parsed.scheme.lower() not in {"http", "https"}:
        raise URLPolicyError("unsupported_scheme", url=value)
    if parsed.username is not None or parsed.password is not None:
        raise URLPolicyError("embedded_credentials", url=value)
    raw_host = parsed.hostname or ""
    if not raw_host:
        raise URLPolicyError("missing_hostname", url=value)
    try:
        host = raw_host.encode("idna").decode("ascii").lower().rstrip(".")
    except UnicodeError as exc:
        raise URLPolicyError("invalid_hostname", url=value) from exc
    if not 1 <= port <= 65535:
        raise URLPolicyError("invalid_port", url=value)
    return parsed, host, port


def _ip_literal(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


def _require_global_address(
    address: ipaddress.IPv4Address | ipaddress.IPv6Address, *, url: str
) -> None:
    if not address.is_global:
        raise URLPolicyError("non_public_address", url=url)


def _blocked_hostname(host: str) -> bool:
    lowered = host.lower().rstrip(".")
    return (
        lowered == "localhost"
        or lowered.endswith(".localhost")
        or lowered.endswith(".local")
        or lowered in {"metadata.google.internal", "metadata.azure.internal"}
        or lowered.startswith("metadata.")
    )


@functools.lru_cache(maxsize=512)
def _resolve_host(host: str, port: int) -> tuple[str, ...]:
    records = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return tuple(sorted({str(record[4][0]).split("%", 1)[0] for record in records}))


__all__ = [
    "ConfiguredEndpointPolicy",
    "PublicURLPolicy",
    "URLPolicyError",
    "URL_POLICY_SCHEMA_VERSION",
    "validate_public_response",
    "validate_public_url",
]
