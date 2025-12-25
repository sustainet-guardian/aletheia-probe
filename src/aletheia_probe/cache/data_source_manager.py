# SPDX-License-Identifier: MIT
"""Data source management for the cache system."""

import sqlite3
from datetime import datetime
from typing import Any

from ..enums import UpdateStatus
from ..logging_config import get_detail_logger, get_status_logger
from .base import CacheBase


detail_logger = get_detail_logger()
status_logger = get_status_logger()


class DataSourceManager(CacheBase):
    """Manages data sources and their statistics."""

    def register_data_source(
        self,
        name: str,
        display_name: str,
        source_type: str,
        authority_level: int = 5,
        base_url: str | None = None,
        description: str | None = None,
    ) -> int:
        """Register a data source and return its ID.

        Args:
            name: Unique name for the data source
            display_name: Human-readable display name
            source_type: Type of the data source
            authority_level: Authority level (1-10)
            base_url: Base URL of the data source
            description: Description of the data source

        Returns:
            ID of the registered data source
        """
        detail_logger.debug(
            f"Registering data source: {name} (type: {source_type}, authority: {authority_level})"
        )
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO data_sources
                (name, display_name, source_type, authority_level, base_url, description)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    name,
                    display_name,
                    source_type,
                    authority_level,
                    base_url,
                    description,
                ),
            )

            cursor.execute("SELECT id FROM data_sources WHERE name = ?", (name,))
            result = cursor.fetchone()
            if result is None:
                error_msg = f"Could not retrieve ID for data source: {name}"
                detail_logger.error(error_msg)
                raise ValueError(error_msg)
            source_id = int(result[0])
            detail_logger.debug(f"Data source '{name}' registered with ID: {source_id}")
            return source_id

    def get_source_statistics(self) -> dict[str, dict[str, Any]]:
        """Get statistics for all data sources.

        Returns:
            Dictionary mapping source names to their statistics
        """
        detail_logger.debug("Retrieving source statistics from database")
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT ds.name, ds.display_name, sa.assessment, COUNT(*) as count
                FROM data_sources ds
                LEFT JOIN source_assessments sa ON ds.id = sa.source_id
                GROUP BY ds.name, sa.assessment
                ORDER BY ds.name, sa.assessment
            """
            )

            stats = {}
            for source_name, display_name, assessment, count in cursor.fetchall():
                if source_name not in stats:
                    stats[source_name] = {
                        "display_name": display_name,
                        "assessments": {},
                        "total": 0,
                    }

                if assessment:
                    stats[source_name]["assessments"][assessment] = count
                    stats[source_name]["total"] += count

            detail_logger.debug(f"Retrieved statistics for {len(stats)} data sources")
            return stats

    def get_source_stats(self) -> dict[str, dict[str, Any]]:
        """Get statistics for all data sources in structured format.

        Returns:
            Dictionary with source statistics
        """
        # Get the base statistics
        stats = self.get_source_statistics()

        # Convert to structured format
        result = {}
        for source_name, source_stats in stats.items():
            result[source_name] = {
                "total": source_stats.get("total", 0),
                "lists": {
                    assessment: {"count": count}
                    for assessment, count in source_stats.get("assessments", {}).items()
                },
            }

        return result

    def find_conflicts(self) -> list[dict[str, Any]]:
        """Find journals with conflicting assessments from different sources.

        Returns:
            List of journals with conflicting assessments
        """
        detail_logger.debug("Searching for journals with conflicting assessments")
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT j.normalized_name, j.display_name,
                       GROUP_CONCAT(ds.name || ':' || sa.assessment) as conflicting_assessments,
                       COUNT(DISTINCT sa.assessment) as assessment_count
                FROM journals j
                JOIN source_assessments sa ON j.id = sa.journal_id
                JOIN data_sources ds ON sa.source_id = ds.id
                GROUP BY j.id
                HAVING COUNT(DISTINCT sa.assessment) > 1
                ORDER BY j.display_name
            """
            )

            conflicts = [dict(row) for row in cursor.fetchall()]
            detail_logger.debug(
                f"Found {len(conflicts)} journals with conflicting assessments"
            )
            return conflicts

    def log_update(
        self,
        source_name: str,
        update_type: str,
        status: str,
        records_added: int = 0,
        records_updated: int = 0,
        records_removed: int = 0,
        error_message: str | None = None,
    ) -> None:
        """Log a source update operation.

        Args:
            source_name: Name of the data source
            update_type: Type of update operation
            status: Status of the update
            records_added: Number of records added
            records_updated: Number of records updated
            records_removed: Number of records removed
            error_message: Error message if update failed
        """
        detail_logger.debug(
            f"Logging update for source '{source_name}': type={update_type}, status={status}, "
            f"added={records_added}, updated={records_updated}, removed={records_removed}"
        )
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM data_sources WHERE name = ?", (source_name,))
            source_row = cursor.fetchone()

            if source_row:
                cursor.execute(
                    """
                    INSERT INTO source_updates
                    (source_id, update_type, status, records_added, records_updated, records_removed, error_message)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        source_row[0],
                        update_type,
                        status,
                        records_added,
                        records_updated,
                        records_removed,
                        error_message,
                    ),
                )
                detail_logger.debug(
                    f"Update log entry created for source '{source_name}'"
                )
            else:
                detail_logger.warning(
                    f"Cannot log update: data source '{source_name}' not found"
                )

    def get_source_last_updated(self, source_name: str) -> datetime | None:
        """Get the last successful update time for a source.

        Args:
            source_name: Name of the data source

        Returns:
            Datetime of last successful update or None if never updated
        """
        detail_logger.debug(f"Checking last update time for source '{source_name}'")
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT MAX(completed_at) FROM source_updates su
                JOIN data_sources ds ON su.source_id = ds.id
                WHERE ds.name = ? AND su.status = ?
            """,
                (source_name, UpdateStatus.SUCCESS.value),
            )

            row = cursor.fetchone()
            if row and row[0]:
                last_updated = datetime.fromisoformat(row[0])
                detail_logger.debug(
                    f"Source '{source_name}' last updated at: {last_updated}"
                )
                return last_updated
            detail_logger.debug(f"Source '{source_name}' has no successful updates")
            return None

    def has_source_data(self, source_name: str) -> bool:
        """Check if a data source has any journal entries.

        Args:
            source_name: Name of the data source

        Returns:
            True if source has data, False otherwise
        """
        detail_logger.debug(f"Checking if source '{source_name}' has data")
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT COUNT(*) FROM source_assessments sa
                JOIN data_sources ds ON sa.source_id = ds.id
                WHERE ds.name = ?
                """,
                (source_name,),
            )
            count: int = cursor.fetchone()[0]
            detail_logger.debug(f"Source '{source_name}' has {count} records")
            return count > 0

    def remove_source_data(self, source_name: str) -> int:
        """Remove all data for a specific source.

        Args:
            source_name: Name of the data source

        Returns:
            Number of records removed
        """
        detail_logger.debug(f"Removing data for source '{source_name}'")
        with sqlite3.connect(self.db_path) as conn:
            # Get source ID
            cursor = conn.execute(
                "SELECT id FROM data_sources WHERE name = ?", (source_name,)
            )
            source_row = cursor.fetchone()
            if not source_row:
                detail_logger.debug(
                    f"Source '{source_name}' not found, no data to remove"
                )
                return 0

            source_id = source_row[0]

            # Count records to be removed
            cursor = conn.execute(
                "SELECT COUNT(*) FROM source_assessments WHERE source_id = ?",
                (source_id,),
            )
            count: int = cursor.fetchone()[0]
            detail_logger.debug(
                f"Found {count} records to remove for source '{source_name}'"
            )

            # Remove source assessments
            conn.execute(
                "DELETE FROM source_assessments WHERE source_id = ?", (source_id,)
            )
            detail_logger.debug(f"Deleted {count} source assessments")

            # Clean up orphaned journals (journals with no source assessments)
            cursor = conn.execute(
                """
                DELETE FROM journals WHERE id NOT IN (
                    SELECT DISTINCT journal_id FROM source_assessments
                )
                """
            )
            orphaned_journals = cursor.rowcount
            detail_logger.debug(f"Cleaned up {orphaned_journals} orphaned journals")

            conn.commit()
            status_logger.info(f"Removed {count} records from source '{source_name}'")
            return count

    def get_available_sources(self) -> list[str]:
        """Get list of all available data sources.

        Returns:
            List of source names
        """
        detail_logger.debug("Retrieving list of available data sources")
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT DISTINCT name FROM data_sources ORDER BY name"
            )
            sources = [row[0] for row in cursor.fetchall()]
            detail_logger.debug(f"Found {len(sources)} available data sources")
            return sources
