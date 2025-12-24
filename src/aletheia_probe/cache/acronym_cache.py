# SPDX-License-Identifier: MIT
"""Venue acronym caching for journals, conferences, and other publication types.

Design Decision: Single Table Approach
=====================================
This module uses a single 'acronyms' table to store acronym mappings for all venue types
(journals, conferences, workshops, symposia, etc.) rather than separate tables per type.

Rationale:
- Reduces database complexity and maintenance overhead
- Simplifies codebase with unified storage/retrieval logic
- Venue type distinction is preserved via the entity_type column
- No performance benefits from multiple tables for this use case
- Easier to query across all venue types when needed

Having multiple tables would increase database and code complexity without any real
positive effect while making cross-venue queries more difficult.
"""

import re
import sqlite3

from ..logging_config import get_detail_logger
from ..normalizer import are_conference_names_equivalent
from .base import CacheBase


detail_logger = get_detail_logger()


class AcronymCache(CacheBase):
    """Manages venue acronym to full name mappings."""

    def get_full_name_for_acronym(self, acronym: str, entity_type: str) -> str | None:
        """Look up the normalized name for a venue acronym.

        Args:
            acronym: The acronym to look up (e.g., 'ICML', 'JMLR')
            entity_type: VenueType value (e.g., 'journal', 'conference', 'workshop')

        Returns:
            Normalized name if found in cache, None otherwise
        """
        detail_logger.debug(
            f"Looking up acronym '{acronym}' for entity_type '{entity_type}'"
        )

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT normalized_name FROM venue_acronyms
                WHERE acronym = ? COLLATE NOCASE AND entity_type = ?
                """,
                (acronym.strip(), entity_type),
            )

            row = cursor.fetchone()
            if row:
                detail_logger.debug(
                    f"Found mapping for '{acronym}' -> '{row['normalized_name']}'"
                )
                # Update last_used_at timestamp
                cursor.execute(
                    """
                    UPDATE venue_acronyms
                    SET last_used_at = CURRENT_TIMESTAMP
                    WHERE acronym = ? COLLATE NOCASE AND entity_type = ?
                    """,
                    (acronym.strip(), entity_type),
                )
                conn.commit()
                detail_logger.debug(
                    f"Updated last_used_at timestamp for acronym '{acronym}'"
                )
                return str(row["normalized_name"])
            else:
                detail_logger.debug(
                    f"No mapping found for acronym '{acronym}' with entity_type '{entity_type}'"
                )
            return None

    def store_acronym_mapping(
        self,
        acronym: str,
        full_name: str,
        entity_type: str,
        source: str = "unknown",
    ) -> None:
        """Store an acronym to normalized name mapping in the cache.

        Automatically normalizes venue names to their generic series form
        by removing years, edition numbers, and "Proceedings of" prefixes.

        If the acronym already exists for this entity_type with a different normalized_name,
        it logs a warning and overwrites it, unless the names are essentially the same
        publication with minor variations (e.g., year prefix/suffix).

        Args:
            acronym: The acronym (e.g., 'ICML', 'JMLR')
            full_name: The full venue name (may include year/edition)
            entity_type: VenueType value (e.g., 'journal', 'conference', 'workshop')
            source: Source of the mapping ('bibtex_extraction', 'openalex_response', 'manual')
        """
        # Import inside method to avoid circular dependency issues
        from ..logging_config import get_status_logger
        from ..normalizer import input_normalizer

        status_logger = get_status_logger()

        acronym = acronym.strip()
        full_name = full_name.strip()

        detail_logger.debug(
            f"Storing acronym mapping: '{acronym}' -> '{full_name}' (entity_type: {entity_type}, source: {source})"
        )

        # Normalize the publication name to generic series form
        # This removes years, ordinals, and "Proceedings of" prefix
        series_name = input_normalizer.extract_conference_series(full_name.lower())

        if series_name:
            # Use the extracted series name
            normalized_name = re.sub(r"\s+", " ", series_name).strip()
            detail_logger.debug(
                f"Normalized '{full_name}' -> '{normalized_name}' (extracted series name)"
            )
        else:
            # No normalization possible, use original (lowercased, whitespace normalized)
            normalized_name = re.sub(r"\s+", " ", full_name.lower()).strip()
            detail_logger.debug(
                f"Normalized '{full_name}' -> '{normalized_name}' (lowercased original)"
            )

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Check for existing mapping with same acronym and entity_type
            detail_logger.debug(
                f"Checking for existing mapping of acronym '{acronym}' with entity_type '{entity_type}'"
            )
            cursor.execute(
                """
                SELECT normalized_name FROM venue_acronyms
                WHERE acronym = ? COLLATE NOCASE AND entity_type = ?
                """,
                (acronym, entity_type),
            )

            existing = cursor.fetchone()
            if existing:
                detail_logger.debug(
                    f"Found existing mapping: '{acronym}' -> '{existing['normalized_name']}'"
                )
                if existing["normalized_name"] != normalized_name:
                    # Check if this is essentially the same publication with minor variations
                    if not are_conference_names_equivalent(
                        existing["normalized_name"], normalized_name
                    ):
                        detail_logger.debug(
                            "Names are not equivalent, will overwrite existing mapping"
                        )
                        status_logger.warning(
                            f"Acronym '{acronym}' (entity_type={entity_type}) already maps to '{existing['normalized_name']}', "
                            f"overwriting with '{normalized_name}'"
                        )
                    else:
                        detail_logger.debug(
                            "Names are equivalent, proceeding with update"
                        )
                else:
                    detail_logger.debug(
                        f"Mapping unchanged: '{acronym}' -> '{normalized_name}'"
                    )
            else:
                detail_logger.debug(
                    f"No existing mapping found for '{acronym}' with entity_type '{entity_type}'"
                )

            # Insert or replace the mapping with normalized form
            detail_logger.debug(
                f"Storing acronym mapping: '{acronym}' -> '{normalized_name}' (entity_type: {entity_type})"
            )
            cursor.execute(
                """
                INSERT OR REPLACE INTO venue_acronyms
                (acronym, normalized_name, entity_type, source, created_at, last_used_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (acronym, normalized_name, entity_type, source),
            )
            conn.commit()
            detail_logger.debug("Successfully stored acronym mapping to database")

    def get_acronym_stats(self, entity_type: str | None = None) -> dict[str, int | str]:
        """Get statistics about the acronym database.

        Args:
            entity_type: Optional VenueType value to filter by (e.g., 'journal', 'conference').
                        If None, returns stats for all entity types.

        Returns:
            Dictionary containing count, most_recent, and oldest entry info
        """
        if entity_type:
            detail_logger.debug(f"Getting stats for entity_type '{entity_type}'")
        else:
            detail_logger.debug("Getting stats for all entity types")

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            if entity_type:
                # Get stats for specific entity type
                cursor.execute(
                    "SELECT COUNT(*) as count FROM venue_acronyms WHERE entity_type = ?",
                    (entity_type,),
                )
                count = cursor.fetchone()["count"]
                detail_logger.debug(
                    f"Found {count} acronym entries for entity_type '{entity_type}'"
                )

                cursor.execute(
                    """
                    SELECT acronym, normalized_name, entity_type, last_used_at
                    FROM venue_acronyms
                    WHERE entity_type = ?
                    ORDER BY last_used_at DESC
                    LIMIT 1
                    """,
                    (entity_type,),
                )
                most_recent = cursor.fetchone()

                cursor.execute(
                    """
                    SELECT acronym, normalized_name, entity_type, created_at
                    FROM venue_acronyms
                    WHERE entity_type = ?
                    ORDER BY created_at ASC
                    LIMIT 1
                    """,
                    (entity_type,),
                )
                oldest = cursor.fetchone()
            else:
                # Get stats for all entity types
                cursor.execute("SELECT COUNT(*) as count FROM venue_acronyms")
                count = cursor.fetchone()["count"]
                detail_logger.debug(
                    f"Found {count} total acronym entries across all entity types"
                )

                cursor.execute(
                    """
                    SELECT acronym, normalized_name, entity_type, last_used_at
                    FROM venue_acronyms
                    ORDER BY last_used_at DESC
                    LIMIT 1
                    """
                )
                most_recent = cursor.fetchone()

                cursor.execute(
                    """
                    SELECT acronym, normalized_name, entity_type, created_at
                    FROM venue_acronyms
                    ORDER BY created_at ASC
                    LIMIT 1
                    """
                )
                oldest = cursor.fetchone()

            if most_recent:
                detail_logger.debug(
                    f"Most recent acronym: '{most_recent['acronym']}' -> '{most_recent['normalized_name']}' (last used: {most_recent['last_used_at']})"
                )
            if oldest:
                detail_logger.debug(
                    f"Oldest acronym: '{oldest['acronym']}' -> '{oldest['normalized_name']}' (created: {oldest['created_at']})"
                )

            stats = {"total_count": count}

            if most_recent:
                stats["most_recent_acronym"] = most_recent["acronym"]
                stats["most_recent_normalized_name"] = most_recent["normalized_name"]
                stats["most_recent_used"] = most_recent["last_used_at"]

            if oldest:
                stats["oldest_acronym"] = oldest["acronym"]
                stats["oldest_normalized_name"] = oldest["normalized_name"]
                stats["oldest_created"] = oldest["created_at"]

            return stats

    def list_all_acronyms(
        self, entity_type: str | None = None, limit: int | None = None, offset: int = 0
    ) -> list[dict[str, str]]:
        """List all acronym mappings in the database.

        Args:
            entity_type: Optional VenueType value to filter by (e.g., 'journal', 'conference').
                        If None, returns all acronyms across all entity types.
            limit: Maximum number of entries to return (None for all)
            offset: Number of entries to skip

        Returns:
            List of dictionaries containing acronym details

        Raises:
            TypeError: If limit or offset are not integers
        """
        # Validate types at runtime to prevent SQL injection
        if limit is not None and not isinstance(limit, int):
            raise TypeError(f"limit must be an integer, got {type(limit).__name__}")
        if not isinstance(offset, int):
            raise TypeError(f"offset must be an integer, got {type(offset).__name__}")

        detail_logger.debug(
            f"Listing acronyms with filters: entity_type={entity_type}, limit={limit}, offset={offset}"
        )

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            if entity_type:
                query = """
                    SELECT acronym, normalized_name, entity_type, source, created_at, last_used_at
                    FROM venue_acronyms
                    WHERE entity_type = ?
                    ORDER BY acronym ASC
                """
                params = [entity_type]
                detail_logger.debug(
                    f"Querying acronyms filtered by entity_type '{entity_type}'"
                )
            else:
                query = """
                    SELECT acronym, normalized_name, entity_type, source, created_at, last_used_at
                    FROM venue_acronyms
                    ORDER BY acronym ASC
                """
                params = []
                detail_logger.debug("Querying all acronyms across all entity types")

            if limit is not None:
                query += f" LIMIT {limit} OFFSET {offset}"
                detail_logger.debug(
                    f"Applied pagination: LIMIT {limit} OFFSET {offset}"
                )

            cursor.execute(query, params)
            rows = cursor.fetchall()
            detail_logger.debug(f"Retrieved {len(rows)} acronym entries from database")

            return [
                {
                    "acronym": row["acronym"],
                    "normalized_name": row["normalized_name"],
                    "entity_type": row["entity_type"],
                    "source": row["source"],
                    "created_at": row["created_at"],
                    "last_used_at": row["last_used_at"],
                }
                for row in rows
            ]

    def clear_acronym_database(self, entity_type: str | None = None) -> int:
        """Clear entries from the acronym database.

        Args:
            entity_type: Optional VenueType value to filter by (e.g., 'journal', 'conference').
                        If None, clears all acronyms across all entity types.

        Returns:
            Number of entries deleted
        """
        if entity_type:
            detail_logger.debug(
                f"Clearing acronym database for entity_type '{entity_type}'"
            )
        else:
            detail_logger.debug("Clearing entire acronym database")

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            if entity_type:
                # Get count before deletion
                cursor.execute(
                    "SELECT COUNT(*) FROM venue_acronyms WHERE entity_type = ?",
                    (entity_type,),
                )
                result = cursor.fetchone()
                count = result[0] if result else 0
                detail_logger.debug(
                    f"Found {count} entries to delete for entity_type '{entity_type}'"
                )

                # Delete entries for specific entity type
                cursor.execute(
                    "DELETE FROM venue_acronyms WHERE entity_type = ?", (entity_type,)
                )
                detail_logger.debug(f"Deleted entries for entity_type '{entity_type}'")
            else:
                # Get count before deletion
                cursor.execute("SELECT COUNT(*) FROM venue_acronyms")
                result = cursor.fetchone()
                count = result[0] if result else 0
                detail_logger.debug(f"Found {count} total entries to delete")

                # Delete all entries
                cursor.execute("DELETE FROM venue_acronyms")
                detail_logger.debug("Deleted all entries from acronym database")

            conn.commit()
            detail_logger.debug(
                f"Database clear operation completed, {count} entries deleted"
            )
            return count
