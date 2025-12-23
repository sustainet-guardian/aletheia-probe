# SPDX-License-Identifier: MIT
"""Assessment result caching for the cache system."""

import sqlite3
from datetime import datetime, timedelta

from ..models import AssessmentResult
from .base import CacheBase


class AssessmentCache(CacheBase):
    """Manages assessment result caching with TTL."""

    def cache_assessment_result(
        self,
        query_hash: str,
        query_input: str,
        result: AssessmentResult,
        ttl_hours: int = 24,
    ) -> None:
        """Cache an assessment result with TTL.

        Args:
            query_hash: Hash of the query for deduplication
            query_input: Original query input
            result: Assessment result to cache
            ttl_hours: Time-to-live in hours
        """
        expires_at = datetime.now() + timedelta(hours=ttl_hours)
        result_json = result.model_dump_json()

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO assessment_cache
                (query_hash, query_input, assessment_result, expires_at)
                VALUES (?, ?, ?, ?)
            """,
                (query_hash, query_input, result_json, expires_at),
            )

    def get_cached_assessment(self, query_hash: str) -> AssessmentResult | None:
        """Get cached assessment result if not expired.

        Args:
            query_hash: Hash of the query

        Returns:
            Cached assessment result or None if not found or expired
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT assessment_result FROM assessment_cache
                WHERE query_hash = ? AND expires_at > ?
            """,
                (query_hash, datetime.now()),
            )

            row = cursor.fetchone()
            if row:
                return AssessmentResult.model_validate_json(row[0])
            return None

    def cleanup_expired_cache(self) -> int:
        """Remove expired assessment cache entries.

        Returns:
            Number of entries removed
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM assessment_cache WHERE expires_at <= ?", (datetime.now(),)
            )
            return cursor.rowcount

    def get_assessment_cache_count(self) -> int:
        """Get the count of assessment cache entries.

        Returns:
            Number of cached assessment entries
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM assessment_cache")
            result = cursor.fetchone()
            return int(result[0]) if result else 0

    def clear_assessment_cache(self) -> int:
        """Clear all assessment cache entries.

        Returns:
            The number of entries that were cleared.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM assessment_cache")
            conn.commit()
            return cursor.rowcount
