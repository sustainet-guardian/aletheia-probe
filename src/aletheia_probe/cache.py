# SPDX-License-Identifier: MIT
"""Normalized caching system for journal data and assessment results."""

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .data_models import JournalEntryData
from .models import AssessmentResult


class CacheManager:
    """Manages SQLite-based normalized caching for journal data and assessment results."""

    def __init__(self, db_path: Path | None = None):
        if db_path is None:
            # Default to local project directory for paper-specific assessment data
            local_dir = Path.cwd() / ".aletheia-probe"
            local_dir.mkdir(exist_ok=True)
            self.db_path = local_dir / "cache.db"
        else:
            self.db_path = db_path

        # Ensure data directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._init_database()

    def _init_database(self) -> None:
        """Initialize normalized database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(
                """
                -- Core journals table (normalized, one entry per unique journal)
                CREATE TABLE IF NOT EXISTS journals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    normalized_name TEXT UNIQUE NOT NULL,
                    display_name TEXT NOT NULL,
                    issn TEXT,
                    eissn TEXT,
                    publisher TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                -- Journal name variants and aliases
                CREATE TABLE IF NOT EXISTS journal_names (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    journal_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    name_type TEXT DEFAULT 'alias',
                    source_name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (journal_id) REFERENCES journals(id) ON DELETE CASCADE,
                    UNIQUE(journal_id, name)
                );

                -- Journal URLs (one-to-many with journals)
                CREATE TABLE IF NOT EXISTS journal_urls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    journal_id INTEGER NOT NULL,
                    url TEXT NOT NULL,
                    url_type TEXT DEFAULT 'website',
                    is_active BOOLEAN DEFAULT TRUE,
                    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (journal_id) REFERENCES journals(id) ON DELETE CASCADE,
                    UNIQUE(journal_id, url)
                );

                -- Data sources registry
                CREATE TABLE IF NOT EXISTS data_sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    display_name TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    authority_level INTEGER DEFAULT 5,
                    base_url TEXT,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                -- Source assessments (many-to-many: journals <-> sources)
                CREATE TABLE IF NOT EXISTS source_assessments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    journal_id INTEGER NOT NULL,
                    source_id INTEGER NOT NULL,
                    assessment TEXT NOT NULL,
                    confidence REAL DEFAULT 1.0,
                    first_listed_at TIMESTAMP,
                    last_confirmed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'active',
                    FOREIGN KEY (journal_id) REFERENCES journals(id) ON DELETE CASCADE,
                    FOREIGN KEY (source_id) REFERENCES data_sources(id) ON DELETE CASCADE,
                    UNIQUE(journal_id, source_id)
                );

                -- Conference/journal acronym mappings (self-learning cache)
                CREATE TABLE IF NOT EXISTS conference_acronyms (
                    acronym TEXT PRIMARY KEY COLLATE NOCASE,
                    full_name TEXT NOT NULL,
                    source TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_acronyms_full_name ON conference_acronyms(full_name);

                -- Source metadata (replaces JSON metadata)
                CREATE TABLE IF NOT EXISTS source_metadata (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    journal_id INTEGER NOT NULL,
                    source_id INTEGER NOT NULL,
                    metadata_key TEXT NOT NULL,
                    metadata_value TEXT,
                    data_type TEXT DEFAULT 'string',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (journal_id) REFERENCES journals(id) ON DELETE CASCADE,
                    FOREIGN KEY (source_id) REFERENCES data_sources(id) ON DELETE CASCADE,
                    UNIQUE(journal_id, source_id, metadata_key)
                );

                -- Source updates tracking
                CREATE TABLE IF NOT EXISTS source_updates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id INTEGER NOT NULL,
                    update_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    records_added INTEGER DEFAULT 0,
                    records_updated INTEGER DEFAULT 0,
                    records_removed INTEGER DEFAULT 0,
                    error_message TEXT,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (source_id) REFERENCES data_sources(id)
                );

                -- Assessment result cache
                CREATE TABLE IF NOT EXISTS assessment_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query_hash TEXT UNIQUE NOT NULL,
                    query_input TEXT NOT NULL,
                    assessment_result TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL
                );

                -- Article retraction cache (for DOI-level retraction checking)
                CREATE TABLE IF NOT EXISTS article_retractions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    doi TEXT UNIQUE NOT NULL,
                    is_retracted BOOLEAN NOT NULL DEFAULT FALSE,
                    retraction_type TEXT,
                    retraction_date TEXT,
                    retraction_doi TEXT,
                    retraction_reason TEXT,
                    source TEXT NOT NULL,
                    metadata TEXT,
                    checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL
                );

                -- Indexes for performance
                CREATE INDEX IF NOT EXISTS idx_journals_normalized_name ON journals(normalized_name);
                CREATE INDEX IF NOT EXISTS idx_journals_display_name ON journals(display_name);
                CREATE INDEX IF NOT EXISTS idx_journals_normalized_name_lower ON journals(LOWER(normalized_name));
                CREATE INDEX IF NOT EXISTS idx_journals_display_name_lower ON journals(LOWER(display_name));
                CREATE INDEX IF NOT EXISTS idx_journals_issn ON journals(issn);
                CREATE INDEX IF NOT EXISTS idx_journals_eissn ON journals(eissn);
                CREATE INDEX IF NOT EXISTS idx_journal_names_name ON journal_names(name);
                CREATE INDEX IF NOT EXISTS idx_journal_names_journal_id ON journal_names(journal_id);
                CREATE INDEX IF NOT EXISTS idx_journal_urls_journal_id ON journal_urls(journal_id);
                CREATE INDEX IF NOT EXISTS idx_journal_urls_url ON journal_urls(url);
                CREATE INDEX IF NOT EXISTS idx_source_assessments_journal_id ON source_assessments(journal_id);
                CREATE INDEX IF NOT EXISTS idx_source_assessments_source_id ON source_assessments(source_id);
                CREATE INDEX IF NOT EXISTS idx_source_assessments_composite ON source_assessments(source_id, assessment);
                CREATE INDEX IF NOT EXISTS idx_source_metadata_journal_source ON source_metadata(journal_id, source_id);
                CREATE INDEX IF NOT EXISTS idx_assessment_cache_expires ON assessment_cache(expires_at);
                CREATE INDEX IF NOT EXISTS idx_article_retractions_doi ON article_retractions(doi);
                CREATE INDEX IF NOT EXISTS idx_article_retractions_expires ON article_retractions(expires_at);
            """
            )

    def register_data_source(
        self,
        name: str,
        display_name: str,
        source_type: str,
        authority_level: int = 5,
        base_url: str | None = None,
        description: str | None = None,
    ) -> int:
        """Register a data source and return its ID."""
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
                raise ValueError(f"Could not retrieve ID for data source: {name}")
            return int(result[0])

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
        """
        Add or update a journal entry with normalized deduplication.

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
            if not isinstance(entry, JournalEntryData):
                raise TypeError("entry must be a JournalEntryData instance")
            source_name = entry.source_name
            assessment = entry.assessment
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
        """Search for journals with normalized results."""
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

    def get_source_statistics(self) -> dict[str, dict[str, Any]]:
        """Get statistics for all data sources."""
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

            return stats

    def find_conflicts(self) -> list[dict[str, Any]]:
        """Find journals with conflicting assessments from different sources."""
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

            return [dict(row) for row in cursor.fetchall()]

    def cache_assessment_result(
        self,
        query_hash: str,
        query_input: str,
        result: AssessmentResult,
        ttl_hours: int = 24,
    ) -> None:
        """Cache an assessment result with TTL."""
        expires_at = datetime.now() + timedelta(hours=ttl_hours)
        result_json = result.model_dump_json()

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO assessment_cache
                (query_hash, query_input, assessment_result, expires_at)
                VALUES (?, ?, ?, ?)
            """,
                (query_hash, query_input, result_json, expires_at),
            )

    def get_cached_assessment(self, query_hash: str) -> AssessmentResult | None:
        """Get cached assessment result if not expired."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT assessment_result FROM assessment_cache
                WHERE query_hash = ? AND expires_at > ?
            """,
                (query_hash, datetime.now()),
            )

            row = cursor.fetchone()
            if row:
                return AssessmentResult.model_validate_json(row[0])
            return None

    def cleanup_expired_cache(self) -> int:
        """Remove expired assessment cache entries."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM assessment_cache WHERE expires_at <= ?", (datetime.now(),)
            )
            return cursor.rowcount

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
        """Log a source update operation."""
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

    def get_source_last_updated(self, source_name: str) -> datetime | None:
        """Get the last successful update time for a source."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT MAX(completed_at) FROM source_updates su
                JOIN data_sources ds ON su.source_id = ds.id
                WHERE ds.name = ? AND su.status = 'success'
            """,
                (source_name,),
            )

            row = cursor.fetchone()
            if row and row[0]:
                return datetime.fromisoformat(row[0])
            return None

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
        """
        Add a journal entry using list-based nomenclature.

        Maps list-based parameters (list_type) to assessment-based parameters.
        """
        # Register the data source if not exists (use generic "mixed" type to avoid conflicts)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM data_sources WHERE name = ?", (source_name,))
            if cursor.fetchone() is None:
                self.register_data_source(source_name, source_name, "mixed")

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

    def has_source_data(self, source_name: str) -> bool:
        """
        Check if a data source has any journal entries.

        Args:
            source_name: Name of the data source

        Returns:
            True if source has data, False otherwise
        """
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
            return count > 0

    def remove_source_data(self, source_name: str) -> int:
        """
        Remove all data for a specific source.

        Args:
            source_name: Name of the data source

        Returns:
            Number of records removed
        """
        with sqlite3.connect(self.db_path) as conn:
            # Get source ID
            cursor = conn.execute(
                "SELECT id FROM data_sources WHERE name = ?", (source_name,)
            )
            source_row = cursor.fetchone()
            if not source_row:
                return 0

            source_id = source_row[0]

            # Count records to be removed
            cursor = conn.execute(
                "SELECT COUNT(*) FROM source_assessments WHERE source_id = ?",
                (source_id,),
            )
            count: int = cursor.fetchone()[0]

            # Remove source assessments
            conn.execute(
                "DELETE FROM source_assessments WHERE source_id = ?", (source_id,)
            )

            # Clean up orphaned journals (journals with no source assessments)
            conn.execute(
                """
                DELETE FROM journals WHERE id NOT IN (
                    SELECT DISTINCT journal_id FROM source_assessments
                )
                """
            )

            conn.commit()
            return count

    def get_available_sources(self) -> list[str]:
        """
        Get list of all available data sources.

        Returns:
            List of source names
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT DISTINCT name FROM data_sources ORDER BY name"
            )
            return [row[0] for row in cursor.fetchall()]

    def set_cached_value(self, key: str, value: str, ttl_hours: int = 24) -> None:
        """
        Store a key-value pair in cache with TTL.

        Args:
            key: Cache key
            value: Value to cache
            ttl_hours: Time-to-live in hours
        """
        expires_at = datetime.now() + timedelta(hours=ttl_hours)

        with sqlite3.connect(self.db_path) as conn:
            # Create table if it doesn't exist
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS key_value_cache (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL
                )
                """
            )

            conn.execute(
                """
                INSERT OR REPLACE INTO key_value_cache (key, value, expires_at)
                VALUES (?, ?, ?)
                """,
                (key, value, expires_at),
            )
            conn.commit()

    def get_cached_value(self, key: str) -> str | None:
        """
        Get a cached value by key.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found or expired
        """
        with sqlite3.connect(self.db_path) as conn:
            # Ensure table exists
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS key_value_cache (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL
                )
                """
            )

            cursor = conn.execute(
                """
                SELECT value FROM key_value_cache
                WHERE key = ? AND expires_at > CURRENT_TIMESTAMP
                """,
                (key,),
            )
            row = cursor.fetchone()
            return row[0] if row else None

    def get_source_stats(self) -> dict[str, dict[str, Any]]:
        """
        Get statistics for all data sources.

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

    def get_article_retraction(self, doi: str) -> dict[str, Any] | None:
        """
        Get cached retraction information for a DOI.

        Args:
            doi: The DOI to check (will be normalized)

        Returns:
            Dictionary with retraction info if found and not expired, None otherwise
        """
        normalized_doi = doi.lower().strip()

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT doi, is_retracted, retraction_type, retraction_date,
                       retraction_doi, retraction_reason, source, metadata,
                       checked_at, expires_at
                FROM article_retractions
                WHERE doi = ? AND expires_at > CURRENT_TIMESTAMP
                """,
                (normalized_doi,),
            )

            row = cursor.fetchone()
            if row:
                result = dict(row)
                # Parse JSON metadata if present
                if result.get("metadata"):
                    try:
                        result["metadata"] = json.loads(result["metadata"])
                    except json.JSONDecodeError:
                        pass
                return result
            return None

    def cache_article_retraction(
        self,
        doi: str,
        is_retracted: bool,
        source: str,
        retraction_type: str | None = None,
        retraction_date: str | None = None,
        retraction_doi: str | None = None,
        retraction_reason: str | None = None,
        metadata: dict[str, Any] | None = None,
        ttl_hours: int = 24 * 30,  # 30 days default
    ) -> None:
        """
        Cache retraction information for a DOI.

        Args:
            doi: The DOI to cache
            is_retracted: Whether the article is retracted
            source: Source of the retraction information (e.g., 'crossref', 'retraction_watch')
            retraction_type: Type of retraction (e.g., 'retraction', 'correction', 'expression_of_concern')
            retraction_date: Date of retraction
            retraction_doi: DOI of the retraction notice
            retraction_reason: Reason for retraction
            metadata: Additional metadata as JSON
            ttl_hours: Cache TTL in hours
        """
        normalized_doi = doi.lower().strip()
        expires_at = datetime.now() + timedelta(hours=ttl_hours)

        metadata_json = json.dumps(metadata) if metadata else None

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO article_retractions
                (doi, is_retracted, retraction_type, retraction_date, retraction_doi,
                 retraction_reason, source, metadata, checked_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
                """,
                (
                    normalized_doi,
                    is_retracted,
                    retraction_type,
                    retraction_date,
                    retraction_doi,
                    retraction_reason,
                    source,
                    metadata_json,
                    expires_at.isoformat(),
                ),
            )
            conn.commit()

    def cleanup_expired_article_retractions(self) -> int:
        """
        Remove expired article retraction cache entries.

        Returns:
            Number of entries removed
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                DELETE FROM article_retractions
                WHERE expires_at <= CURRENT_TIMESTAMP
                """
            )
            conn.commit()
            return cursor.rowcount

    # Acronym management methods

    def get_full_name_for_acronym(self, acronym: str) -> str | None:
        """
        Look up the full name for a conference/journal acronym.

        Args:
            acronym: The acronym to look up (e.g., 'ICML', 'CVPR')

        Returns:
            Full name if found in cache, None otherwise
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT full_name FROM conference_acronyms
                WHERE acronym = ? COLLATE NOCASE
                """,
                (acronym.strip(),),
            )

            row = cursor.fetchone()
            if row:
                # Update last_used_at timestamp
                cursor.execute(
                    """
                    UPDATE conference_acronyms
                    SET last_used_at = CURRENT_TIMESTAMP
                    WHERE acronym = ? COLLATE NOCASE
                    """,
                    (acronym.strip(),),
                )
                conn.commit()
                return str(row["full_name"])
            return None

    def store_acronym_mapping(
        self, acronym: str, full_name: str, source: str = "unknown"
    ) -> None:
        """
        Store an acronym to full name mapping in the cache.

        If the acronym already exists with a different full_name, logs a warning
        and overwrites with the new mapping.

        Args:
            acronym: The acronym (e.g., 'ICML')
            full_name: The full conference/journal name
            source: Source of the mapping ('bibtex_extraction', 'openalex_response', 'manual')
        """
        from .logging_config import get_status_logger

        status_logger = get_status_logger()

        acronym = acronym.strip()
        full_name = full_name.strip()

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Check for existing mapping
            cursor.execute(
                """
                SELECT full_name FROM conference_acronyms
                WHERE acronym = ? COLLATE NOCASE
                """,
                (acronym,),
            )

            existing = cursor.fetchone()
            if existing and existing["full_name"] != full_name:
                status_logger.warning(
                    f"Acronym '{acronym}' already maps to '{existing['full_name']}', "
                    f"overwriting with '{full_name}'"
                )

            # Insert or replace the mapping
            cursor.execute(
                """
                INSERT OR REPLACE INTO conference_acronyms
                (acronym, full_name, source, created_at, last_used_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (acronym, full_name, source),
            )
            conn.commit()

    def get_acronym_stats(self) -> dict[str, int | str]:
        """
        Get statistics about the acronym database.

        Returns:
            Dictionary containing count, most_recent, and oldest entry info
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Get total count
            cursor.execute("SELECT COUNT(*) as count FROM conference_acronyms")
            count = cursor.fetchone()["count"]

            # Get most recently used
            cursor.execute(
                """
                SELECT acronym, full_name, last_used_at
                FROM conference_acronyms
                ORDER BY last_used_at DESC
                LIMIT 1
                """
            )
            most_recent = cursor.fetchone()

            # Get oldest entry
            cursor.execute(
                """
                SELECT acronym, full_name, created_at
                FROM conference_acronyms
                ORDER BY created_at ASC
                LIMIT 1
                """
            )
            oldest = cursor.fetchone()

            stats = {"total_count": count}

            if most_recent:
                stats["most_recent_acronym"] = most_recent["acronym"]
                stats["most_recent_full_name"] = most_recent["full_name"]
                stats["most_recent_used"] = most_recent["last_used_at"]

            if oldest:
                stats["oldest_acronym"] = oldest["acronym"]
                stats["oldest_full_name"] = oldest["full_name"]
                stats["oldest_created"] = oldest["created_at"]

            return stats

    def list_all_acronyms(
        self, limit: int | None = None, offset: int = 0
    ) -> list[dict[str, str]]:
        """
        List all acronym mappings in the database.

        Args:
            limit: Maximum number of entries to return (None for all)
            offset: Number of entries to skip

        Returns:
            List of dictionaries containing acronym details
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            query = """
                SELECT acronym, full_name, source, created_at, last_used_at
                FROM conference_acronyms
                ORDER BY acronym ASC
            """

            if limit is not None:
                query += f" LIMIT {limit} OFFSET {offset}"

            cursor.execute(query)
            rows = cursor.fetchall()

            return [
                {
                    "acronym": row["acronym"],
                    "full_name": row["full_name"],
                    "source": row["source"],
                    "created_at": row["created_at"],
                    "last_used_at": row["last_used_at"],
                }
                for row in rows
            ]

    def clear_acronym_database(self) -> int:
        """
        Clear all entries from the acronym database.

        Returns:
            Number of entries deleted
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Get count before deletion
            cursor.execute("SELECT COUNT(*) FROM conference_acronyms")
            result = cursor.fetchone()
            count: int = result[0] if result else 0

            # Delete all entries
            cursor.execute("DELETE FROM conference_acronyms")
            conn.commit()

            return count


# Global cache manager instance with factory pattern
_cache_manager_instance: CacheManager | None = None


def get_cache_manager() -> CacheManager:
    """Get or create the global cache manager instance.

    Returns:
        The global CacheManager instance
    """
    global _cache_manager_instance
    if _cache_manager_instance is None:
        _cache_manager_instance = CacheManager()
    return _cache_manager_instance


def set_cache_manager(manager: CacheManager) -> None:
    """Set the cache manager instance (primarily for testing).

    Args:
        manager: CacheManager instance to use globally
    """
    global _cache_manager_instance
    _cache_manager_instance = manager


def reset_cache_manager() -> None:
    """Reset the cache manager instance (primarily for testing)."""
    global _cache_manager_instance
    _cache_manager_instance = None
