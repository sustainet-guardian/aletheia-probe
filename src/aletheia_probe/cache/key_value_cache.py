# SPDX-License-Identifier: MIT
"""Generic key-value caching for the cache system."""

import sqlite3
from datetime import datetime, timedelta

from .base import CacheBase


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

        with sqlite3.connect(self.db_path) as conn:
            # Create table if it doesn't exist
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS key_value_cache (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL
                )
                """
            )

            conn.execute(
                """
                INSERT OR REPLACE INTO key_value_cache (key, value, expires_at)
                VALUES (?, ?, ?)
                """,
                (key, value, expires_at),
            )
            conn.commit()

    def get_cached_value(self, key: str) -> str | None:
        """Get a cached value by key.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found or expired
        """
        with sqlite3.connect(self.db_path) as conn:
            # Ensure table exists
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS key_value_cache (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL
                )
                """
            )

            cursor = conn.execute(
                """
                SELECT value FROM key_value_cache
                WHERE key = ? AND expires_at > CURRENT_TIMESTAMP
                """,
                (key,),
            )
            row = cursor.fetchone()
            return row[0] if row else None
