# SPDX-License-Identifier: MIT
"""Article retraction tracking for the cache system."""

import json
import sqlite3
from datetime import datetime, timedelta
from typing import Any

from .base import CacheBase


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
                    except json.JSONDecodeError:
                        pass
                return result
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

        metadata_json = json.dumps(metadata) if metadata else None

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

    def cleanup_expired_article_retractions(self) -> int:
        """Remove expired article retraction cache entries.

        Returns:
            Number of entries removed
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                DELETE FROM article_retractions
                WHERE expires_at <= CURRENT_TIMESTAMP
                """
            )
            conn.commit()
            return cursor.rowcount
