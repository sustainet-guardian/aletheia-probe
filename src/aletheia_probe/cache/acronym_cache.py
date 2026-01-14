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
from typing import Any

from ..logging_config import get_detail_logger, get_status_logger
from ..normalizer import are_conference_names_equivalent, input_normalizer
from .base import CacheBase


detail_logger = get_detail_logger()
status_logger = get_status_logger()


class AcronymCache(CacheBase):
    """Manages venue acronym to full name mappings."""

    def get_full_name_for_acronym(self, acronym: str, entity_type: str) -> str | None:
        """Look up the normalized name for a venue acronym using variant system.

        Args:
            acronym: The acronym to look up (e.g., 'ICML', 'JMLR')
            entity_type: VenueType value (e.g., 'journal', 'conference', 'workshop')

        Returns:
            Canonical normalized name if found and not ambiguous, None otherwise
        """
        detail_logger.debug(
            f"Looking up acronym '{acronym}' for entity_type '{entity_type}'"
        )

        with self.get_connection_with_row_factory() as conn:
            cursor = conn.cursor()

            # Get canonical variant
            cursor.execute(
                """
                SELECT normalized_name, is_ambiguous FROM venue_acronym_variants
                WHERE acronym = ? COLLATE NOCASE
                  AND entity_type = ?
                  AND is_canonical = TRUE
                """,
                (acronym.strip(), entity_type),
            )

            row = cursor.fetchone()
            if row:
                # Check if acronym is ambiguous
                if row["is_ambiguous"]:
                    detail_logger.debug(
                        f"Acronym '{acronym}' is ambiguous (maps to multiple venues), cannot be used for matching"
                    )
                    status_logger.warning(
                        f"Acronym '{acronym}' is ambiguous and cannot be used for automatic matching"
                    )
                    return None

                detail_logger.debug(
                    f"Found canonical mapping for '{acronym}' -> '{row['normalized_name']}'"
                )
                # Update last_seen_at timestamp
                cursor.execute(
                    """
                    UPDATE venue_acronym_variants
                    SET last_seen_at = CURRENT_TIMESTAMP
                    WHERE acronym = ? COLLATE NOCASE
                      AND entity_type = ?
                      AND is_canonical = TRUE
                    """,
                    (acronym.strip(), entity_type),
                )
                conn.commit()
                detail_logger.debug(
                    f"Updated last_seen_at timestamp for acronym '{acronym}'"
                )
                return str(row["normalized_name"])
            else:
                detail_logger.debug(
                    f"No canonical mapping found for acronym '{acronym}' with entity_type '{entity_type}'"
                )
            return None

    def _normalize_venue_name(self, full_name: str) -> str:
        """Normalize venue name to generic series form.

        Args:
            full_name: The full venue name (may include year/edition)

        Returns:
            Normalized venue name
        """
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

        return normalized_name

    def _check_existing_mapping(
        self,
        cursor: sqlite3.Cursor,
        acronym: str,
        entity_type: str,
        normalized_name: str,
    ) -> None:
        """Check for existing mapping and log conflicts if necessary.

        Args:
            cursor: Database cursor
            acronym: The acronym to check
            entity_type: VenueType value
            normalized_name: The normalized name to compare against existing mapping
        """
        # Check for existing mapping with same acronym and entity_type
        detail_logger.debug(
            f"Checking for existing mapping of acronym '{acronym}' with entity_type '{entity_type}'"
        )
        cursor.execute(
            """
            SELECT normalized_name FROM venue_acronym_variants
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
                    detail_logger.debug("Names are equivalent, proceeding with update")
            else:
                detail_logger.debug(
                    f"Mapping unchanged: '{acronym}' -> '{normalized_name}'"
                )
        else:
            detail_logger.debug(
                f"No existing mapping found for '{acronym}' with entity_type '{entity_type}'"
            )

    def _store_mapping(
        self,
        cursor: sqlite3.Cursor,
        acronym: str,
        normalized_name: str,
        entity_type: str,
        source: str,
    ) -> None:
        """Store the mapping to the database using new variant system.

        Args:
            cursor: Database cursor
            acronym: The acronym
            normalized_name: The normalized name
            entity_type: VenueType value
            source: Source of the mapping
        """
        # Insert or update using new variant system
        detail_logger.debug(
            f"Storing acronym mapping: '{acronym}' -> '{normalized_name}' (entity_type: {entity_type})"
        )

        # Check if variant already exists
        cursor.execute(
            """
            SELECT id, usage_count FROM venue_acronym_variants
            WHERE acronym = ? COLLATE NOCASE
              AND entity_type = ?
              AND normalized_name = ?
            """,
            (acronym.strip(), entity_type, normalized_name),
        )
        existing = cursor.fetchone()

        if existing:
            # Update existing variant
            cursor.execute(
                """
                UPDATE venue_acronym_variants
                SET usage_count = usage_count + 1,
                    last_seen_at = CURRENT_TIMESTAMP,
                    is_canonical = TRUE
                WHERE id = ?
                """,
                (existing["id"],),
            )
            detail_logger.debug(f"Updated existing variant {existing['id']}")
        else:
            # Check for any existing variants for this acronym
            cursor.execute(
                """
                SELECT id, normalized_name FROM venue_acronym_variants
                WHERE acronym = ? COLLATE NOCASE AND entity_type = ?
                """,
                (acronym.strip(), entity_type),
            )
            existing_variants = cursor.fetchall()

            # For backward compatibility: if there are existing non-equivalent variants,
            # delete them (this mimics the old INSERT OR REPLACE behavior)
            for variant in existing_variants:
                if not are_conference_names_equivalent(
                    variant["normalized_name"], normalized_name
                ):
                    cursor.execute(
                        "DELETE FROM venue_acronym_variants WHERE id = ?",
                        (variant["id"],),
                    )
                    detail_logger.debug(
                        f"Deleted non-equivalent variant {variant['id']}"
                    )

            # Insert new variant
            cursor.execute(
                """
                INSERT INTO venue_acronym_variants
                (acronym, entity_type, variant_name, normalized_name, usage_count, source, is_canonical)
                VALUES (?, ?, ?, ?, 1, ?, TRUE)
                """,
                (
                    acronym.strip(),
                    entity_type,
                    normalized_name,
                    normalized_name,
                    source,
                ),
            )
            variant_id = cursor.lastrowid
            detail_logger.debug(f"Inserted new variant {variant_id} as canonical")

        detail_logger.debug("Successfully stored acronym mapping to database")

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
        acronym = acronym.strip()
        full_name = full_name.strip()

        detail_logger.debug(
            f"Storing acronym mapping: '{acronym}' -> '{full_name}' (entity_type: {entity_type}, source: {source})"
        )

        normalized_name = self._normalize_venue_name(full_name)

        with self.get_connection_with_row_factory() as conn:
            cursor = conn.cursor()

            self._check_existing_mapping(cursor, acronym, entity_type, normalized_name)
            self._store_mapping(cursor, acronym, normalized_name, entity_type, source)

            conn.commit()

    def get_acronym_stats(self, entity_type: str | None = None) -> dict[str, int]:
        """Get statistics about the acronym database.

        Args:
            entity_type: Optional VenueType value to filter by (e.g., 'journal', 'conference').
                        If None, returns stats for all entity types.

        Returns:
            Dictionary containing total_count
        """
        with self.get_connection_with_row_factory() as conn:
            cursor = conn.cursor()

            if entity_type:
                cursor.execute(
                    "SELECT COUNT(*) as count FROM venue_acronym_variants WHERE entity_type = ?",
                    (entity_type,),
                )
            else:
                cursor.execute("SELECT COUNT(*) as count FROM venue_acronym_variants")

            count = cursor.fetchone()["count"]
            detail_logger.debug(f"Total acronym count: {count}")

            return {"total_count": count}

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

        with self.get_connection_with_row_factory() as conn:
            cursor = conn.cursor()

            params: list[str | int]
            if entity_type:
                query = """
                    SELECT acronym, normalized_name, entity_type, usage_count
                    FROM venue_acronym_variants
                    WHERE entity_type = ?
                    ORDER BY acronym ASC
                """
                params = [entity_type]
                detail_logger.debug(
                    f"Querying acronyms filtered by entity_type '{entity_type}'"
                )
            else:
                query = """
                    SELECT acronym, normalized_name, entity_type, usage_count
                    FROM venue_acronym_variants
                    ORDER BY acronym ASC
                """
                params = []
                detail_logger.debug("Querying all acronyms across all entity types")

            if limit is not None:
                query += " LIMIT ? OFFSET ?"
                params.extend([limit, offset])
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
                    "usage_count": row["usage_count"],
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

        with self.get_connection() as conn:
            cursor = conn.cursor()

            if entity_type:
                # Get count before deletion
                cursor.execute(
                    "SELECT COUNT(*) FROM venue_acronym_variants WHERE entity_type = ?",
                    (entity_type,),
                )
                result = cursor.fetchone()
                count = result[0] if result else 0
                detail_logger.debug(
                    f"Found {count} entries to delete for entity_type '{entity_type}'"
                )

                # Delete entries for specific entity type
                cursor.execute(
                    "DELETE FROM venue_acronym_variants WHERE entity_type = ?",
                    (entity_type,),
                )
                detail_logger.debug(f"Deleted entries for entity_type '{entity_type}'")
            else:
                # Get count before deletion
                cursor.execute("SELECT COUNT(*) FROM venue_acronym_variants")
                result = cursor.fetchone()
                count = result[0] if result else 0
                detail_logger.debug(f"Found {count} total entries to delete")

                # Delete all entries
                cursor.execute("DELETE FROM venue_acronym_variants")
                detail_logger.debug("Deleted all entries from acronym database")

            conn.commit()
            detail_logger.debug(
                f"Database clear operation completed, {count} entries deleted"
            )
            return count

    def mark_acronym_as_ambiguous(
        self, acronym: str, entity_type: str, venues: list[str] | None = None
    ) -> None:
        """Mark an acronym as ambiguous (maps to multiple venues).

        Args:
            acronym: The acronym to mark as ambiguous
            entity_type: VenueType value (e.g., 'journal', 'conference')
            venues: Optional list of conflicting venue names for logging
        """
        detail_logger.debug(
            f"Marking acronym '{acronym}' (entity_type={entity_type}) as ambiguous"
        )

        if venues:
            status_logger.warning(
                f"Acronym '{acronym}' is ambiguous - maps to multiple venues: {', '.join(venues)}"
            )
        else:
            status_logger.warning(
                f"Acronym '{acronym}' (entity_type={entity_type}) marked as ambiguous"
            )

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE venue_acronym_variants
                SET is_ambiguous = TRUE
                WHERE acronym = ? COLLATE NOCASE AND entity_type = ?
                """,
                (acronym.strip(), entity_type),
            )
            conn.commit()
            detail_logger.debug(f"Marked acronym '{acronym}' as ambiguous in database")

    def check_acronym_conflict(
        self, acronym: str, entity_type: str, normalized_name: str
    ) -> tuple[bool, bool, str | None]:
        """Check if storing this acronym would create a conflict.

        Args:
            acronym: The acronym to check
            entity_type: VenueType value
            normalized_name: The normalized venue name

        Returns:
            Tuple of (has_conflict, already_exists, existing_name)
            - has_conflict: True if acronym exists with different non-equivalent normalized_name
            - already_exists: True if acronym exists with same or equivalent normalized_name
            - existing_name: The existing normalized_name if found, None otherwise
        """
        detail_logger.debug(
            f"Checking for conflict: '{acronym}' (entity_type={entity_type}) -> '{normalized_name}'"
        )

        with self.get_connection_with_row_factory() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT normalized_name FROM venue_acronym_variants
                WHERE acronym = ? COLLATE NOCASE AND entity_type = ?
                """,
                (acronym.strip(), entity_type),
            )

            row = cursor.fetchone()
            if row:
                existing_name = str(row["normalized_name"])
                if existing_name == normalized_name:
                    detail_logger.debug("Acronym already mapped to same venue")
                    return False, True, existing_name  # No conflict, already exists
                elif are_conference_names_equivalent(existing_name, normalized_name):
                    detail_logger.debug(
                        f"Names are equivalent variants: '{existing_name}' ≈ '{normalized_name}'"
                    )
                    return False, True, existing_name  # No conflict, equivalent exists
                else:
                    detail_logger.debug(
                        f"Conflict detected: existing '{existing_name}' != new '{normalized_name}'"
                    )
                    return True, False, existing_name  # Conflict detected
            else:
                detail_logger.debug("No existing mapping found")
                return False, False, None  # New acronym

    def list_ambiguous_acronyms(
        self, entity_type: str | None = None
    ) -> list[dict[str, str]]:
        """List all acronyms marked as ambiguous.

        Args:
            entity_type: Optional VenueType value to filter by

        Returns:
            List of dictionaries containing ambiguous acronym details
        """
        detail_logger.debug(
            f"Listing ambiguous acronyms (entity_type={entity_type or 'all'})"
        )

        with self.get_connection_with_row_factory() as conn:
            cursor = conn.cursor()

            if entity_type:
                query = """
                    SELECT acronym, normalized_name, entity_type, usage_count
                    FROM venue_acronym_variants
                    WHERE is_ambiguous = TRUE AND entity_type = ?
                    ORDER BY acronym ASC
                """
                cursor.execute(query, (entity_type,))
            else:
                query = """
                    SELECT acronym, normalized_name, entity_type, usage_count
                    FROM venue_acronym_variants
                    WHERE is_ambiguous = TRUE
                    ORDER BY acronym ASC
                """
                cursor.execute(query)

            rows = cursor.fetchall()
            detail_logger.debug(f"Found {len(rows)} ambiguous acronym entries")

            return [
                {
                    "acronym": row["acronym"],
                    "normalized_name": row["normalized_name"],
                    "entity_type": row["entity_type"],
                    "usage_count": row["usage_count"],
                }
                for row in rows
            ]

    def increment_usage_count(self, acronym: str, entity_type: str) -> None:
        """Increment the usage count for an acronym.

        Args:
            acronym: The acronym to increment
            entity_type: VenueType value (e.g., 'journal', 'conference')
        """
        detail_logger.debug(
            f"Incrementing usage count for '{acronym}' (entity_type={entity_type})"
        )

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE venue_acronym_variants
                SET usage_count = usage_count + 1, last_seen_at = CURRENT_TIMESTAMP
                WHERE acronym = ? COLLATE NOCASE AND entity_type = ?
                """,
                (acronym.strip(), entity_type),
            )
            conn.commit()
            detail_logger.debug(
                f"Incremented usage count for acronym '{acronym}' (entity_type={entity_type})"
            )

    # ========== Variant Management Methods ==========

    def get_variants(self, acronym: str, entity_type: str) -> list[dict[str, Any]]:
        """Get all variants for an acronym.

        Args:
            acronym: The acronym to look up
            entity_type: VenueType value

        Returns:
            List of variant records as dictionaries
        """
        with self.get_connection_with_row_factory() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, acronym, entity_type, variant_name, normalized_name,
                       usage_count, is_canonical, is_ambiguous, source,
                       first_seen_at, last_seen_at
                FROM venue_acronym_variants
                WHERE acronym = ? COLLATE NOCASE AND entity_type = ?
                ORDER BY usage_count DESC, id ASC
                """,
                (acronym.strip(), entity_type),
            )
            return [dict(row) for row in cursor.fetchall()]

    def store_variant(
        self,
        acronym: str,
        entity_type: str,
        variant_name: str,
        normalized_name: str,
        usage_count: int,
        source: str,
    ) -> int:
        """Store a new variant or update existing one.

        Args:
            acronym: The acronym
            entity_type: VenueType value
            variant_name: Original form
            normalized_name: Normalized form for comparison
            usage_count: Number of occurrences
            source: Source of mapping

        Returns:
            variant_id of the stored/updated variant
        """
        with self.get_connection_with_row_factory() as conn:
            cursor = conn.cursor()

            # Check if variant already exists
            cursor.execute(
                """
                SELECT id, usage_count FROM venue_acronym_variants
                WHERE acronym = ? COLLATE NOCASE
                  AND entity_type = ?
                  AND normalized_name = ?
                """,
                (acronym.strip(), entity_type, normalized_name),
            )
            existing = cursor.fetchone()

            if existing:
                # Update existing variant
                variant_id = int(existing["id"])
                new_count = existing["usage_count"] + usage_count
                cursor.execute(
                    """
                    UPDATE venue_acronym_variants
                    SET usage_count = ?,
                        last_seen_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (new_count, variant_id),
                )
                detail_logger.debug(
                    f"Updated variant {variant_id}: usage_count {existing['usage_count']} -> {new_count}"
                )
            else:
                # Insert new variant
                cursor.execute(
                    """
                    INSERT INTO venue_acronym_variants
                    (acronym, entity_type, variant_name, normalized_name,
                     usage_count, source)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        acronym.strip(),
                        entity_type,
                        variant_name,
                        normalized_name,
                        usage_count,
                        source,
                    ),
                )
                variant_id = int(cursor.lastrowid)
                detail_logger.debug(
                    f"Inserted new variant {variant_id}: '{variant_name}' (normalized: '{normalized_name}')"
                )

            conn.commit()
            return variant_id

    def increment_variant_count(self, variant_id: int, increment: int = 1) -> None:
        """Increment usage count for an existing variant.

        Args:
            variant_id: Database ID of the variant
            increment: Amount to increment by
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE venue_acronym_variants
                SET usage_count = usage_count + ?,
                    last_seen_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (increment, variant_id),
            )
            conn.commit()
            detail_logger.debug(
                f"Incremented variant {variant_id} usage_count by {increment}"
            )

    def update_canonical_variant(self, acronym: str, entity_type: str) -> None:
        """Recalculate and set canonical variant (highest usage_count).

        Args:
            acronym: The acronym
            entity_type: VenueType value
        """
        with self.get_connection_with_row_factory() as conn:
            cursor = conn.cursor()

            # First, clear all canonical flags for this acronym
            cursor.execute(
                """
                UPDATE venue_acronym_variants
                SET is_canonical = FALSE
                WHERE acronym = ? COLLATE NOCASE AND entity_type = ?
                """,
                (acronym.strip(), entity_type),
            )

            # Find the variant with highest usage_count
            cursor.execute(
                """
                SELECT id, usage_count FROM venue_acronym_variants
                WHERE acronym = ? COLLATE NOCASE AND entity_type = ?
                ORDER BY usage_count DESC, id ASC
                LIMIT 1
                """,
                (acronym.strip(), entity_type),
            )
            top_variant = cursor.fetchone()

            if top_variant:
                # Set this variant as canonical
                cursor.execute(
                    """
                    UPDATE venue_acronym_variants
                    SET is_canonical = TRUE
                    WHERE id = ?
                    """,
                    (top_variant["id"],),
                )
                detail_logger.debug(
                    f"Set variant {top_variant['id']} as canonical (usage_count={top_variant['usage_count']})"
                )

            conn.commit()

    # ========== Learned Abbreviation Methods ==========

    def get_learned_abbreviations(
        self, min_confidence: float = 0.05
    ) -> dict[str, list[tuple[str, float]]]:
        """Get abbreviation mappings above confidence threshold.

        Args:
            min_confidence: Minimum confidence score to include

        Returns:
            dict mapping abbreviated form to list of (expanded_form, confidence) tuples
            Example: {
                "int.": [("international", 0.9), ("integer", 0.3)],
                "conf.": [("conference", 0.95)]
            }
        """
        with self.get_connection_with_row_factory() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT abbreviated_form, expanded_form, confidence_score
                FROM learned_abbreviations
                WHERE confidence_score >= ?
                ORDER BY abbreviated_form, confidence_score DESC
                """,
                (min_confidence,),
            )

            result: dict[str, list[tuple[str, float]]] = {}
            for row in cursor.fetchall():
                abbrev = row["abbreviated_form"]
                expanded = row["expanded_form"]
                confidence = row["confidence_score"]

                if abbrev not in result:
                    result[abbrev] = []
                result[abbrev].append((expanded, confidence))

            detail_logger.debug(
                f"Loaded {len(result)} abbreviations with min_confidence >= {min_confidence}"
            )
            return result

    def store_learned_abbreviation(
        self,
        abbrev: str,
        expanded: str,
        confidence: float,
        context: str | None = None,
        log_prefix: str = "",
    ) -> None:
        """Store or update a learned abbreviation mapping.

        Args:
            abbrev: Abbreviated form
            expanded: Expanded form
            confidence: Initial confidence score
            context: Optional context (venue type, etc.)
            log_prefix: Optional prefix for log messages (e.g., file path)
        """
        import math

        with self.get_connection_with_row_factory() as conn:
            cursor = conn.cursor()

            # Check if mapping already exists
            cursor.execute(
                """
                SELECT occurrence_count FROM learned_abbreviations
                WHERE abbreviated_form = ? AND expanded_form = ?
                """,
                (abbrev, expanded),
            )
            existing = cursor.fetchone()

            if existing:
                # Update existing mapping
                new_count = existing["occurrence_count"] + 1
                # Recalculate confidence using logarithmic formula
                new_confidence = min(1.0, 0.1 + 0.3 * math.log10(new_count + 1))

                cursor.execute(
                    """
                    UPDATE learned_abbreviations
                    SET occurrence_count = ?,
                        confidence_score = ?,
                        last_seen_at = CURRENT_TIMESTAMP
                    WHERE abbreviated_form = ? AND expanded_form = ?
                    """,
                    (new_count, new_confidence, abbrev, expanded),
                )
                status_logger.info(
                    f"{log_prefix}updated abbrev '{abbrev}' → '{expanded}' "
                    f"(confidence: {new_confidence:.2f}, count: {new_count})"
                )
            else:
                # Insert new mapping
                cursor.execute(
                    """
                    INSERT INTO learned_abbreviations
                    (abbreviated_form, expanded_form, confidence_score,
                     occurrence_count, context)
                    VALUES (?, ?, ?, 1, ?)
                    """,
                    (abbrev, expanded, confidence, context),
                )
                status_logger.info(
                    f"{log_prefix}learned abbrev '{abbrev}' → '{expanded}' "
                    f"(confidence: {confidence:.2f}, count: 1)"
                )

            conn.commit()

    def get_abbreviation_confidence(self, abbrev: str, expanded: str) -> float:
        """Get confidence score for a specific mapping.

        Args:
            abbrev: Abbreviated form
            expanded: Expanded form

        Returns:
            Confidence score (0.0-1.0), or 0.0 if mapping doesn't exist
        """
        with self.get_connection_with_row_factory() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT confidence_score FROM learned_abbreviations
                WHERE abbreviated_form = ? AND expanded_form = ?
                """,
                (abbrev, expanded),
            )
            row = cursor.fetchone()
            return float(row["confidence_score"]) if row else 0.0
