# SPDX-License-Identifier: MIT
"""Pytest configuration and shared fixtures."""

import sqlite3
import tempfile
from pathlib import Path

import pytest

import aletheia_probe.backends  # Import backends to register them
from aletheia_probe.data_models import JournalEntryData
from aletheia_probe.enums import NameType
from aletheia_probe.models import BackendResult, BackendStatus, QueryInput


@pytest.fixture(scope="function", autouse=True)
def isolated_test_cache(tmp_path):
    """
    Automatically provide an isolated test database path for every test.

    This fixture:
    1. Creates a temporary database file path for each test
    2. Initializes the database schema
    3. Returns the path for cache classes to use

    This prevents tests from accessing the production cache.db file.
    """
    # Local import to avoid circular dependency
    from aletheia_probe.cache.schema import init_database

    # Create a temporary database file
    cache_path = tmp_path / "test_cache.db"

    # Initialize the database schema
    init_database(cache_path)

    # Yield the path for tests to use
    yield cache_path

    # The tmp_path fixture automatically cleans up the temp directory


@pytest.fixture
def sample_query_input():
    """Sample QueryInput for testing."""
    return QueryInput(
        raw_input="Journal of Advanced Computer Science",
        normalized_name="Journal of Advanced Computer Science",
        identifiers={"issn": "1234-5678"},
        aliases=["Advanced Computer Science"],
    )


@pytest.fixture
def sample_backend_result():
    """Sample BackendResult for testing."""
    return BackendResult(
        backend_name="test_backend",
        status=BackendStatus.FOUND,
        confidence=0.9,
        assessment="legitimate",
        data={"test": "data"},
        sources=["test_source"],
        response_time=0.1,
    )


@pytest.fixture
def temp_config_dir(tmp_path):
    """Create temporary config directory for testing."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    return config_dir


def add_test_journal_entry(db_path: Path, entry: JournalEntryData) -> int:
    """Add journal entry to test database using direct SQL inserts.

    This is a test helper function that replaces the removed JournalCache.add_journal_entry.
    It directly inserts journal data into the database for test setup purposes.

    Args:
        db_path: Path to the test database
        entry: JournalEntryData object containing journal information

    Returns:
        Journal ID

    Raises:
        TypeError: If entry is not a JournalEntryData instance
        ValueError: If source is not registered or if database operation fails
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

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()

        # Get source ID
        cursor.execute(
            "SELECT id FROM data_sources WHERE name = ?", (entry.source_name,)
        )
        source_row = cursor.fetchone()
        if not source_row:
            raise ValueError(
                f"Source '{entry.source_name}' not registered. Register it first."
            )
        source_id = int(source_row[0])

        # Upsert journal
        cursor.execute(
            "SELECT id FROM journals WHERE normalized_name = ?",
            (entry.normalized_name,),
        )
        journal_row = cursor.fetchone()

        if journal_row:
            journal_id = int(journal_row[0])
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
                (
                    entry.journal_name,
                    entry.issn,
                    entry.eissn,
                    entry.publisher,
                    journal_id,
                ),
            )
        else:
            cursor.execute(
                """
                INSERT INTO journals (normalized_name, display_name, issn, eissn, publisher)
                VALUES (?, ?, ?, ?, ?)
            """,
                (
                    entry.normalized_name,
                    entry.journal_name,
                    entry.issn,
                    entry.eissn,
                    entry.publisher,
                ),
            )
            lastrow_id = cursor.lastrowid
            if lastrow_id is None:
                raise ValueError("Failed to insert journal record")
            journal_id = int(lastrow_id)

        # Add journal names
        names_to_add = [entry.journal_name]
        if entry.aliases:
            names_to_add.extend(entry.aliases)

        for name in names_to_add:
            if name and name.strip():
                name_type = (
                    NameType.CANONICAL.value
                    if name == entry.journal_name
                    else NameType.ALIAS.value
                )
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO journal_names
                    (journal_id, name, name_type, source_name)
                    VALUES (?, ?, ?, ?)
                """,
                    (journal_id, name.strip(), name_type, entry.source_name),
                )

        # Add journal URLs
        if entry.urls:
            for url in entry.urls:
                if url and url.strip():
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO journal_urls
                        (journal_id, url, last_seen_at)
                        VALUES (?, ?, CURRENT_TIMESTAMP)
                    """,
                        (journal_id, url.strip()),
                    )

        # Add source assessment
        cursor.execute(
            """
            INSERT OR REPLACE INTO source_assessments
            (journal_id, source_id, assessment, confidence, last_confirmed_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
            (journal_id, source_id, assessment, entry.confidence),
        )

        return journal_id
