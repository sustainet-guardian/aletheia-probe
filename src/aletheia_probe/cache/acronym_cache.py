# SPDX-License-Identifier: MIT
"""Venue acronym cache — consumer of pre-compiled venue-acronyms-2025 data.

Three normalized tables back this module:

* ``venue_acronyms``         — one row per (acronym, entity_type) pair.
* ``venue_acronym_variants`` — one row per observed name form (FK → venue_acronyms).
* ``venue_acronym_issns``    — one row per known ISSN (FK → venue_acronyms).

Canonical names and variant lists are produced upstream by the LLM consensus
pipeline; this module only stores and retrieves them.
"""

import re
from pathlib import Path
from typing import Any

from ..logging_config import get_detail_logger, get_status_logger
from ..normalizer import are_conference_names_equivalent, input_normalizer
from .base import CacheBase


detail_logger = get_detail_logger()
status_logger = get_status_logger()


class AcronymCache(CacheBase):
    """Read/write access to the venue_acronyms cluster of tables."""

    # ------------------------------------------------------------------ lookup

    def get_full_name_for_acronym(
        self,
        acronym: str,
        entity_type: str,
        min_confidence: float = 0.0,
    ) -> str | None:
        """Return the canonical name for an acronym, or None if not found.

        Args:
            acronym: The acronym to look up (e.g., 'ICML', 'JMLR')
            entity_type: VenueType value (e.g., 'journal', 'conference')

        Returns:
            Canonical normalized name, or None if not found.
        """
        detail_logger.debug(f"Looking up acronym '{acronym}' ({entity_type})")
        with self.get_connection_with_row_factory() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT canonical FROM venue_acronyms "
                "WHERE acronym = ? COLLATE NOCASE AND entity_type = ? "
                "AND confidence_score >= ?",
                (acronym.strip(), entity_type, min_confidence),
            )
            row = cursor.fetchone()
            if row:
                detail_logger.debug(
                    f"Found canonical for '{acronym}' -> '{row['canonical']}'"
                )
                return str(row["canonical"])
            detail_logger.debug(f"No entry found for '{acronym}' ({entity_type})")
            return None

    def get_variant_match(
        self,
        variant: str,
        entity_type: str,
        min_confidence: float = 0.0,
    ) -> dict[str, str | float] | None:
        """Return canonical+acronym match data for a variant lookup.

        Args:
            variant: An abbreviated or alternative venue name.
            entity_type: VenueType value (e.g., 'journal', 'conference').

        Returns:
            Dict with keys ``canonical`` and ``acronym``, or None if no match.
        """
        detail_logger.debug(f"Looking up variant '{variant}' ({entity_type})")
        with self.get_connection_with_row_factory() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT va.canonical, va.acronym, va.confidence_score
                FROM venue_acronyms va
                JOIN venue_acronym_variants vav ON va.id = vav.venue_acronym_id
                WHERE vav.variant = ? COLLATE NOCASE
                  AND va.entity_type = ?
                  AND va.confidence_score >= ?
                LIMIT 1
                """,
                (variant.strip(), entity_type, min_confidence),
            )
            row = cursor.fetchone()
            if row:
                canonical = str(row["canonical"])
                acronym = str(row["acronym"])
                detail_logger.debug(
                    f"Found canonical for variant '{variant}' "
                    f"(acronym: '{acronym}') -> '{canonical}'"
                )
                return {
                    "canonical": canonical,
                    "acronym": acronym,
                    "confidence_score": float(row["confidence_score"]),
                }
            detail_logger.debug(
                f"No variant match found for '{variant}' ({entity_type})"
            )
            return None

    def get_canonical_for_variant(
        self,
        variant: str,
        entity_type: str,
        min_confidence: float = 0.0,
    ) -> str | None:
        """Return the canonical name for a venue variant (abbreviated) form.

        Looks up the variant in the ``venue_acronym_variants`` table and returns
        the canonical name of the parent acronym entry.  Enables lookup of
        abbreviated forms such as "ieee trans. pattern anal. mach. intell.".

        Args:
            variant: An abbreviated or alternative venue name to look up
            entity_type: VenueType value (e.g., 'journal', 'conference')

        Returns:
            Canonical name string, or None if no matching variant found.
        """
        match = self.get_variant_match(
            variant, entity_type, min_confidence=min_confidence
        )
        if match:
            return str(match["canonical"])
        return None

    def get_variants(self, acronym: str, entity_type: str) -> list[str]:
        """Return all known name variants for an acronym.

        Args:
            acronym: The acronym to look up
            entity_type: VenueType value

        Returns:
            List of variant strings in insertion order, empty list if not found.
        """
        with self.get_connection_with_row_factory() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT vav.variant
                FROM venue_acronym_variants vav
                JOIN venue_acronyms va ON va.id = vav.venue_acronym_id
                WHERE va.acronym = ? COLLATE NOCASE AND va.entity_type = ?
                ORDER BY vav.id
                """,
                (acronym.strip(), entity_type),
            )
            return [str(row["variant"]) for row in cursor.fetchall()]

    def get_issn_match(
        self,
        issn: str,
        min_confidence: float = 0.0,
    ) -> dict[str, str | float] | None:
        """Return canonical+acronym match data for an ISSN lookup.

        Args:
            issn: ISSN string (e.g. '1550-4859').

        Returns:
            Dict with keys ``canonical`` and ``acronym``, or None if no match.
        """
        detail_logger.debug(f"Looking up ISSN '{issn}'")
        with self.get_connection_with_row_factory() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT va.canonical, va.acronym, va.confidence_score
                FROM venue_acronyms va
                JOIN venue_acronym_issns vai ON va.id = vai.venue_acronym_id
                WHERE vai.issn = ?
                  AND va.confidence_score >= ?
                LIMIT 1
                """,
                (issn.strip(), min_confidence),
            )
            row = cursor.fetchone()
            if row:
                canonical = str(row["canonical"])
                acronym = str(row["acronym"])
                detail_logger.debug(
                    f"Found canonical for ISSN '{issn}' "
                    f"(acronym: '{acronym}') -> '{canonical}'"
                )
                return {
                    "canonical": canonical,
                    "acronym": acronym,
                    "confidence_score": float(row["confidence_score"]),
                }
            detail_logger.debug(f"No entry found for ISSN '{issn}'")
            return None

    def get_canonical_for_issn(
        self,
        issn: str,
        min_confidence: float = 0.0,
    ) -> str | None:
        """Return the canonical name for a venue identified by ISSN.

        Searches the ``venue_acronym_issns`` table.  No entity_type filter is
        applied because ISSNs are globally unique across venue types.

        Args:
            issn: ISSN string (e.g. '1550-4859')

        Returns:
            Canonical name string, or None if not found.
        """
        match = self.get_issn_match(issn, min_confidence=min_confidence)
        if match:
            return str(match["canonical"])
        return None

    def get_issns(
        self,
        acronym: str,
        entity_type: str,
        min_confidence: float = 0.0,
    ) -> list[str]:
        """Return all known ISSNs for an acronym.

        Args:
            acronym: The acronym to look up
            entity_type: VenueType value

        Returns:
            List of ISSN strings, empty list if not found.
        """
        with self.get_connection_with_row_factory() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT vai.issn
                FROM venue_acronym_issns vai
                JOIN venue_acronyms va ON va.id = vai.venue_acronym_id
                WHERE va.acronym = ? COLLATE NOCASE
                  AND va.entity_type = ?
                  AND va.confidence_score >= ?
                ORDER BY vai.id
                """,
                (acronym.strip(), entity_type, min_confidence),
            )
            return [str(row["issn"]) for row in cursor.fetchall()]

    # ------------------------------------------------------------------ import

    def import_acronyms(
        self,
        entries: list[dict[str, Any]],
        source_file: str | None = None,
    ) -> int:
        """Bulk-import acronym entries from venue-acronyms-2025 pipeline output.

        Each entry must have at minimum: acronym, entity_type, canonical.
        Optional: confidence_score, issn (list of strings), variants (list of strings).

        Existing rows for the same (acronym, entity_type) are replaced: the parent
        row is upserted and the child variants/ISSNs are fully replaced.

        Args:
            entries: List of acronym dicts from the pipeline JSON.
            source_file: Filename of the source JSON (for provenance).

        Returns:
            Number of parent rows inserted or replaced.
        """
        if not entries:
            return 0

        count = 0
        skipped = 0

        with self.get_connection_with_row_factory() as conn:
            cursor = conn.cursor()
            for entry in entries:
                acronym = entry.get("acronym", "").strip()
                entity_type = entry.get("entity_type", "")
                canonical = entry.get("canonical", "").strip()

                if not acronym or not entity_type or not canonical:
                    detail_logger.warning(f"Skipping incomplete entry: {entry}")
                    skipped += 1
                    continue

                confidence = float(entry.get("confidence_score", 0.0))
                issns: list[str] = list(entry.get("issn") or [])
                variants: list[str] = list(entry.get("variants") or [])

                # Upsert parent row
                cursor.execute(
                    """
                    INSERT INTO venue_acronyms
                        (acronym, entity_type, canonical, confidence_score, source_file)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(acronym, entity_type) DO UPDATE SET
                        canonical        = excluded.canonical,
                        confidence_score = excluded.confidence_score,
                        source_file      = excluded.source_file,
                        imported_at      = CURRENT_TIMESTAMP
                    """,
                    (acronym, entity_type, canonical, confidence, source_file),
                )

                # Resolve the row id (works for both INSERT and UPDATE paths)
                cursor.execute(
                    "SELECT id FROM venue_acronyms "
                    "WHERE acronym = ? AND entity_type = ?",
                    (acronym, entity_type),
                )
                venue_id: int = cursor.fetchone()["id"]

                # Replace variants
                cursor.execute(
                    "DELETE FROM venue_acronym_variants WHERE venue_acronym_id = ?",
                    (venue_id,),
                )
                for v in variants:
                    v = str(v).strip()
                    if v:
                        cursor.execute(
                            "INSERT OR IGNORE INTO venue_acronym_variants "
                            "(venue_acronym_id, variant) VALUES (?, ?)",
                            (venue_id, v),
                        )

                # Replace ISSNs
                cursor.execute(
                    "DELETE FROM venue_acronym_issns WHERE venue_acronym_id = ?",
                    (venue_id,),
                )
                for issn in issns:
                    issn = str(issn).strip()
                    if issn:
                        cursor.execute(
                            "INSERT OR IGNORE INTO venue_acronym_issns "
                            "(venue_acronym_id, issn) VALUES (?, ?)",
                            (venue_id, issn),
                        )

                count += 1

            conn.commit()

        if skipped:
            detail_logger.info(f"Skipped {skipped} incomplete entries during import")
        detail_logger.info(f"Imported {count} acronym entries from '{source_file}'")
        return count

    def import_from_file(self, json_path: Path) -> int:
        """Import acronyms from a venue-acronyms-YYYY-MM.json file.

        Args:
            json_path: Path to the pipeline output JSON file.

        Returns:
            Number of rows inserted or replaced.
        """
        import json

        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        entries = data.get("acronyms", [])
        return self.import_acronyms(entries, source_file=json_path.name)

    # ------------------------------------------------------------------ write (runtime)

    def _normalize_venue_name(self, full_name: str) -> str:
        """Normalize venue name to generic series form (strips years, ordinals).

        Args:
            full_name: The full venue name (may include year/edition)

        Returns:
            Normalized venue name
        """
        series_name = input_normalizer.extract_conference_series(full_name.lower())
        if series_name:
            return re.sub(r"\s+", " ", series_name).strip()
        return re.sub(r"\s+", " ", full_name.lower()).strip()

    def store_acronym_mapping(
        self,
        acronym: str,
        full_name: str,
        entity_type: str,
        source: str = "unknown",
    ) -> None:
        """Store a single acronym→canonical mapping discovered at runtime.

        Normalizes the name (strips years/ordinals). Warns when a non-equivalent
        conflicting name overwrites an existing entry.  No variants or ISSNs are
        stored — those come from the pre-compiled pipeline import.

        Used by dispatcher and OpenAlex backend when a new mapping is observed
        during assessment.

        Args:
            acronym: The acronym (e.g., 'ICML')
            full_name: The full venue name (used as canonical)
            entity_type: VenueType value
            source: Source of the mapping (for provenance logging)
        """
        acronym = acronym.strip()
        canonical = self._normalize_venue_name(full_name)

        detail_logger.debug(
            f"Storing runtime mapping: '{acronym}' -> '{canonical}' "
            f"(entity_type: {entity_type}, source: {source})"
        )

        with self.get_connection_with_row_factory() as conn:
            cursor = conn.cursor()

            # Check for conflicting existing entry
            cursor.execute(
                "SELECT canonical FROM venue_acronyms "
                "WHERE acronym = ? COLLATE NOCASE AND entity_type = ?",
                (acronym, entity_type),
            )
            existing = cursor.fetchone()
            if existing and existing["canonical"] != canonical:
                if not are_conference_names_equivalent(
                    existing["canonical"], canonical
                ):
                    status_logger.warning(
                        f"Acronym '{acronym}' ({entity_type}) already maps to "
                        f"'{existing['canonical']}', overwriting with '{canonical}'"
                    )

            cursor.execute(
                """
                INSERT INTO venue_acronyms
                    (acronym, entity_type, canonical, confidence_score, source_file)
                VALUES (?, ?, ?, 0.0, ?)
                ON CONFLICT(acronym, entity_type) DO UPDATE SET
                    canonical   = excluded.canonical,
                    source_file = excluded.source_file,
                    imported_at = CURRENT_TIMESTAMP
                """,
                (acronym, entity_type, canonical, source),
            )
            conn.commit()

    # ------------------------------------------------------------------ stats / maintenance

    def get_acronym_stats(self, entity_type: str | None = None) -> dict[str, int]:
        """Return row counts from the acronym table.

        Args:
            entity_type: Optional filter (e.g., 'journal', 'conference').

        Returns:
            Dict with 'total_count'.
        """
        with self.get_connection_with_row_factory() as conn:
            cursor = conn.cursor()
            if entity_type:
                cursor.execute(
                    "SELECT COUNT(*) AS count FROM venue_acronyms WHERE entity_type = ?",
                    (entity_type,),
                )
            else:
                cursor.execute("SELECT COUNT(*) AS count FROM venue_acronyms")
            count = cursor.fetchone()["count"]
            detail_logger.debug(f"Acronym count ({entity_type or 'all'}): {count}")
            return {"total_count": count}

    def get_full_stats(self) -> dict[str, Any]:
        """Return detailed statistics across all three venue acronym tables.

        Returns:
            Dict with keys:
            - ``total_acronyms``: total rows in venue_acronyms
            - ``total_variants``: total rows in venue_acronym_variants
            - ``total_issns``: total rows in venue_acronym_issns
            - ``by_entity_type``: list of dicts with entity_type, acronyms,
              variants, issns counts per type
        """
        with self.get_connection_with_row_factory() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) AS c FROM venue_acronyms")
            total_acronyms: int = cursor.fetchone()["c"]

            cursor.execute("SELECT COUNT(*) AS c FROM venue_acronym_variants")
            total_variants: int = cursor.fetchone()["c"]

            cursor.execute("SELECT COUNT(*) AS c FROM venue_acronym_issns")
            total_issns: int = cursor.fetchone()["c"]

            cursor.execute(
                """
                SELECT
                    va.entity_type,
                    COUNT(DISTINCT va.id)          AS acronyms,
                    COUNT(DISTINCT vav.id)         AS variants,
                    COUNT(DISTINCT vai.id)         AS issns
                FROM venue_acronyms va
                LEFT JOIN venue_acronym_variants vav ON va.id = vav.venue_acronym_id
                LEFT JOIN venue_acronym_issns    vai ON va.id = vai.venue_acronym_id
                GROUP BY va.entity_type
                ORDER BY acronyms DESC
                """
            )
            by_type = [
                {
                    "entity_type": row["entity_type"],
                    "acronyms": row["acronyms"],
                    "variants": row["variants"],
                    "issns": row["issns"],
                }
                for row in cursor.fetchall()
            ]

        return {
            "total_acronyms": total_acronyms,
            "total_variants": total_variants,
            "total_issns": total_issns,
            "by_entity_type": by_type,
        }

    def clear_acronym_database(self, entity_type: str | None = None) -> int:
        """Delete rows from the acronym table (cascades to variants and ISSNs).

        Args:
            entity_type: Optional filter; if None, deletes everything.

        Returns:
            Number of parent rows deleted.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if entity_type:
                cursor.execute(
                    "SELECT COUNT(*) FROM venue_acronyms WHERE entity_type = ?",
                    (entity_type,),
                )
                count = int(cursor.fetchone()[0])
                cursor.execute(
                    "DELETE FROM venue_acronyms WHERE entity_type = ?", (entity_type,)
                )
                detail_logger.debug(
                    f"Deleted {count} rows for entity_type '{entity_type}'"
                )
            else:
                cursor.execute("SELECT COUNT(*) FROM venue_acronyms")
                count = int(cursor.fetchone()[0])
                cursor.execute("DELETE FROM venue_acronyms")
                detail_logger.debug(f"Deleted all {count} rows from venue_acronyms")
            conn.commit()
            return count
