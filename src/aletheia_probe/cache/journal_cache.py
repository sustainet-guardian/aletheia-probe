# SPDX-License-Identifier: MIT
"""Journal data caching for the cache system."""

import sqlite3
from typing import Any

from ..logging_config import get_detail_logger, get_status_logger
from .base import CacheBase


detail_logger = get_detail_logger()
status_logger = get_status_logger()


class JournalCache(CacheBase):
    """Manages journal data caching and queries."""

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

        with self.get_connection_with_row_factory() as conn:
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

        with self.get_connection_with_row_factory() as conn:
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
