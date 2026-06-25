from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True, slots=True)
class UnsafeOutboundAddressError(Exception):
    message: str

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True, slots=True)
class UrlSafetyResult:
    allowed: bool
    message: str = ""


def validate_outbound_http_url(raw_url: str) -> UrlSafetyResult:
    url = raw_url.strip()
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return UrlSafetyResult(False, "地址必须以 http:// 或 https:// 开头")
    if parsed.username or parsed.password:
        return UrlSafetyResult(False, "地址不允许包含用户名或密码")
    host = parsed.hostname.rstrip(".").lower()
    try:
        resolve_safe_connect_host(host, _default_port(parsed.scheme, parsed.port))
    except UnsafeOutboundAddressError as exc:
        return UrlSafetyResult(False, str(exc))
    except ValueError:
        return UrlSafetyResult(False, "地址端口格式不正确")
    return UrlSafetyResult(True)


def resolve_safe_connect_host(host: str, port: int) -> str:
    normalized = host.rstrip(".").lower()
    if _is_local_demo_host(normalized):
        return normalized
    try:
        literal_ip = ipaddress.ip_address(normalized)
    except ValueError:
        return _resolve_public_host(normalized, port)
    if _is_blocked_ip(literal_ip):
        raise UnsafeOutboundAddressError("不允许访问该地址")
    return normalized


def _default_port(scheme: str, parsed_port: int | None) -> int:
    if parsed_port is not None:
        return parsed_port
    if scheme == "https":
        return 443
    return 80


def _resolve_public_host(host: str, port: int) -> str:
    try:
        resolved = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeOutboundAddressError("地址无法解析") from exc
    addresses: list[str] = []
    for item in resolved:
        address = item[4][0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError as exc:
            raise UnsafeOutboundAddressError("不允许访问该地址") from exc
        if _is_blocked_ip(ip):
            raise UnsafeOutboundAddressError("不允许访问该地址")
        addresses.append(address)
    if not addresses:
        raise UnsafeOutboundAddressError("地址无法解析")
    return addresses[0]


def _is_local_demo_host(host: str) -> bool:
    return host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".localhost")


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )
