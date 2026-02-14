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
from aletheia_probe.cache.migrations import migrate_database, reset_database
from aletheia_probe.cache.schema import (
    SCHEMA_VERSION,
    SchemaVersionError,
    check_schema_compatibility,
    get_schema_version,
    init_database,
    set_schema_version,
)


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
            "schema_version",
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
            "venue_acronyms",
            "venue_acronym_variants",
            "venue_acronym_issns",
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
            "venue_acronyms",
            "venue_acronym_variants",
            "venue_acronym_issns",
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
            "venue_acronym_variants": ["venue_acronym_id"],
            "venue_acronym_issns": ["venue_acronym_id"],
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
                "idx_venue_acronyms_acronym",
                "idx_venue_acronym_variants_variant",
                "idx_venue_acronym_issns_issn",
                "idx_custom_lists_list_name",
            }

            assert expected_indexes.issubset(indexes)


class TestSchemaVersioning:
    """Test cases for database schema versioning."""

    def test_schema_version_table_created(self, temp_db):
        """Test that schema_version table is created."""
        with get_configured_connection(temp_db) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
            )
            result = cursor.fetchone()
            assert result is not None, "schema_version table not created"

    def test_initial_version_set(self, temp_db):
        """Test that initial schema version is set correctly."""
        version = get_schema_version(temp_db)
        assert version == SCHEMA_VERSION, (
            f"Expected version {SCHEMA_VERSION}, got {version}"
        )

    def test_get_schema_version_returns_none_for_legacy(self):
        """Test that get_schema_version returns None for legacy databases."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        try:
            # Create a legacy database without schema_version table
            with get_configured_connection(db_path) as conn:
                conn.execute(
                    """
                    CREATE TABLE journals (
                        id INTEGER PRIMARY KEY,
                        name TEXT
                    )
                    """
                )
                conn.commit()

            version = get_schema_version(db_path)
            assert version is None, "Legacy database should return None for version"

        finally:
            db_path.unlink(missing_ok=True)

    def test_set_schema_version(self, temp_db):
        """Test that set_schema_version works correctly."""
        # Set to a different version
        set_schema_version(temp_db, 99, "Test version")

        # Verify it was set
        version = get_schema_version(temp_db)
        assert version == 99

        # Check description was stored
        with get_configured_connection(temp_db) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT description FROM schema_version WHERE version = 99")
            result = cursor.fetchone()
            assert result is not None
            assert result[0] == "Test version"

    def test_check_compatibility_success(self, temp_db):
        """Test that check_schema_compatibility passes for compatible version."""
        # Should not raise an exception
        result = check_schema_compatibility(temp_db)
        assert result is True

    def test_check_compatibility_fails_for_legacy(self):
        """Test that check_schema_compatibility fails for legacy database."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        try:
            # Create a legacy database
            with get_configured_connection(db_path) as conn:
                conn.execute("CREATE TABLE journals (id INTEGER PRIMARY KEY)")
                conn.commit()

            # Should raise SchemaVersionError
            with pytest.raises(SchemaVersionError) as exc_info:
                check_schema_compatibility(db_path)

            assert "unknown" in str(exc_info.value).lower()

        finally:
            db_path.unlink(missing_ok=True)

    def test_check_compatibility_fails_for_old_version(self, temp_db):
        """Test that check_schema_compatibility fails for old version."""
        # Set to an old version
        set_schema_version(temp_db, 1, "Old version")

        # Should raise SchemaVersionError
        with pytest.raises(SchemaVersionError) as exc_info:
            check_schema_compatibility(temp_db)

        assert "too old" in str(exc_info.value).lower()

    def test_check_compatibility_fails_for_future_version(self, temp_db):
        """Test that check_schema_compatibility fails for future version."""
        # Set to a future version
        future_version = SCHEMA_VERSION + 10
        set_schema_version(temp_db, future_version, "Future version")

        # Should raise SchemaVersionError
        with pytest.raises(SchemaVersionError) as exc_info:
            check_schema_compatibility(temp_db)

        assert "newer" in str(exc_info.value).lower()

    def test_init_database_checks_compatibility(self):
        """Test that init_database checks compatibility when check_version=True."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        try:
            # Create initial database
            init_database(db_path)

            # Set to an old version
            set_schema_version(db_path, 1, "Old version")

            # Try to init again with check_version=False (default) - should NOT raise
            init_database(db_path, check_version=False)

            # Try to init again with check_version=True - should raise SchemaVersionError
            with pytest.raises(SchemaVersionError):
                init_database(db_path, check_version=True)

        finally:
            db_path.unlink(missing_ok=True)

    def test_migrate_database_from_legacy(self):
        """Test migrating a legacy database to current version."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        try:
            # Create a legacy database with some tables
            with get_configured_connection(db_path) as conn:
                conn.executescript(
                    """
                    CREATE TABLE journals (
                        id INTEGER PRIMARY KEY,
                        name TEXT
                    );
                    CREATE TABLE venue_acronyms (
                        id INTEGER PRIMARY KEY,
                        acronym TEXT
                    );
                    """
                )
                conn.commit()

            # Migrate to current version
            success = migrate_database(db_path, target_version=SCHEMA_VERSION)
            assert success is True

            # Verify version was updated
            version = get_schema_version(db_path)
            assert version == SCHEMA_VERSION

            # Verify old table was dropped
            with get_configured_connection(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='venue_acronyms'"
                )
                assert cursor.fetchone() is None

            # Verify backup was created
            backup_files = list(db_path.parent.glob(f"{db_path.stem}_backup_*.db"))
            assert len(backup_files) > 0

            # Cleanup backups
            for backup in backup_files:
                backup.unlink(missing_ok=True)

        finally:
            db_path.unlink(missing_ok=True)

    def test_reset_database(self):
        """Test resetting database to current schema."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        try:
            # Create initial database
            init_database(db_path)

            # Add some data
            with get_configured_connection(db_path) as conn:
                conn.execute(
                    "INSERT INTO journals (normalized_name, display_name) VALUES ('test', 'Test Journal')"
                )
                conn.commit()

            # Reset database
            success = reset_database(db_path, confirm=True)
            assert success is True

            # Verify database was reset (data should be gone)
            with get_configured_connection(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM journals")
                count = cursor.fetchone()[0]
                assert count == 0

            # Verify version is current
            version = get_schema_version(db_path)
            assert version == SCHEMA_VERSION

            # Verify backup was created
            backup_files = list(db_path.parent.glob(f"{db_path.stem}_backup_*.db"))
            assert len(backup_files) > 0

            # Cleanup backups
            for backup in backup_files:
                backup.unlink(missing_ok=True)

        finally:
            db_path.unlink(missing_ok=True)

    def test_reset_database_requires_confirmation(self):
        """Test that reset_database requires confirmation."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        try:
            init_database(db_path)

            # Should raise ValueError without confirmation
            with pytest.raises(ValueError) as exc_info:
                reset_database(db_path, confirm=False)

            assert "confirmation" in str(exc_info.value).lower()

        finally:
            db_path.unlink(missing_ok=True)
