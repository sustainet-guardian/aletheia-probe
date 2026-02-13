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

    def import_variants(
        self,
        variants: list[dict[str, Any]],
        merge: bool = True,
        default_source: str = "import",
    ) -> int:
        """Import acronym variants into the database.

        Handles the venue-acronyms-2025 consensus format in addition to the
        standard export format:
          - Skips entries where normalized_name is null or empty
          - Falls back to "original_name" when "variant_name" is absent
          - Uses confidence_score × 100 as usage_count when usage_count is absent
          - Computes is_canonical and is_ambiguous from the batch after import

        Args:
            variants: List of variant dictionaries.
            merge: If True, merges with existing data (increments counts).
            default_source: Source string used when not present in variant data.

        Returns:
            Number of variants imported/updated.
        """
        if not variants:
            return 0

        detail_logger.debug(f"Importing {len(variants)} acronym variants")
        count = 0
        skipped_null = 0

        # Track unique (acronym, entity_type) pairs seen — used for the
        # post-import canonical + ambiguity pass (avoids redundant SQL per entry).
        seen_keys: set[tuple[str, str]] = set()

        for variant in variants:
            # Validate required fields
            if not all(
                k in variant for k in ["acronym", "entity_type", "normalized_name"]
            ):
                detail_logger.warning(f"Skipping invalid variant: {variant}")
                continue

            # Skip entries where the LLM produced no usable name
            if not variant["normalized_name"]:
                skipped_null += 1
                detail_logger.debug(
                    f"Skipping null normalized_name for {variant['acronym']!r}"
                )
                continue

            # variant_name: prefer explicit field, fall back to original_name
            # (venue-acronyms-2025 uses "original_name"), then normalized_name
            variant_name = (
                variant.get("variant_name")
                or variant.get("original_name")
                or variant["normalized_name"]
            )

            # usage_count: use confidence_score × 100 as a proxy when absent
            # so that update_canonical_variant picks the highest-confidence expansion
            if "usage_count" in variant:
                usage_count = variant["usage_count"]
            elif "confidence_score" in variant:
                usage_count = max(1, int(round(variant["confidence_score"] * 100)))
            else:
                usage_count = 1

            source = variant.get("source") or default_source

            self.store_variant(
                acronym=variant["acronym"],
                entity_type=variant["entity_type"],
                variant_name=variant_name,
                normalized_name=variant["normalized_name"],
                usage_count=usage_count,
                source=source,
            )

            # Restore explicit is_ambiguous flag from source data if present
            if variant.get("is_ambiguous"):
                self.mark_acronym_as_ambiguous(
                    variant["acronym"], variant["entity_type"]
                )

            seen_keys.add((variant["acronym"], variant["entity_type"]))
            count += 1

        if skipped_null:
            detail_logger.info(
                f"Skipped {skipped_null} entries with null normalized_name"
            )

        # Post-import pass: update canonical and detect ambiguity for every
        # affected (acronym, entity_type) pair in one sweep instead of per entry.
        self._post_import_update(seen_keys)

        return count

    def _post_import_update(self, keys: set[tuple[str, str]]) -> None:
        """Update canonical flags and detect ambiguity for a set of acronyms.

        Called once after a batch import instead of per-entry, which avoids
        O(n) redundant SQL round-trips for acronyms with many variants
        (e.g. NeurIPS with 376 entries).

        An acronym is marked ambiguous when it has two or more distinct
        normalized_names whose word-level Jaccard similarity is below 0.3 —
        meaning they genuinely describe different venues, not just surface
        variants of the same name.
        """
        for acronym, entity_type in keys:
            self.update_canonical_variant(acronym, entity_type)
            self._detect_and_mark_ambiguous(acronym, entity_type)

    def _detect_and_mark_ambiguous(self, acronym: str, entity_type: str) -> None:
        """Mark acronym as ambiguous if its variants describe genuinely different venues."""
        with self.get_connection_with_row_factory() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT normalized_name, usage_count
                FROM venue_acronym_variants
                WHERE acronym = ? COLLATE NOCASE AND entity_type = ?
                ORDER BY usage_count DESC
                """,
                (acronym.strip(), entity_type),
            )
            rows = cursor.fetchall()

        if len(rows) < 2:
            return

        # Only consider names with meaningful usage (top-half by count)
        counts = [r["usage_count"] for r in rows]
        threshold = max(1, max(counts) // 4)
        candidates = [
            r["normalized_name"] for r in rows if r["usage_count"] >= threshold
        ]

        if len(candidates) < 2:
            return

        # Jaccard similarity on word sets
        def jaccard(a: str, b: str) -> float:
            sa, sb = set(a.lower().split()), set(b.lower().split())
            if not sa or not sb:
                return 0.0
            return len(sa & sb) / len(sa | sb)

        top = candidates[0]
        for other in candidates[1:]:
            if jaccard(top, other) < 0.3:
                self.mark_acronym_as_ambiguous(acronym, entity_type)
                return

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
