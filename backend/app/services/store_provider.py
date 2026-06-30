from __future__ import annotations

from functools import lru_cache

from blacklist.stores.factory import StoreBundle, create_store_bundle


@lru_cache(maxsize=1)
def get_store_bundle() -> StoreBundle:
    from main import load_config

    return create_store_bundle(load_config())


def reset_store_bundle_cache() -> None:
    get_store_bundle.cache_clear()
