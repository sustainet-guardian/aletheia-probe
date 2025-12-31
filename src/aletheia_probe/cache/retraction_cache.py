# SPDX-License-Identifier: MIT
"""Article retraction tracking and journal retraction statistics for the cache system."""

import json
from datetime import datetime, timedelta
from typing import Any

from ..logging_config import get_detail_logger
from .base import CacheBase


detail_logger = get_detail_logger()


class RetractionCache(CacheBase):
    """Manages article retraction information and journal retraction statistics caching."""

    def get_article_retraction(self, doi: str) -> dict[str, Any] | None:
        """Get cached retraction information for a DOI.

        Args:
            doi: The DOI to check (will be normalized)

        Returns:
            Dictionary with retraction info if found and not expired, None otherwise
        """
        normalized_doi = doi.lower().strip()
        detail_logger.debug(
            f"Looking up retraction info for DOI '{doi}' (normalized: '{normalized_doi}')"
        )

        with self.get_connection_with_row_factory() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT doi, is_retracted, retraction_type, retraction_date,
                       retraction_doi, retraction_reason, source,
                       checked_at, expires_at
                FROM article_retractions
                WHERE doi = ? AND expires_at > CURRENT_TIMESTAMP
                """,
                (normalized_doi,),
            )

            row = cursor.fetchone()
            if row:
                result = dict(row)
                # Convert SQLite boolean fields to Python bool types
                result["is_retracted"] = bool(result["is_retracted"])
                detail_logger.debug(
                    f"Cache hit for DOI '{normalized_doi}': "
                    f"is_retracted={result['is_retracted']}, source={result['source']}"
                )
                return result
            detail_logger.debug(
                f"Cache miss for DOI '{normalized_doi}' (not found or expired)"
            )
            return None

    def cache_article_retraction(
        self,
        doi: str,
        is_retracted: bool,
        source: str,
        retraction_type: str | None = None,
        retraction_date: str | None = None,
        retraction_doi: str | None = None,
        retraction_reason: str | None = None,
        ttl_hours: int = 24 * 30,  # 30 days default
    ) -> None:
        """Cache retraction information for a DOI.

        Args:
            doi: The DOI to cache
            is_retracted: Whether the article is retracted
            source: Source of the retraction information (e.g., 'crossref', 'retraction_watch')
            retraction_type: Type of retraction (e.g., 'retraction', 'correction', 'expression_of_concern')
            retraction_date: Date of retraction
            retraction_doi: DOI of the retraction notice
            retraction_reason: Reason for retraction
            ttl_hours: Cache TTL in hours
        """
        normalized_doi = doi.lower().strip()
        expires_at = datetime.utcnow() + timedelta(hours=ttl_hours)
        detail_logger.debug(
            f"Caching retraction info for DOI '{doi}' (normalized: '{normalized_doi}'): "
            f"is_retracted={is_retracted}, source={source}, ttl_hours={ttl_hours}"
        )

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO article_retractions
                (doi, is_retracted, retraction_type, retraction_date, retraction_doi,
                 retraction_reason, source, checked_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
                """,
                (
                    normalized_doi,
                    is_retracted,
                    retraction_type,
                    retraction_date,
                    retraction_doi,
                    retraction_reason,
                    source,
                    expires_at.strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )
            conn.commit()
            detail_logger.debug(
                f"Successfully cached retraction info for DOI '{normalized_doi}'"
            )

    def cleanup_expired_article_retractions(self) -> int:
        """Remove expired article retraction cache entries.

        Returns:
            Number of entries removed
        """
        detail_logger.debug("Starting cleanup of expired article retraction entries")

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                DELETE FROM article_retractions
                WHERE expires_at <= CURRENT_TIMESTAMP
                """
            )
            conn.commit()
            removed_count = int(cursor.rowcount)

            detail_logger.debug(
                f"Cleanup completed: removed {removed_count} expired retraction entries"
            )

            return removed_count

    def upsert_retraction_statistics(
        self,
        journal_id: int,
        total_retractions: int,
        recent_retractions: int,
        very_recent_retractions: int,
        retraction_types: dict[str, int] | None = None,
        top_reasons: list[tuple[str, int]] | None = None,
        publishers: list[str] | None = None,
        first_retraction_date: str | None = None,
        last_retraction_date: str | None = None,
    ) -> None:
        """Insert or update retraction statistics for a journal.

        Args:
            journal_id: Journal database ID
            total_retractions: Total number of retractions
            recent_retractions: Number of retractions in last 2 years
            very_recent_retractions: Number of retractions in last 1 year
            retraction_types: Dictionary of retraction types and counts (stored as JSON)
            top_reasons: List of (reason, count) tuples (stored as JSON)
            publishers: List of publishers (stored as JSON)
            first_retraction_date: First retraction date (ISO format)
            last_retraction_date: Last retraction date (ISO format)
        """
        detail_logger.debug(
            f"Upserting retraction statistics for journal_id {journal_id}: "
            f"total={total_retractions}, recent={recent_retractions}"
        )

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO retraction_statistics
                (journal_id, total_retractions, recent_retractions, very_recent_retractions,
                 retraction_types, top_reasons, publishers, first_retraction_date,
                 last_retraction_date, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT(journal_id) DO UPDATE SET
                    total_retractions = excluded.total_retractions,
                    recent_retractions = excluded.recent_retractions,
                    very_recent_retractions = excluded.very_recent_retractions,
                    retraction_types = excluded.retraction_types,
                    top_reasons = excluded.top_reasons,
                    publishers = excluded.publishers,
                    first_retraction_date = excluded.first_retraction_date,
                    last_retraction_date = excluded.last_retraction_date,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    journal_id,
                    total_retractions,
                    recent_retractions,
                    very_recent_retractions,
                    json.dumps(retraction_types) if retraction_types else None,
                    json.dumps(top_reasons) if top_reasons else None,
                    json.dumps(publishers) if publishers else None,
                    first_retraction_date,
                    last_retraction_date,
                ),
            )
            conn.commit()
            detail_logger.debug(
                f"Successfully upserted retraction statistics for journal_id {journal_id}"
            )

    def get_retraction_statistics(self, journal_id: int) -> dict[str, Any] | None:
        """Get retraction statistics for a journal.

        Args:
            journal_id: Journal database ID

        Returns:
            Dictionary with retraction statistics if found, None otherwise
        """
        detail_logger.debug(
            f"Looking up retraction statistics for journal_id {journal_id}"
        )

        with self.get_connection_with_row_factory() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT journal_id, total_retractions, recent_retractions,
                       very_recent_retractions, retraction_types, top_reasons,
                       publishers, first_retraction_date, last_retraction_date,
                       created_at, updated_at
                FROM retraction_statistics
                WHERE journal_id = ?
                """,
                (journal_id,),
            )

            row = cursor.fetchone()
            if row:
                result = dict(row)
                # Parse JSON fields
                if result.get("retraction_types"):
                    result["retraction_types"] = json.loads(result["retraction_types"])
                if result.get("top_reasons"):
                    result["top_reasons"] = json.loads(result["top_reasons"])
                if result.get("publishers"):
                    result["publishers"] = json.loads(result["publishers"])

                detail_logger.debug(
                    f"Found retraction statistics for journal_id {journal_id}: "
                    f"total={result['total_retractions']}, recent={result['recent_retractions']}"
                )
                return result

            detail_logger.debug(
                f"No retraction statistics found for journal_id {journal_id}"
            )
            return None
