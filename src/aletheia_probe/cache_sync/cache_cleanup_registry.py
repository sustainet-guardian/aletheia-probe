# SPDX-License-Identifier: MIT
"""Registry for cache cleanup operations."""

from collections.abc import Callable
from typing import Any

from ..logging_config import get_detail_logger


class CacheCleanupRegistry:
    """Registry for managing cache cleanup operations."""

    def __init__(self) -> None:
        self._cleaners: dict[str, Callable[[], int]] = {}
        self.detail_logger = get_detail_logger()

    def register(self, name: str, cleanup_func: Callable[[], int]) -> None:
        """Register a cache cleanup function.

        Args:
            name: Name of the cache (for logging)
            cleanup_func: Callable that performs cleanup and returns count of removed entries
        """
        self._cleaners[name] = cleanup_func

    def cleanup_all(self) -> dict[str, Any]:
        """Execute all registered cleanup functions.

        Returns:
            Dictionary with cleanup results including total count
        """
        results: dict[str, int] = {}
        total_expired = 0

        for name, cleanup_func in self._cleaners.items():
            try:
                count = cleanup_func()
                results[name] = count
                total_expired += count
                self.detail_logger.info(
                    f"Cleaned up {count} expired {name} cache entries"
                )
            except Exception as e:
                self.detail_logger.exception(f"Error cleaning up {name} cache: {e}")
                results[name] = 0

        return {"results": results, "total": total_expired}
