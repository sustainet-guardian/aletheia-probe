# SPDX-License-Identifier: MIT
"""Article retraction tracking for the cache system."""

import json
import sqlite3
from datetime import datetime, timedelta
from typing import Any

from ..logging_config import get_detail_logger
from .base import CacheBase


detail_logger = get_detail_logger()


class RetractionCache(CacheBase):
    """Manages article retraction information caching."""

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

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT doi, is_retracted, retraction_type, retraction_date,
                       retraction_doi, retraction_reason, source, metadata,
                       checked_at, expires_at
                FROM article_retractions
                WHERE doi = ? AND expires_at > CURRENT_TIMESTAMP
                """,
                (normalized_doi,),
            )

            row = cursor.fetchone()
            if row:
                result = dict(row)
                # Parse JSON metadata if present
                if result.get("metadata"):
                    try:
                        result["metadata"] = json.loads(result["metadata"])
                        detail_logger.debug(f"Parsed JSON metadata for DOI '{normalized_doi}'")
                    except json.JSONDecodeError:
                        detail_logger.debug(
                            f"Failed to parse JSON metadata for DOI '{normalized_doi}'"
                        )
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
        metadata: dict[str, Any] | None = None,
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
            metadata: Additional metadata as JSON
            ttl_hours: Cache TTL in hours
        """
        normalized_doi = doi.lower().strip()
        expires_at = datetime.now() + timedelta(hours=ttl_hours)
        detail_logger.debug(
            f"Caching retraction info for DOI '{doi}' (normalized: '{normalized_doi}'): "
            f"is_retracted={is_retracted}, source={source}, ttl_hours={ttl_hours}"
        )

        metadata_json = json.dumps(metadata) if metadata else None
        if metadata:
            detail_logger.debug(f"Serialized metadata to JSON for DOI '{normalized_doi}'")

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO article_retractions
                (doi, is_retracted, retraction_type, retraction_date, retraction_doi,
                 retraction_reason, source, metadata, checked_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
                """,
                (
                    normalized_doi,
                    is_retracted,
                    retraction_type,
                    retraction_date,
                    retraction_doi,
                    retraction_reason,
                    source,
                    metadata_json,
                    expires_at.isoformat(),
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

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                DELETE FROM article_retractions
                WHERE expires_at <= CURRENT_TIMESTAMP
                """
            )
            conn.commit()
            removed_count = cursor.rowcount

            detail_logger.debug(
                f"Cleanup completed: removed {removed_count} expired retraction entries"
            )

            return removed_count
