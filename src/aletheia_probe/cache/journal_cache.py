# SPDX-License-Identifier: MIT
"""Journal data caching for the cache system."""

import sqlite3
from typing import Any

from ..data_models import JournalEntryData
from ..enums import NameType
from ..logging_config import get_detail_logger, get_status_logger
from .base import CacheBase


detail_logger = get_detail_logger()
status_logger = get_status_logger()


class JournalCache(CacheBase):
    """Manages journal data caching and queries."""

    def _get_source_id(self, cursor: sqlite3.Cursor, source_name: str) -> int:
        """Get source ID from database.

        Args:
            cursor: Database cursor
            source_name: Data source name

        Returns:
            Source ID

        Raises:
            ValueError: If source is not registered
        """
        cursor.execute("SELECT id FROM data_sources WHERE name = ?", (source_name,))
        source_row = cursor.fetchone()
        if not source_row:
            detail_logger.debug(f"Data source '{source_name}' not found in database")
            status_logger.error(
                f"Source '{source_name}' not registered. Register it first."
            )
            raise ValueError(
                f"Source '{source_name}' not registered. Register it first."
            )
        source_id = int(source_row[0])
        detail_logger.debug(f"Found data source '{source_name}' with ID {source_id}")
        return source_id

    def _upsert_journal(
        self,
        cursor: sqlite3.Cursor,
        normalized_name: str,
        journal_name: str,
        issn: str | None,
        eissn: str | None,
        publisher: str | None,
    ) -> int:
        """Find or create journal by normalized name.

        Args:
            cursor: Database cursor
            normalized_name: Normalized journal name
            journal_name: Display journal name
            issn: Print ISSN
            eissn: Electronic ISSN
            publisher: Publisher name

        Returns:
            Journal ID

        Raises:
            ValueError: If journal insert fails
        """
        cursor.execute(
            "SELECT id FROM journals WHERE normalized_name = ?", (normalized_name,)
        )
        journal_row = cursor.fetchone()

        if journal_row:
            journal_id = int(journal_row[0])
            detail_logger.debug(
                f"Updating existing journal '{normalized_name}' (ID: {journal_id})"
            )
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
            detail_logger.debug(f"Creating new journal '{normalized_name}'")
            cursor.execute(
                """
                INSERT INTO journals (normalized_name, display_name, issn, eissn, publisher)
                VALUES (?, ?, ?, ?, ?)
            """,
                (normalized_name, journal_name, issn, eissn, publisher),
            )
            lastrow_id = cursor.lastrowid
            if lastrow_id is None:
                detail_logger.debug("Failed to get lastrowid from journal insert")
                raise ValueError("Failed to insert journal record")
            journal_id = int(lastrow_id)
            detail_logger.debug(f"Created journal with ID {journal_id}")

        return journal_id

    def _add_journal_names(
        self,
        cursor: sqlite3.Cursor,
        journal_id: int,
        journal_name: str,
        source_name: str,
        aliases: list[str] | None,
    ) -> None:
        """Add journal name variants to database.

        Args:
            cursor: Database cursor
            journal_id: Journal ID
            journal_name: Canonical journal name
            source_name: Data source name
            aliases: List of journal name aliases
        """
        names_to_add = [journal_name]
        if aliases:
            names_to_add.extend(aliases)

        for name in names_to_add:
            if name and name.strip():
                name_type = (
                    NameType.CANONICAL.value
                    if name == journal_name
                    else NameType.ALIAS.value
                )
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO journal_names
                    (journal_id, name, name_type, source_name)
                    VALUES (?, ?, ?, ?)
                """,
                    (journal_id, name.strip(), name_type, source_name),
                )

    def _add_journal_urls(
        self, cursor: sqlite3.Cursor, journal_id: int, urls: list[str] | None
    ) -> None:
        """Add or update journal URLs in database.

        Args:
            cursor: Database cursor
            journal_id: Journal ID
            urls: List of URLs
        """
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

    def _add_source_assessment(
        self,
        cursor: sqlite3.Cursor,
        journal_id: int,
        source_id: int,
        assessment: str,
        confidence: float,
    ) -> None:
        """Add or update source assessment in database.

        Args:
            cursor: Database cursor
            journal_id: Journal ID
            source_id: Source ID
            assessment: Assessment type
            confidence: Confidence score
        """
        cursor.execute(
            """
            INSERT OR REPLACE INTO source_assessments
            (journal_id, source_id, assessment, confidence, last_confirmed_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
            (journal_id, source_id, assessment, confidence),
        )

    def add_journal_entry(self, entry: JournalEntryData) -> int:
        """Add or update a journal entry with normalized deduplication.

        Args:
            entry: JournalEntryData object containing journal information

        Returns:
            Journal ID

        Raises:
            TypeError: If entry is not a JournalEntryData instance
            ValueError: If source is not registered or if database operation fails

        Examples:
            >>> from aletheia_probe.data_models import JournalEntryData
            >>> entry = JournalEntryData(
            ...     source_name="doaj",
            ...     assessment="legitimate",
            ...     journal_name="Nature",
            ...     normalized_name="nature"
            ... )
            >>> cache.add_journal_entry(entry)
        """
        if not isinstance(entry, JournalEntryData):
            raise TypeError(
                f"entry must be a JournalEntryData instance, got {type(entry).__name__}"
            )

        assessment = (
            entry.assessment.value
            if hasattr(entry.assessment, "value")
            else entry.assessment
        )

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            source_id = self._get_source_id(cursor, entry.source_name)
            journal_id = self._upsert_journal(
                cursor,
                entry.normalized_name,
                entry.journal_name,
                entry.issn,
                entry.eissn,
                entry.publisher,
            )
            self._add_journal_names(
                cursor,
                journal_id,
                entry.journal_name,
                entry.source_name,
                entry.aliases if entry.aliases else None,
            )
            self._add_journal_urls(
                cursor, journal_id, entry.urls if entry.urls else None
            )
            self._add_source_assessment(
                cursor, journal_id, source_id, assessment, entry.confidence
            )
            return journal_id

    def _batch_fetch_urls(
        self, conn: sqlite3.Connection, journal_ids: list[int]
    ) -> dict[int, list[str]]:
        """Batch fetch URLs for multiple journals.

        Args:
            conn: Database connection
            journal_ids: List of journal IDs

        Returns:
            Dictionary mapping journal_id to list of URLs
        """
        if not journal_ids:
            return {}

        placeholders = ",".join("?" * len(journal_ids))
        url_cursor = conn.execute(
            f"""
            SELECT journal_id, url FROM journal_urls
            WHERE journal_id IN ({placeholders}) AND is_active = TRUE
            ORDER BY journal_id, first_seen_at
        """,  # nosec B608
            journal_ids,
        )

        urls_by_journal: dict[int, list[str]] = {}
        for journal_id, url in url_cursor.fetchall():
            urls_by_journal.setdefault(journal_id, []).append(url)

        return urls_by_journal

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
        detail_logger.debug(
            f"Searching journals by name: '{name}' (normalized: '{name_lower}'), "
            f"source: {source_name}, assessment: {assessment}"
        )

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

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

            journal_ids = [dict(row)["id"] for row in rows] if rows else []
            urls_by_journal = self._batch_fetch_urls(conn, journal_ids)

            results = []
            for row in rows:
                journal_dict = dict(row)
                journal_id = journal_dict["id"]
                journal_dict["urls"] = urls_by_journal.get(journal_id, [])
                journal_dict["journal_name"] = journal_dict["display_name"]
                results.append(journal_dict)

            detail_logger.debug(
                f"Search by name returned {len(results)} result(s) for '{name}'"
            )
            return results

    def _build_search_query(
        self,
        normalized_name: str | None,
        journal_name: str | None,
        issn: str | None,
        source_name: str | None,
        assessment: str | None,
    ) -> tuple[str, list[Any]]:
        """Build dynamic search query with filters.

        Args:
            normalized_name: Normalized journal name to search
            journal_name: Display journal name to search
            issn: ISSN to search
            source_name: Data source name to filter by
            assessment: Assessment type to filter by

        Returns:
            Tuple of (query string, query parameters)
        """
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
        params: list[Any] = []

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
        return " ".join(query_parts), params

    def _enrich_search_result(
        self,
        journal_dict: dict[str, Any],
        urls_by_journal: dict[int, list[str]],
        conn: sqlite3.Connection,
        source_name: str | None,
    ) -> dict[str, Any]:
        """Enrich search result with URLs and source-specific data.

        Args:
            journal_dict: Base journal dictionary
            urls_by_journal: Pre-fetched URLs by journal ID
            conn: Database connection
            source_name: Data source name (optional)

        Returns:
            Enriched journal dictionary
        """
        journal_id = journal_dict["id"]
        journal_dict["urls"] = urls_by_journal.get(journal_id, [])

        if source_name:
            source_cursor = conn.execute(
                """
                SELECT sa.assessment, sa.confidence
                FROM source_assessments sa
                JOIN data_sources ds ON sa.source_id = ds.id
                WHERE sa.journal_id = ? AND ds.name = ?
            """,
                (journal_id, source_name),
            )

            source_data = source_cursor.fetchone()
            if source_data:
                journal_dict["journal_name"] = journal_dict["display_name"]
                journal_dict["list_type"] = source_data[0]

        return journal_dict

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
        detail_logger.debug(
            f"Searching journals with filters: normalized_name={normalized_name}, "
            f"journal_name={journal_name}, issn={issn}, source_name={source_name}, "
            f"assessment={assessment}"
        )

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            query, params = self._build_search_query(
                normalized_name, journal_name, issn, source_name, assessment
            )
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()

            journal_ids = [dict(row)["id"] for row in rows] if rows else []
            urls_by_journal = self._batch_fetch_urls(conn, journal_ids)

            results = [
                self._enrich_search_result(
                    dict(row), urls_by_journal, conn, source_name
                )
                for row in rows
            ]

            detail_logger.debug(f"Search returned {len(results)} result(s)")
            return results
