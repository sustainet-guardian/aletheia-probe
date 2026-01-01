# SPDX-License-Identifier: MIT
"""Tests for the cache retraction module."""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from aletheia_probe.cache import RetractionCache
from aletheia_probe.cache.connection_utils import get_configured_connection
from aletheia_probe.cache.schema import init_database


@pytest.fixture
def temp_cache():
    """Create a temporary cache for testing with all cache components."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        cache_path = Path(f.name)

    # Initialize database schema
    init_database(cache_path)

    cache = RetractionCache(cache_path)
    yield cache

    # Cleanup
    cache_path.unlink(missing_ok=True)


class TestCacheRetraction:
    """Test cases for Cache Retraction."""

    def test_get_article_retraction(self, temp_cache):
        """Test getting cached article retraction."""
        # Cache a retraction
        temp_cache.cache_article_retraction(
            doi="10.1234/test",
            is_retracted=True,
            source="test_source",
            retraction_type="full",
            retraction_date="2023-01-01",
            retraction_doi="10.1234/retraction",
            retraction_reason="Fraud",
        )

        # Retrieve it
        result = temp_cache.get_article_retraction(doi="10.1234/test")

        assert result is not None
        assert result["is_retracted"] is True
        assert result["retraction_type"] == "full"

    def test_get_article_retraction_nonexistent(self, temp_cache):
        """Test that non-existent DOI returns None."""
        result = temp_cache.get_article_retraction(doi="10.1234/nonexistent")
        assert result is None

    def test_get_article_retraction_boolean_types(self, temp_cache):
        """Test that boolean fields are returned as strict Python bool types."""
        # Test with is_retracted=True
        temp_cache.cache_article_retraction(
            doi="10.1234/retracted",
            is_retracted=True,
            source="test_source",
        )

        # Test with is_retracted=False
        temp_cache.cache_article_retraction(
            doi="10.1234/not-retracted",
            is_retracted=False,
            source="test_source",
        )

        # Verify True case
        result_true = temp_cache.get_article_retraction(doi="10.1234/retracted")
        assert result_true is not None
        assert result_true["is_retracted"] is True
        assert isinstance(result_true["is_retracted"], bool)

        # Verify False case
        result_false = temp_cache.get_article_retraction(doi="10.1234/not-retracted")
        assert result_false is not None
        assert result_false["is_retracted"] is False
        assert isinstance(result_false["is_retracted"], bool)

    def test_cleanup_expired_article_retractions(self, temp_cache):
        """Test cleanup of expired article retraction entries."""
        # Insert expired entries using the public API with negative TTL
        temp_cache.cache_article_retraction(
            doi="10.1234/expired1",
            is_retracted=True,
            source="test_source",
            ttl_hours=-24,  # Expired 1 day ago
        )
        temp_cache.cache_article_retraction(
            doi="10.1234/expired2",
            is_retracted=False,
            source="test_source",
            ttl_hours=-48,  # Expired 2 days ago
        )

        # Add a non-expired entry using the regular method
        temp_cache.cache_article_retraction(
            doi="10.1234/valid",
            is_retracted=True,
            source="test_source",
            ttl_hours=24,
        )

        # Cleanup expired entries
        removed_count = temp_cache.cleanup_expired_article_retractions()

        # Verify count of removed entries
        assert removed_count == 2

        # Verify expired entries are gone
        assert temp_cache.get_article_retraction(doi="10.1234/expired1") is None
        assert temp_cache.get_article_retraction(doi="10.1234/expired2") is None

        # Verify non-expired entry still exists
        result = temp_cache.get_article_retraction(doi="10.1234/valid")
        assert result is not None
        assert result["is_retracted"] is True

    def test_datetime_format_consistency(self, temp_cache):
        """Test that expires_at format is consistent with SQLite CURRENT_TIMESTAMP."""
        # Cache an entry
        temp_cache.cache_article_retraction(
            doi="10.1234/format-test",
            is_retracted=False,
            source="test_source",
            ttl_hours=1,
        )

        # Query the database directly to check the stored format
        with get_configured_connection(temp_cache.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT expires_at
                FROM article_retractions
                WHERE doi = ?
                """,
                ("10.1234/format-test",),
            )
            row = cursor.fetchone()
            assert row is not None
            expires_at_str = row[0]

            # Verify format matches SQLite timestamp (YYYY-MM-DD HH:MM:SS)
            # Should not contain 'T' separator or microseconds
            assert "T" not in expires_at_str
            assert len(expires_at_str) == 19  # 'YYYY-MM-DD HH:MM:SS'

            # Verify string comparison with CURRENT_TIMESTAMP works correctly
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM article_retractions
                WHERE doi = ? AND expires_at > CURRENT_TIMESTAMP
                """,
                ("10.1234/format-test",),
            )
            count = cursor.fetchone()[0]
            # Should find the entry since it expires in 1 hour (future)
            assert count == 1

    def test_upsert_retraction_statistics_preserves_created_at(self, temp_cache):
        """Test that upsert preserves original created_at timestamp on updates."""
        # First, we need a journal_id to work with
        # Insert a basic journal record directly since RetractionCache doesn't manage journals
        with temp_cache.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO journals (normalized_name, display_name) VALUES (?, ?)""",
                ("test-journal", "Test Journal"),
            )
            journal_id = cursor.lastrowid
            conn.commit()

        # Initial insert
        temp_cache.upsert_retraction_statistics(
            journal_id=journal_id,
            total_retractions=5,
            recent_retractions=2,
            very_recent_retractions=1,
            retraction_types={"retraction": 3, "correction": 2},
            top_reasons=[("error", 3), ("fraud", 2)],
            publishers=["TestPub"],
            first_retraction_date="2020-01-01",
            last_retraction_date="2023-12-01",
        )

        # Get the initial created_at timestamp
        with temp_cache.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT created_at, updated_at
                FROM retraction_statistics
                WHERE journal_id = ?
                """,
                (journal_id,),
            )
            row = cursor.fetchone()
            assert row is not None
            initial_created_at = row[0]
            initial_updated_at = row[1]

        # Wait at least 1 second to ensure timestamp difference (SQLite CURRENT_TIMESTAMP has second precision)
        import time

        time.sleep(1.1)

        # Update the same record
        temp_cache.upsert_retraction_statistics(
            journal_id=journal_id,
            total_retractions=6,  # Changed
            recent_retractions=3,  # Changed
            very_recent_retractions=1,
            retraction_types={"retraction": 4, "correction": 2},  # Changed
            top_reasons=[("error", 3), ("fraud", 3)],  # Changed
            publishers=["TestPub"],
            first_retraction_date="2020-01-01",
            last_retraction_date="2024-01-01",  # Changed
        )

        # Verify created_at is preserved, updated_at is changed
        with temp_cache.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT created_at, updated_at, total_retractions, recent_retractions
                FROM retraction_statistics
                WHERE journal_id = ?
                """,
                (journal_id,),
            )
            row = cursor.fetchone()
            assert row is not None
            final_created_at, final_updated_at, total_ret, recent_ret = row

            # created_at should be unchanged
            assert final_created_at == initial_created_at

            # updated_at should be different (newer)
            assert final_updated_at != initial_updated_at

            # Data should be updated
            assert total_ret == 6
            assert recent_ret == 3

    def test_upsert_retraction_statistics_new_record(self, temp_cache):
        """Test that upsert creates new record with both timestamps set."""
        # Insert a basic journal record
        with temp_cache.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO journals (normalized_name, display_name) VALUES (?, ?)""",
                ("new-journal", "New Journal"),
            )
            journal_id = cursor.lastrowid
            conn.commit()

        # Insert new record
        temp_cache.upsert_retraction_statistics(
            journal_id=journal_id,
            total_retractions=3,
            recent_retractions=1,
            very_recent_retractions=0,
        )

        # Verify both timestamps are set and equal
        with temp_cache.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT created_at, updated_at, total_retractions
                FROM retraction_statistics
                WHERE journal_id = ?
                """,
                (journal_id,),
            )
            row = cursor.fetchone()
            assert row is not None
            created_at, updated_at, total_ret = row

            # Both timestamps should be set
            assert created_at is not None
            assert updated_at is not None

            # Data should be correct
            assert total_ret == 3

    def test_parse_json_fields_valid_json(self, temp_cache):
        """Test that _parse_json_fields correctly parses valid JSON."""
        result = {
            "retraction_types": '{"retraction": 3, "correction": 2}',
            "top_reasons": '[["error", 3], ["fraud", 2]]',
            "publishers": '["TestPub", "OtherPub"]',
            "other_field": "regular_value",
        }

        parsed_result = temp_cache._parse_json_fields(
            result, ["retraction_types", "top_reasons", "publishers"]
        )

        # JSON fields should be parsed
        assert parsed_result["retraction_types"] == {"retraction": 3, "correction": 2}
        assert parsed_result["top_reasons"] == [["error", 3], ["fraud", 2]]
        assert parsed_result["publishers"] == ["TestPub", "OtherPub"]

        # Non-JSON fields should remain unchanged
        assert parsed_result["other_field"] == "regular_value"

    def test_parse_json_fields_invalid_json(self, temp_cache):
        """Test that _parse_json_fields handles invalid JSON gracefully."""
        result = {
            "retraction_types": "invalid json {",
            "top_reasons": None,
            "publishers": '["valid", "json"]',
            "empty_field": "",
        }

        parsed_result = temp_cache._parse_json_fields(
            result, ["retraction_types", "top_reasons", "publishers", "empty_field"]
        )

        # Invalid JSON should keep original value
        assert parsed_result["retraction_types"] == "invalid json {"

        # None/empty values should remain unchanged
        assert parsed_result["top_reasons"] is None
        assert parsed_result["empty_field"] == ""

        # Valid JSON should be parsed
        assert parsed_result["publishers"] == ["valid", "json"]

    def test_parse_json_fields_nonexistent_fields(self, temp_cache):
        """Test that _parse_json_fields handles nonexistent fields gracefully."""
        result = {"existing_field": "value"}

        parsed_result = temp_cache._parse_json_fields(
            result, ["nonexistent_field", "also_missing"]
        )

        # Should not add new fields or modify existing ones
        assert parsed_result == {"existing_field": "value"}

    def test_get_retraction_statistics_with_json_parsing(self, temp_cache):
        """Test that get_retraction_statistics correctly parses JSON fields."""
        # Insert a basic journal record
        with temp_cache.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO journals (normalized_name, display_name) VALUES (?, ?)""",
                ("test-journal", "Test Journal"),
            )
            journal_id = cursor.lastrowid
            conn.commit()

        # Insert retraction statistics with JSON data
        temp_cache.upsert_retraction_statistics(
            journal_id=journal_id,
            total_retractions=5,
            recent_retractions=2,
            very_recent_retractions=1,
            retraction_types={"retraction": 3, "correction": 2},
            top_reasons=[["error", 3], ["fraud", 2]],
            publishers=["TestPub", "OtherPub"],
            first_retraction_date="2020-01-01",
            last_retraction_date="2023-12-01",
        )

        # Retrieve and verify parsing
        result = temp_cache.get_retraction_statistics(journal_id)

        assert result is not None
        assert result["total_retractions"] == 5

        # Verify JSON fields are properly parsed as Python objects
        assert isinstance(result["retraction_types"], dict)
        assert result["retraction_types"] == {"retraction": 3, "correction": 2}

        assert isinstance(result["top_reasons"], list)
        assert result["top_reasons"] == [["error", 3], ["fraud", 2]]

        assert isinstance(result["publishers"], list)
        assert result["publishers"] == ["TestPub", "OtherPub"]

    def test_get_retraction_statistics_with_corrupted_json(self, temp_cache):
        """Test that get_retraction_statistics handles corrupted JSON gracefully."""
        # Insert a basic journal record
        with temp_cache.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO journals (normalized_name, display_name) VALUES (?, ?)""",
                ("test-journal-corrupt", "Test Journal Corrupt"),
            )
            journal_id = cursor.lastrowid

            # Insert retraction statistics with corrupted JSON directly
            cursor.execute(
                """
                INSERT INTO retraction_statistics
                (journal_id, total_retractions, recent_retractions, very_recent_retractions,
                 retraction_types, top_reasons, publishers, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (
                    journal_id,
                    5,
                    2,
                    1,
                    "invalid json {",  # Corrupted JSON
                    '["valid", "json"]',  # Valid JSON
                    None,  # Null value
                ),
            )
            conn.commit()

        # Should not raise exception and return data with available fields
        result = temp_cache.get_retraction_statistics(journal_id)

        assert result is not None
        assert result["total_retractions"] == 5

        # Corrupted JSON should remain as string
        assert result["retraction_types"] == "invalid json {"

        # Valid JSON should be parsed
        assert result["top_reasons"] == ["valid", "json"]

        # Null values should remain null
        assert result["publishers"] is None
