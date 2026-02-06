# SPDX-License-Identifier: MIT
"""Export acronym database to JSON format for dataset publication.

This module provides functionality to export the collected acronym database
as a structured JSON file suitable for public dataset publication.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .cache import AcronymCache
from .logging_config import get_detail_logger, get_status_logger


detail_logger = get_detail_logger()
status_logger = get_status_logger()


@dataclass
class ExportOptions:
    """Configuration options for acronym export."""

    output_path: Path
    min_usage_count: int = 1
    entity_type_filter: str | None = None


@dataclass
class AcronymExportRecord:
    """A single acronym record for export."""

    acronym: str
    entity_type: str
    variant_name: str
    normalized_name: str
    usage_count: int
    is_ambiguous: bool

    def to_variant_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON export (variant fields only)."""
        return {
            "variant_name": self.variant_name,
            "normalized_name": self.normalized_name,
            "count": self.usage_count,
        }


@dataclass
class ExportStatistics:
    """Computed statistics for the exported dataset."""

    total_records: int = 0
    unique_acronyms: int = 0
    by_entity_type: dict[str, int] = field(default_factory=dict)
    ambiguous_count: int = 0
    ambiguity_rate: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON export."""
        return {
            "total_records": self.total_records,
            "unique_acronyms": self.unique_acronyms,
            "by_entity_type": self.by_entity_type,
            "ambiguous_count": self.ambiguous_count,
            "ambiguity_rate": round(self.ambiguity_rate, 4),
        }


class AcronymExporter:
    """Exports acronym database to JSON format for dataset publication."""

    def __init__(self, acronym_cache: AcronymCache | None = None) -> None:
        """Initialize the exporter.

        Args:
            acronym_cache: Optional AcronymCache instance. If not provided,
                          a new instance will be created.
        """
        self.acronym_cache = acronym_cache or AcronymCache()

    def fetch_all_variants(
        self,
        min_usage_count: int = 1,
        entity_type: str | None = None,
    ) -> list[AcronymExportRecord]:
        """Fetch all variants from the cache as export records.

        Args:
            min_usage_count: Minimum usage count to include
            entity_type: Optional filter by entity type

        Returns:
            List of AcronymExportRecord objects
        """
        detail_logger.debug(
            f"Fetching variants (min_usage={min_usage_count}, entity_type={entity_type})"
        )

        raw_variants = self.acronym_cache.get_all_variants_for_export(
            min_usage_count=min_usage_count,
            entity_type=entity_type,
        )

        records = [
            AcronymExportRecord(
                acronym=v["acronym"],
                entity_type=v["entity_type"],
                variant_name=v["variant_name"],
                normalized_name=v["normalized_name"],
                usage_count=v["usage_count"],
                is_ambiguous=v["is_ambiguous"],
            )
            for v in raw_variants
        ]

        detail_logger.debug(f"Fetched {len(records)} variant records")
        return records

    def compute_statistics(
        self, records: list[AcronymExportRecord]
    ) -> ExportStatistics:
        """Compute statistics from export records.

        Args:
            records: List of acronym export records

        Returns:
            ExportStatistics with computed metrics
        """
        if not records:
            return ExportStatistics()

        # Count unique acronyms
        unique_acronyms: set[str] = set()
        by_entity_type: dict[str, int] = {}
        ambiguous_acronyms: set[str] = set()

        for record in records:
            unique_acronyms.add(record.acronym)

            # Count by entity type
            if record.entity_type not in by_entity_type:
                by_entity_type[record.entity_type] = 0
            by_entity_type[record.entity_type] += 1

            # Track ambiguous acronyms
            if record.is_ambiguous:
                ambiguous_acronyms.add(record.acronym)

        unique_count = len(unique_acronyms)
        ambiguous_count = len(ambiguous_acronyms)
        ambiguity_rate = ambiguous_count / unique_count if unique_count > 0 else 0.0

        return ExportStatistics(
            total_records=len(records),
            unique_acronyms=unique_count,
            by_entity_type=by_entity_type,
            ambiguous_count=ambiguous_count,
            ambiguity_rate=ambiguity_rate,
        )

    def _build_hierarchical_acronyms(
        self, records: list[AcronymExportRecord]
    ) -> dict[str, dict[str, dict[str, Any]]]:
        """Build hierarchical acronym structure grouped by acronym and entity_type.

        Args:
            records: List of acronym export records

        Returns:
            Nested dict: acronym -> entity_type -> {is_ambiguous, variants}
        """
        acronyms: dict[str, dict[str, dict[str, Any]]] = {}

        for record in records:
            if record.acronym not in acronyms:
                acronyms[record.acronym] = {}

            if record.entity_type not in acronyms[record.acronym]:
                acronyms[record.acronym][record.entity_type] = {
                    "is_ambiguous": record.is_ambiguous,
                    "variants": [],
                }

            acronyms[record.acronym][record.entity_type]["variants"].append(
                record.to_variant_dict()
            )
            # Update is_ambiguous if any variant is ambiguous
            if record.is_ambiguous:
                acronyms[record.acronym][record.entity_type]["is_ambiguous"] = True

        return acronyms

    def export_to_json(self, options: ExportOptions) -> dict[str, Any]:
        """Export acronyms to JSON file with metadata and statistics.

        Args:
            options: Export configuration options

        Returns:
            Dictionary containing the exported data structure
        """
        status_logger.info(f"Exporting acronyms to {options.output_path}")

        # Fetch records
        records = self.fetch_all_variants(
            min_usage_count=options.min_usage_count,
            entity_type=options.entity_type_filter,
        )

        # Compute statistics
        statistics = self.compute_statistics(records)

        # Build hierarchical acronym structure
        acronyms_hierarchical = self._build_hierarchical_acronyms(records)

        # Build export structure
        export_data: dict[str, Any] = {
            "metadata": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "generator": "aletheia-probe",
                "version": __version__,
                "parameters": {
                    "min_usage_count": options.min_usage_count,
                    "entity_type_filter": options.entity_type_filter,
                },
                "license": "CC-BY-4.0",
            },
            "statistics": statistics.to_dict(),
            "acronyms": acronyms_hierarchical,
        }

        # Write to file
        options.output_path.parent.mkdir(parents=True, exist_ok=True)
        with options.output_path.open("w", encoding="utf-8") as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)

        status_logger.info(f"Exported {len(records)} acronym records")
        status_logger.info(f"Unique acronyms: {statistics.unique_acronyms}")
        status_logger.info(f"Ambiguous acronyms: {statistics.ambiguous_count}")

        return export_data
