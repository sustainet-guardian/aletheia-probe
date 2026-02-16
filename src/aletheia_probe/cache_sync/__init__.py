# SPDX-License-Identifier: MIT
"""Cache synchronization package for automatic backend data management."""

from typing import Any

from .cache_cleanup_registry import CacheCleanupRegistry
from .db_writer import AsyncDBWriter


__all__ = [
    "AsyncDBWriter",
    "CacheCleanupRegistry",
    "CacheSyncManager",
    "cache_sync_manager",
]


def __getattr__(name: str) -> Any:
    """Lazily resolve sync_manager exports to avoid import-time cycles."""
    if name in {"CacheSyncManager", "cache_sync_manager"}:
        from .sync_manager import CacheSyncManager, cache_sync_manager

        if name == "CacheSyncManager":
            return CacheSyncManager
        return cache_sync_manager
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
