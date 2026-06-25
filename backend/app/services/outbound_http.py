from __future__ import annotations

from types import TracebackType
from typing import Iterable

import httpcore
import httpx

from backend.app.services.url_safety import (
    UnsafeOutboundAddressError,
    resolve_safe_connect_host,
)

OUTBOUND_LIMITS = httpx.Limits(
    max_connections=20,
    max_keepalive_connections=5,
    keepalive_expiry=10.0,
)


class SafeAsyncNetworkBackend(httpcore.AsyncNetworkBackend):
    def __init__(self) -> None:
        self._backend = httpcore.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        try:
            connect_host = resolve_safe_connect_host(host, port)
        except UnsafeOutboundAddressError as exc:
            raise httpcore.ConnectError(str(exc)) from exc
        return await self._backend.connect_tcp(
            connect_host,
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        return await self._backend.connect_unix_socket(
            path,
            timeout=timeout,
            socket_options=socket_options,
        )

    async def sleep(self, seconds: float) -> None:
        await self._backend.sleep(seconds)


class SafeAsyncHTTPTransport(httpx.AsyncHTTPTransport):
    def __init__(
        self,
        *,
        limits: httpx.Limits = OUTBOUND_LIMITS,
        retries: int = 0,
    ) -> None:
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=httpcore.default_ssl_context(),
            max_connections=limits.max_connections,
            max_keepalive_connections=limits.max_keepalive_connections,
            keepalive_expiry=limits.keepalive_expiry,
            http1=True,
            http2=False,
            retries=retries,
            network_backend=SafeAsyncNetworkBackend(),
        )

    async def __aenter__(self) -> SafeAsyncHTTPTransport:
        await self._pool.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ) -> None:
        await self._pool.__aexit__(exc_type, exc_value, traceback)


def create_outbound_async_client(
    *,
    timeout: float,
    follow_redirects: bool = False,
) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=follow_redirects,
        trust_env=False,
        transport=SafeAsyncHTTPTransport(),
    )
