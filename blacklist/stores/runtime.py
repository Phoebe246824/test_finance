from __future__ import annotations

import json
from typing import Any

from blacklist.stores.factory import StoreBundle, create_store_bundle

_STORE_BUNDLE: StoreBundle | None = None
_STORE_SIGNATURE: str | None = None


def get_runtime_store_bundle(config: dict[str, Any]) -> StoreBundle:
    global _STORE_BUNDLE, _STORE_SIGNATURE

    signature = _store_config_signature(config)
    if _STORE_BUNDLE is None or _STORE_SIGNATURE != signature:
        _STORE_BUNDLE = create_store_bundle(config)
        _STORE_SIGNATURE = signature
    return _STORE_BUNDLE


def reset_runtime_store_bundle_cache() -> None:
    global _STORE_BUNDLE, _STORE_SIGNATURE

    _STORE_BUNDLE = None
    _STORE_SIGNATURE = None


def _store_config_signature(config: dict[str, Any]) -> str:
    return json.dumps(
        {
            "milvus": config.get("milvus", {}),
            "embedder": config.get("embedder", {}),
        },
        sort_keys=True,
    )
