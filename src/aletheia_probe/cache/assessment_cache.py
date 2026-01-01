# SPDX-License-Identifier: MIT
"""Assessment result caching for the cache system."""

from datetime import datetime, timedelta

from ..logging_config import get_detail_logger, get_status_logger
from ..models import AssessmentResult
from .base import CacheBase


detail_logger = get_detail_logger()
status_logger = get_status_logger()


class AssessmentCache(CacheBase):
    """Manages assessment result caching with TTL."""

    def _validate_query_hash(self, query_hash: str) -> None:
        """Validate query_hash parameter format.

        Args:
            query_hash: Hash value to validate

        Raises:
            ValueError: If query_hash is invalid or empty
        """
        if not query_hash or not query_hash.strip():
            raise ValueError("query_hash cannot be empty or None")

        # MD5 hash should be 32 hexadecimal characters
        if len(query_hash) != 32:
            raise ValueError(
                f"query_hash must be 32 characters long, got {len(query_hash)}"
            )

        # Check if all characters are hexadecimal
        if not all(c in "0123456789abcdefABCDEF" for c in query_hash):
            raise ValueError("query_hash must contain only hexadecimal characters")

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
        self._validate_query_hash(query_hash)

        detail_logger.debug(
            f"Caching assessment result for query_hash '{query_hash}' with TTL {ttl_hours}h"
        )
        detail_logger.debug(f"Query input: '{query_input}'")
        detail_logger.debug(f"Assessment result: {result.assessment}")

        expires_at = datetime.now() + timedelta(hours=ttl_hours)
        result_json = result.model_dump_json()

        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO assessment_cache
                (query_hash, query_input, assessment_result, expires_at)
                VALUES (?, ?, ?, ?)
            """,
                (query_hash, query_input, result_json, expires_at.isoformat()),
            )
            detail_logger.debug(
                f"Successfully cached assessment result for query_hash '{query_hash}'"
            )

    def get_cached_assessment(self, query_hash: str) -> AssessmentResult | None:
        """Get cached assessment result if not expired.

        Args:
            query_hash: Hash of the query

        Returns:
            Cached assessment result or None if not found or expired
        """
        self._validate_query_hash(query_hash)

        detail_logger.debug(
            f"Looking up cached assessment for query_hash '{query_hash}'"
        )

        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT assessment_result FROM assessment_cache
                WHERE query_hash = ? AND expires_at > ?
            """,
                (query_hash, datetime.now().isoformat()),
            )

            row = cursor.fetchone()
            if row:
                result = AssessmentResult.model_validate_json(row[0])
                detail_logger.debug(
                    f"Found cached assessment for query_hash '{query_hash}': {result.assessment}"
                )
                return result
            else:
                detail_logger.debug(
                    f"No valid cached assessment found for query_hash '{query_hash}'"
                )
                return None

    def cleanup_expired_cache(self) -> int:
        """Remove expired assessment cache entries.

        Returns:
            Number of entries removed
        """
        detail_logger.debug("Starting cleanup of expired assessment cache entries")

        with self.get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM assessment_cache WHERE expires_at <= ?",
                (datetime.now().isoformat(),),
            )
            removed_count: int = cursor.rowcount
            detail_logger.debug(
                f"Cleanup completed: removed {removed_count} expired assessment cache entries"
            )
            return removed_count

    def get_assessment_cache_count(self) -> int:
        """Get the count of assessment cache entries.

        Returns:
            Number of cached assessment entries
        """
        detail_logger.debug("Getting assessment cache count")

        with self.get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM assessment_cache")
            result = cursor.fetchone()
            count = int(result[0]) if result else 0
            detail_logger.debug(f"Assessment cache contains {count} entries")
            return count

    def clear_assessment_cache(self) -> int:
        """Clear all assessment cache entries.

        Returns:
            The number of entries that were cleared.
        """
        detail_logger.debug("Starting to clear all assessment cache entries")

        with self.get_connection() as conn:
            cursor = conn.execute("DELETE FROM assessment_cache")
            conn.commit()
            cleared_count: int = cursor.rowcount
            detail_logger.debug(
                f"Assessment cache cleared: {cleared_count} entries removed"
            )
            return cleared_count
