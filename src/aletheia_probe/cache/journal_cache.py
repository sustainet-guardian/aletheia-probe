# SPDX-License-Identifier: MIT
"""Journal data caching for the cache system."""

import json
import sqlite3
from typing import TYPE_CHECKING, Any

from .base import CacheBase


if TYPE_CHECKING:
    from ..data_models import JournalEntryData


class JournalCache(CacheBase):
    """Manages journal data caching and queries."""

    def add_journal_entry(
        self,
        source_name: str | None = None,
        assessment: str | None = None,
        journal_name: str | None = None,
        normalized_name: str | None = None,
        confidence: float = 1.0,
        issn: str | None = None,
        eissn: str | None = None,
        publisher: str | None = None,
        urls: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        aliases: list[str] | None = None,
        entry: "JournalEntryData | None" = None,
    ) -> int:
        """Add or update a journal entry with normalized deduplication.

        Can be called either with individual parameters or with a JournalEntryData object.

        Args:
            source_name: Data source name
            assessment: Assessment type
            journal_name: Display journal name
            normalized_name: Normalized journal name for deduplication
            confidence: Confidence score (0.0 to 1.0)
            issn: Print ISSN
            eissn: Electronic ISSN
            publisher: Publisher name
            urls: List of URLs
            metadata: Additional metadata
            aliases: List of journal name aliases
            entry: JournalEntryData object (alternative to individual params)

        Returns:
            Journal ID

        Raises:
            ValueError: If required fields are missing or invalid

        Examples:
            >>> # Using individual parameters
            >>> cache.add_journal_entry(
            ...     source_name="doaj",
            ...     assessment="legitimate",
            ...     journal_name="Nature",
            ...     normalized_name="nature"
            ... )

            >>> # Using dataclass
            >>> from aletheia_probe.data_models import JournalEntryData
            >>> entry = JournalEntryData(
            ...     source_name="doaj",
            ...     assessment="legitimate",
            ...     journal_name="Nature",
            ...     normalized_name="nature"
            ... )
            >>> cache.add_journal_entry(entry=entry)
        """
        # Support dataclass entry
        if entry is not None:
            from ..data_models import JournalEntryData

            if not isinstance(entry, JournalEntryData):
                raise TypeError("entry must be a JournalEntryData instance")
            source_name = entry.source_name
            # Convert AssessmentType enum to string
            assessment = (
                entry.assessment.value
                if hasattr(entry.assessment, "value")
                else entry.assessment
            )
            journal_name = entry.journal_name
            normalized_name = entry.normalized_name
            confidence = entry.confidence
            issn = entry.issn
            eissn = entry.eissn
            publisher = entry.publisher
            urls = entry.urls
            metadata = entry.metadata
            aliases = entry.aliases

        # Validate required fields
        if not source_name:
            raise ValueError("source_name is required")
        if not assessment:
            raise ValueError("assessment is required")
        if not journal_name:
            raise ValueError("journal_name is required")
        if not normalized_name:
            raise ValueError("normalized_name is required")
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Get or create source ID
            cursor.execute("SELECT id FROM data_sources WHERE name = ?", (source_name,))
            source_row = cursor.fetchone()
            if not source_row:
                raise ValueError(
                    f"Source '{source_name}' not registered. Register it first."
                )
            source_id = int(source_row[0])

            # Find or create journal by normalized name
            cursor.execute(
                "SELECT id FROM journals WHERE normalized_name = ?", (normalized_name,)
            )
            journal_row = cursor.fetchone()

            if journal_row:
                journal_id = int(journal_row[0])
                # Update existing journal
                cursor.execute(
                    """
                    UPDATE journals
                    SET display_name = COALESCE(?, display_name),
                        issn = COALESCE(?, issn),
                        eissn = COALESCE(?, eissn),
                        publisher = COALESCE(?, publisher),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """,
                    (journal_name, issn, eissn, publisher, journal_id),
                )
            else:
                # Create new journal
                cursor.execute(
                    """
                    INSERT INTO journals (normalized_name, display_name, issn, eissn, publisher)
                    VALUES (?, ?, ?, ?, ?)
                """,
                    (normalized_name, journal_name, issn, eissn, publisher),
                )
                lastrow_id = cursor.lastrowid
                if lastrow_id is None:
                    raise ValueError("Failed to insert journal record")
                journal_id = int(lastrow_id)

            # Add journal name variants
            names_to_add = [journal_name]
            if aliases:
                names_to_add.extend(aliases)

            for name in names_to_add:
                if name and name.strip():
                    name_type = "canonical" if name == journal_name else "alias"
                    cursor.execute(
                        """
                        INSERT OR IGNORE INTO journal_names
                        (journal_id, name, name_type, source_name)
                        VALUES (?, ?, ?, ?)
                    """,
                        (journal_id, name.strip(), name_type, source_name),
                    )

            # Add or update URLs
            if urls:
                for url in urls:
                    if url and url.strip():
                        cursor.execute(
                            """
                            INSERT OR REPLACE INTO journal_urls
                            (journal_id, url, last_seen_at)
                            VALUES (?, ?, CURRENT_TIMESTAMP)
                        """,
                            (journal_id, url.strip()),
                        )

            # Add or update source assessment
            cursor.execute(
                """
                INSERT OR REPLACE INTO source_assessments
                (journal_id, source_id, assessment, confidence, last_confirmed_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
                (journal_id, source_id, assessment, confidence),
            )

            # Add metadata
            if metadata:
                for key, value in metadata.items():
                    if value is not None:
                        # Determine data type
                        data_type = "string"
                        if isinstance(value, bool):
                            data_type = "boolean"
                            value = str(value).lower()
                        elif isinstance(value, int):
                            data_type = "integer"
                            value = str(value)
                        elif isinstance(value, (dict, list)):
                            data_type = "json"
                            value = json.dumps(value)
                        else:
                            value = str(value)

                        cursor.execute(
                            """
                            INSERT OR REPLACE INTO source_metadata
                            (journal_id, source_id, metadata_key, metadata_value, data_type)
                            VALUES (?, ?, ?, ?, ?)
                        """,
                            (journal_id, source_id, key, value, data_type),
                        )

            return journal_id

    def search_journals_by_name(
        self,
        name: str,
        source_name: str,
        assessment: str,
    ) -> list[dict[str, Any]]:
        """Search for journals by exact normalized name match.

        Uses SQL WHERE clause for efficient lookup with indexed columns.

        Args:
            name: Journal name to search (will be normalized to lowercase)
            source_name: Data source name to filter by
            assessment: Assessment type to filter by

        Returns:
            List of matching journal records
        """
        name_lower = name.lower().strip()

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            # Optimized query using WHERE clause instead of loading all records
            query = """
                SELECT DISTINCT j.*,
                       sa.assessment as list_type,
                       GROUP_CONCAT(DISTINCT jn.name) as all_names
                FROM journals j
                JOIN source_assessments sa ON j.id = sa.journal_id
                JOIN data_sources ds ON sa.source_id = ds.id
                LEFT JOIN journal_names jn ON j.id = jn.journal_id
                WHERE ds.name = ?
                  AND sa.assessment = ?
                  AND (LOWER(j.normalized_name) = ? OR LOWER(j.display_name) = ?)
                GROUP BY j.id
            """

            cursor = conn.execute(
                query, (source_name, assessment, name_lower, name_lower)
            )
            rows = cursor.fetchall()

            results = []

            # Batch fetch all URLs to avoid N+1 query pattern
            urls_by_journal: dict[int, list[str]] = {}
            if rows:
                journal_ids = [dict(row)["id"] for row in rows]
                placeholders = ",".join("?" * len(journal_ids))
                url_cursor = conn.execute(
                    f"""
                    SELECT journal_id, url FROM journal_urls
                    WHERE journal_id IN ({placeholders}) AND is_active = TRUE
                    ORDER BY journal_id, first_seen_at
                """,  # nosec B608
                    journal_ids,
                )
                # Group URLs by journal_id
                for journal_id, url in url_cursor.fetchall():
                    urls_by_journal.setdefault(journal_id, []).append(url)

            for row in rows:
                journal_dict = dict(row)
                journal_id = journal_dict["id"]

                # Get URLs from pre-fetched data
                journal_dict["urls"] = urls_by_journal.get(journal_id, [])

                # Add convenience aliases for common fields
                journal_dict["journal_name"] = journal_dict["display_name"]

                # Get source-specific metadata
                metadata_cursor = conn.execute(
                    """
                    SELECT sm.metadata_key, sm.metadata_value, sm.data_type
                    FROM source_metadata sm
                    JOIN data_sources ds ON sm.source_id = ds.id
                    WHERE sm.journal_id = ? AND ds.name = ?
                """,
                    (journal_id, source_name),
                )

                metadata = {}
                for key, value, data_type in metadata_cursor.fetchall():
                    if key and value:
                        if data_type == "json":
                            metadata[key] = json.loads(value)
                        elif data_type == "boolean":
                            metadata[key] = value.lower() == "true"
                        elif data_type == "integer":
                            metadata[key] = int(value)
                        else:
                            metadata[key] = value

                if metadata:
                    journal_dict["metadata"] = json.dumps(metadata)

                results.append(journal_dict)

            return results

    def search_journals(
        self,
        normalized_name: str | None = None,
        journal_name: str | None = None,
        issn: str | None = None,
        source_name: str | None = None,
        assessment: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search for journals with normalized results.

        Args:
            normalized_name: Normalized journal name to search
            journal_name: Display journal name to search
            issn: ISSN to search
            source_name: Data source name to filter by
            assessment: Assessment type to filter by

        Returns:
            List of matching journal records
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            # Build base query
            query_parts = [
                """
                SELECT DISTINCT j.*,
                       GROUP_CONCAT(sa.assessment || ':' || ds.name) as source_assessments,
                       GROUP_CONCAT(DISTINCT jn.name) as all_names
                FROM journals j
                LEFT JOIN source_assessments sa ON j.id = sa.journal_id
                LEFT JOIN data_sources ds ON sa.source_id = ds.id
                LEFT JOIN journal_names jn ON j.id = jn.journal_id
                WHERE 1=1
            """
            ]
            params = []

            # Add filters
            if normalized_name:
                query_parts.append("AND j.normalized_name LIKE ?")
                params.append(f"%{normalized_name}%")

            if journal_name:
                query_parts.append(
                    "AND j.id IN (SELECT journal_id FROM journal_names WHERE name LIKE ?)"
                )
                params.append(f"%{journal_name}%")

            if issn:
                query_parts.append("AND (j.issn = ? OR j.eissn = ?)")
                params.extend([issn, issn])

            if source_name:
                query_parts.append(
                    "AND sa.source_id = (SELECT id FROM data_sources WHERE name = ?)"
                )
                params.append(source_name)

            if assessment:
                query_parts.append("AND sa.assessment = ?")
                params.append(assessment)

            query_parts.append("GROUP BY j.id")

            cursor = conn.execute(" ".join(query_parts), params)
            results = []
            rows = cursor.fetchall()

            # Batch fetch all URLs to avoid N+1 query pattern
            urls_by_journal: dict[int, list[str]] = {}
            if rows:
                journal_ids = [dict(row)["id"] for row in rows]
                placeholders = ",".join("?" * len(journal_ids))
                url_cursor = conn.execute(
                    f"""
                    SELECT journal_id, url FROM journal_urls
                    WHERE journal_id IN ({placeholders}) AND is_active = TRUE
                    ORDER BY journal_id, first_seen_at
                """,  # nosec B608
                    journal_ids,
                )
                # Group URLs by journal_id
                for journal_id, url in url_cursor.fetchall():
                    urls_by_journal.setdefault(journal_id, []).append(url)

            for row in rows:
                journal_dict = dict(row)
                journal_id = journal_dict["id"]

                # Get URLs from pre-fetched data
                journal_dict["urls"] = urls_by_journal.get(journal_id, [])

                # Get source-specific data when filtering by source
                if source_name:
                    source_cursor = conn.execute(
                        """
                        SELECT sa.assessment, sa.confidence, sm.metadata_key, sm.metadata_value, sm.data_type
                        FROM source_assessments sa
                        LEFT JOIN source_metadata sm ON sa.journal_id = sm.journal_id AND sa.source_id = sm.source_id
                        JOIN data_sources ds ON sa.source_id = ds.id
                        WHERE sa.journal_id = ? AND ds.name = ?
                    """,
                        (journal_id, source_name),
                    )

                    source_data = source_cursor.fetchall()
                    if source_data:
                        # Add convenience aliases for common fields
                        journal_dict["journal_name"] = journal_dict["display_name"]
                        journal_dict["list_type"] = source_data[0][0]  # assessment

                        # Reconstruct metadata
                        metadata = {}
                        for _, _, key, value, data_type in source_data:
                            if key and value:
                                if data_type == "json":
                                    metadata[key] = json.loads(value)
                                elif data_type == "boolean":
                                    metadata[key] = value.lower() == "true"
                                elif data_type == "integer":
                                    metadata[key] = int(value)
                                else:
                                    metadata[key] = value

                        if metadata:
                            journal_dict["metadata"] = json.dumps(metadata)

                results.append(journal_dict)

            return results

    def add_journal_list_entry(
        self,
        source_name: str,
        list_type: str,
        journal_name: str,
        normalized_name: str | None = None,
        issn: str | None = None,
        eissn: str | None = None,
        publisher: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Add a journal entry using list-based nomenclature.

        Maps list-based parameters (list_type) to assessment-based parameters.

        Args:
            source_name: Data source name
            list_type: Type of list (maps to assessment)
            journal_name: Display journal name
            normalized_name: Normalized journal name
            issn: Print ISSN
            eissn: Electronic ISSN
            publisher: Publisher name
            metadata: Additional metadata
        """
        # Register the data source if not exists (use generic "mixed" type to avoid conflicts)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM data_sources WHERE name = ?", (source_name,))
            if cursor.fetchone() is None:
                # Import here to avoid circular dependency
                from .data_source_manager import DataSourceManager

                dsm = DataSourceManager(self.db_path)
                dsm.register_data_source(source_name, source_name, "mixed")

        # Add the journal entry using the new normalized method
        self.add_journal_entry(
            source_name=source_name,
            assessment=list_type,
            journal_name=journal_name,
            normalized_name=normalized_name,
            issn=issn,
            eissn=eissn,
            publisher=publisher,
            metadata=metadata,
        )
