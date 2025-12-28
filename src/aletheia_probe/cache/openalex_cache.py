# SPDX-License-Identifier: MIT
"""OpenAlex caching for publication statistics."""

import json
import sqlite3
from datetime import datetime, timedelta
from typing import Any

from ..logging_config import get_detail_logger
from .base import CacheBase


detail_logger = get_detail_logger()


class OpenAlexCache(CacheBase):
    """Manages caching of OpenAlex publication statistics with structured schema."""

    def set_openalex_data(
        self,
        issn: str | None,
        journal_name: str | None,
        openalex_data: dict[str, Any],
        ttl_hours: int = 720,  # 30 days default
    ) -> None:
        """Store OpenAlex publication data in cache.

        Args:
            issn: ISSN for lookup (optional)
            journal_name: Normalized journal name for lookup (optional)
            openalex_data: Dictionary with OpenAlex publication statistics
            ttl_hours: Time-to-live in hours (default: 720 = 30 days)

        Raises:
            ValueError: If both issn and journal_name are None, or TTL is invalid
        """
        # Validate inputs
        if not issn and not journal_name:
            raise ValueError("Either issn or journal_name must be provided")

        if ttl_hours <= 0:
            raise ValueError("TTL must be positive")
        if ttl_hours > 8760:  # 365 days
            raise ValueError("TTL exceeds maximum allowed (8760 hours)")

        expires_at = datetime.now() + timedelta(hours=ttl_hours)

        # Extract structured fields from openalex_data
        openalex_id = openalex_data.get("openalex_id")
        openalex_url = openalex_data.get("openalex_url")
        display_name = openalex_data.get("display_name")
        source_type = openalex_data.get("source_type")
        issn_l = openalex_data.get("issn_l")
        issns = json.dumps(openalex_data.get("issns", []))
        total_publications = openalex_data.get("total_publications", 0)
        recent_publications = openalex_data.get("recent_publications", 0)
        recent_publications_by_year = json.dumps(
            openalex_data.get("recent_publications_by_year", {})
        )
        publisher = openalex_data.get("publisher")
        first_publication_year = openalex_data.get("first_publication_year")
        last_publication_year = openalex_data.get("last_publication_year")
        cited_by_count = openalex_data.get("cited_by_count", 0)
        is_in_doaj = openalex_data.get("is_in_doaj", False)
        fetched_at_str = openalex_data.get("fetched_at")

        # Parse fetched_at timestamp
        if fetched_at_str:
            try:
                fetched_at = datetime.fromisoformat(fetched_at_str)
            except (ValueError, TypeError):
                fetched_at = datetime.now()
        else:
            fetched_at = datetime.now()

        detail_logger.debug(
            f"Storing OpenAlex cache entry: issn={issn}, journal_name={journal_name}"
        )

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO openalex_cache (
                    issn, normalized_journal_name,
                    openalex_id, openalex_url, display_name, source_type,
                    issn_l, issns,
                    total_publications, recent_publications, recent_publications_by_year,
                    publisher, first_publication_year, last_publication_year,
                    cited_by_count, is_in_doaj,
                    fetched_at, expires_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    issn,
                    journal_name,
                    openalex_id,
                    openalex_url,
                    display_name,
                    source_type,
                    issn_l,
                    issns,
                    total_publications,
                    recent_publications,
                    recent_publications_by_year,
                    publisher,
                    first_publication_year,
                    last_publication_year,
                    cited_by_count,
                    is_in_doaj,
                    fetched_at,
                    expires_at,
                ),
            )
            conn.commit()
            detail_logger.debug(
                f"Successfully stored OpenAlex cache entry for issn={issn}, journal_name={journal_name}"
            )

    def get_openalex_data(
        self, issn: str | None = None, journal_name: str | None = None
    ) -> dict[str, Any] | None:
        """Get cached OpenAlex data by ISSN or journal name.

        Args:
            issn: ISSN to search for
            journal_name: Normalized journal name to search for

        Returns:
            Dictionary with OpenAlex publication statistics or None if not found/expired

        Raises:
            ValueError: If both issn and journal_name are None
        """
        if not issn and not journal_name:
            raise ValueError("Either issn or journal_name must be provided")

        detail_logger.debug(
            f"Looking up OpenAlex cache entry for issn={issn}, journal_name={journal_name}"
        )

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            # Build query based on available parameters
            params: tuple[str, ...] | tuple[str | None, ...]
            if issn and journal_name:
                query = """
                    SELECT * FROM openalex_cache
                    WHERE (issn = ? OR normalized_journal_name = ?)
                    AND expires_at > CURRENT_TIMESTAMP
                    ORDER BY created_at DESC
                    LIMIT 1
                """
                params = (issn, journal_name)
            elif issn:
                query = """
                    SELECT * FROM openalex_cache
                    WHERE issn = ? AND expires_at > CURRENT_TIMESTAMP
                    ORDER BY created_at DESC
                    LIMIT 1
                """
                params = (issn,)
            else:  # journal_name only
                query = """
                    SELECT * FROM openalex_cache
                    WHERE normalized_journal_name = ? AND expires_at > CURRENT_TIMESTAMP
                    ORDER BY created_at DESC
                    LIMIT 1
                """
                params = (journal_name,)

            cursor = conn.execute(query, params)
            row = cursor.fetchone()

            if not row:
                detail_logger.debug(
                    f"Cache miss for issn={issn}, journal_name={journal_name}"
                )
                return None

            detail_logger.debug(
                f"Cache hit for issn={issn}, journal_name={journal_name}"
            )

            # Reconstruct the openalex_data dictionary
            # Convert year keys from strings to integers (JSON serialization converts int keys to strings)
            recent_pubs_by_year = {}
            if row["recent_publications_by_year"]:
                year_data = json.loads(row["recent_publications_by_year"])
                recent_pubs_by_year = {int(year): count for year, count in year_data.items()}

            return {
                "openalex_id": row["openalex_id"],
                "openalex_url": row["openalex_url"],
                "display_name": row["display_name"],
                "source_type": row["source_type"],
                "issn_l": row["issn_l"],
                "issns": json.loads(row["issns"]) if row["issns"] else [],
                "total_publications": row["total_publications"],
                "recent_publications": row["recent_publications"],
                "recent_publications_by_year": recent_pubs_by_year,
                "publisher": row["publisher"],
                "first_publication_year": row["first_publication_year"],
                "last_publication_year": row["last_publication_year"],
                "cited_by_count": row["cited_by_count"],
                "is_in_doaj": bool(row["is_in_doaj"]),
                "fetched_at": row["fetched_at"],
            }

    def cleanup_expired_entries(self) -> int:
        """Remove expired cache entries.

        Returns:
            Number of entries removed
        """
        detail_logger.debug("Starting cleanup of expired OpenAlex cache entries")

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM openalex_cache WHERE expires_at <= CURRENT_TIMESTAMP"
            )
            removed_count = cursor.rowcount
            conn.commit()

            detail_logger.debug(
                f"Cleanup completed: removed {removed_count} expired OpenAlex entries"
            )

            return removed_count
