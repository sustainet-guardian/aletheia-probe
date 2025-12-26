# SPDX-License-Identifier: MIT
"""Generic key-value caching for the cache system."""

import sqlite3
from datetime import datetime, timedelta

from ..logging_config import get_detail_logger, get_status_logger
from .base import CacheBase


detail_logger = get_detail_logger()
status_logger = get_status_logger()


class KeyValueCache(CacheBase):
    """Manages generic key-value caching with TTL."""

    def set_cached_value(self, key: str, value: str, ttl_hours: int = 24) -> None:
        """Store a key-value pair in cache with TTL.

        Args:
            key: Cache key
            value: Value to cache
            ttl_hours: Time-to-live in hours
        """
        expires_at = datetime.now() + timedelta(hours=ttl_hours)
        detail_logger.debug(f"Storing cache entry: key='{key}', ttl_hours={ttl_hours}")

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO key_value_cache (key, value, expires_at)
                VALUES (?, ?, ?)
                """,
                (key, value, expires_at),
            )
            conn.commit()
            detail_logger.debug(f"Successfully stored cache entry for key '{key}'")

    def get_cached_value(self, key: str) -> str | None:
        """Get a cached value by key.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found or expired
        """
        detail_logger.debug(f"Looking up cache entry for key '{key}'")

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT value FROM key_value_cache
                WHERE key = ? AND expires_at > CURRENT_TIMESTAMP
                """,
                (key,),
            )
            row = cursor.fetchone()
            result = row[0] if row else None

            if result:
                detail_logger.debug(f"Cache hit for key '{key}'")
            else:
                detail_logger.debug(f"Cache miss for key '{key}' (not found or expired)")

            return result
