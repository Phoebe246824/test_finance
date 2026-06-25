from __future__ import annotations

from urllib.parse import urlsplit

from backend.app.core.config import settings


def webhook_headers_for_target(target: str) -> dict[str, str]:
    if not is_local_demo_receiver(target):
        return {}
    return {"X-Sentinel-Webhook-Token": settings.webhook_token}


def is_local_demo_receiver(target: str) -> bool:
    parsed = urlsplit(target)
    host = (parsed.hostname or "").rstrip(".").lower()
    return host in {"localhost", "127.0.0.1", "::1"} and parsed.path == "/webhook/alert"
