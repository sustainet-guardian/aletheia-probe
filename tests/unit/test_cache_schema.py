# SPDX-License-Identifier: MIT
"""Tests for cache database schema initialization.

These are high-level tests that verify the schema was created correctly
without duplicating schema definition details. The actual schema definition
in src/aletheia_probe/cache/schema.py remains the single source of truth.

Tests verify:
- All expected tables exist
- Tables have columns (basic structure check)
- Foreign key relationships are created
- Indexes are created

Tests intentionally do NOT duplicate:
- Exact column definitions
- Data types and constraints
- Detailed schema structure
"""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from aletheia_probe.cache.connection_utils import get_configured_connection
from aletheia_probe.cache.schema import init_database


@pytest.fixture
def temp_db():
    """Create a temporary database for testing schema."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    # Initialize database schema
    init_database(db_path)

    yield db_path

    # Cleanup
    db_path.unlink(missing_ok=True)


class TestCacheSchema:
    """Test cases for cache database schema."""

    def test_all_tables_created(self, temp_db):
        """Test that all expected tables are created."""
        expected_tables = {
            "journals",
            "journal_names",
            "journal_urls",
            "data_sources",
            "source_assessments",
            "retraction_statistics",
            "source_updates",
            "assessment_cache",
            "article_retractions",
            "openalex_cache",
            "venue_acronym_variants",
            "learned_abbreviations",
            "custom_lists",
        }

        with get_configured_connection(temp_db) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            # SQLite automatically creates sqlite_sequence for AUTOINCREMENT
            actual_tables = {
                row[0] for row in cursor.fetchall() if row[0] != "sqlite_sequence"
            }

            assert expected_tables == actual_tables

    def test_tables_have_columns(self, temp_db):
        """Test that tables have columns (basic structure check)."""
        tables_to_check = [
            "journals",
            "journal_names",
            "journal_urls",
            "data_sources",
            "source_assessments",
            "retraction_statistics",
            "source_updates",
            "assessment_cache",
            "article_retractions",
            "venue_acronym_variants",
            "learned_abbreviations",
            "custom_lists",
        ]

        with get_configured_connection(temp_db) as conn:
            cursor = conn.cursor()
            for table in tables_to_check:
                cursor.execute(f"PRAGMA table_info({table})")
                columns = cursor.fetchall()
                assert len(columns) > 0, f"Table {table} has no columns"

    def test_foreign_keys_created(self, temp_db):
        """Test that foreign key relationships are created."""
        tables_with_fks = {
            "journal_names": ["journal_id"],
            "journal_urls": ["journal_id"],
            "source_assessments": ["journal_id", "source_id"],
            "retraction_statistics": ["journal_id"],
            "source_updates": ["source_id"],
        }

        with get_configured_connection(temp_db) as conn:
            cursor = conn.cursor()
            for table, expected_fks in tables_with_fks.items():
                cursor.execute(f"PRAGMA foreign_key_list({table})")
                fks = cursor.fetchall()
                fk_columns = [fk[3] for fk in fks]
                for expected_fk in expected_fks:
                    assert expected_fk in fk_columns, (
                        f"Foreign key {expected_fk} missing in {table}"
                    )

    def test_indexes_created(self, temp_db):
        """Test that indexes are created."""
        with get_configured_connection(temp_db) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
            indexes = {row[0] for row in cursor.fetchall()}

            # Check some key indexes exist
            expected_indexes = {
                "idx_journals_issn",
                "idx_journal_names_journal_id",
                "idx_source_assessments_journal_id",
                "idx_assessment_cache_expires",
                "idx_article_retractions_doi",
                "idx_variants_acronym",
                "idx_variants_canonical",
                "idx_variants_normalized",
                "idx_abbrev_lookup",
                "idx_custom_lists_list_name",
            }

            assert expected_indexes.issubset(indexes)
