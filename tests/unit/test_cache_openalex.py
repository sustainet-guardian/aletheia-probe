# SPDX-License-Identifier: MIT
"""Tests for the OpenAlex cache module."""

import sqlite3
import tempfile
from collections.abc import Generator
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from aletheia_probe.cache import OpenAlexCache
from aletheia_probe.cache.schema import init_database


@pytest.fixture
def temp_cache() -> Generator[OpenAlexCache, None, None]:
    """Create a temporary cache for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        cache_path = Path(f.name)

    # Initialize database schema
    init_database(cache_path)

    cache = OpenAlexCache(cache_path)
    yield cache

    # Cleanup
    cache_path.unlink(missing_ok=True)


@pytest.fixture
def sample_openalex_data() -> dict:
    """Sample OpenAlex data for testing."""
    return {
        "openalex_id": "S137773608",
        "openalex_url": "https://openalex.org/S137773608",
        "display_name": "Nature",
        "source_type": "journal",
        "issn_l": "0028-0836",
        "issns": ["0028-0836", "1476-4687"],
        "total_publications": 446231,
        "recent_publications": 15234,
        "recent_publications_by_year": {2023: 5234, 2022: 5000, 2021: 5000},
        "publisher": "Nature Publishing Group",
        "first_publication_year": 1869,
        "last_publication_year": 2023,
        "cited_by_count": 89234567,
        "is_in_doaj": False,
        "fetched_at": datetime.now().isoformat(),
    }


class TestOpenAlexCache:
    """Test cases for OpenAlexCache."""

    def test_set_and_get_by_issn(self, temp_cache, sample_openalex_data):
        """Test storing and retrieving OpenAlex data by ISSN."""
        temp_cache.set_openalex_data(
            issn="0028-0836",
            journal_name=None,
            openalex_data=sample_openalex_data,
            ttl_hours=720,
        )

        result = temp_cache.get_openalex_data(issn="0028-0836")
        assert result is not None
        assert result["openalex_id"] == "S137773608"
        assert result["display_name"] == "Nature"
        assert result["total_publications"] == 446231

    def test_set_and_get_by_journal_name(self, temp_cache, sample_openalex_data):
        """Test storing and retrieving OpenAlex data by journal name."""
        temp_cache.set_openalex_data(
            issn=None,
            journal_name="nature",
            openalex_data=sample_openalex_data,
            ttl_hours=720,
        )

        result = temp_cache.get_openalex_data(journal_name="nature")
        assert result is not None
        assert result["openalex_id"] == "S137773608"
        assert result["display_name"] == "Nature"

    def test_set_and_get_by_both(self, temp_cache, sample_openalex_data):
        """Test storing and retrieving OpenAlex data with both ISSN and journal name."""
        temp_cache.set_openalex_data(
            issn="0028-0836",
            journal_name="nature",
            openalex_data=sample_openalex_data,
            ttl_hours=720,
        )

        # Should be retrievable by either
        result_by_issn = temp_cache.get_openalex_data(issn="0028-0836")
        result_by_name = temp_cache.get_openalex_data(journal_name="nature")

        assert result_by_issn is not None
        assert result_by_name is not None
        assert result_by_issn["openalex_id"] == result_by_name["openalex_id"]

    def test_get_nonexistent(self, temp_cache):
        """Test that non-existent entry returns None."""
        result = temp_cache.get_openalex_data(issn="9999-9999")
        assert result is None

    def test_set_without_issn_or_name_raises_error(
        self, temp_cache, sample_openalex_data
    ):
        """Test that setting without ISSN or journal name raises ValueError."""
        with pytest.raises(
            ValueError, match="Either issn or journal_name must be provided"
        ):
            temp_cache.set_openalex_data(
                issn=None,
                journal_name=None,
                openalex_data=sample_openalex_data,
            )

    def test_get_without_issn_or_name_raises_error(self, temp_cache):
        """Test that getting without ISSN or journal name raises ValueError."""
        with pytest.raises(
            ValueError, match="Either issn or journal_name must be provided"
        ):
            temp_cache.get_openalex_data(issn=None, journal_name=None)

    def test_set_negative_ttl_raises_error(self, temp_cache, sample_openalex_data):
        """Test that negative TTL raises ValueError."""
        with pytest.raises(ValueError, match="TTL must be positive"):
            temp_cache.set_openalex_data(
                issn="0028-0836",
                journal_name=None,
                openalex_data=sample_openalex_data,
                ttl_hours=-1,
            )

    def test_set_zero_ttl_raises_error(self, temp_cache, sample_openalex_data):
        """Test that zero TTL raises ValueError."""
        with pytest.raises(ValueError, match="TTL must be positive"):
            temp_cache.set_openalex_data(
                issn="0028-0836",
                journal_name=None,
                openalex_data=sample_openalex_data,
                ttl_hours=0,
            )

    def test_set_excessive_ttl_raises_error(self, temp_cache, sample_openalex_data):
        """Test that TTL exceeding max allowed raises ValueError."""
        with pytest.raises(ValueError, match="TTL exceeds maximum allowed"):
            temp_cache.set_openalex_data(
                issn="0028-0836",
                journal_name=None,
                openalex_data=sample_openalex_data,
                ttl_hours=8761,
            )

    def test_cleanup_expired_entries(self, temp_cache, sample_openalex_data):
        """Test cleanup of expired cache entries."""
        # Add a valid entry
        temp_cache.set_openalex_data(
            issn="0028-0836",
            journal_name="nature",
            openalex_data=sample_openalex_data,
            ttl_hours=720,
        )

        # Manually insert an expired entry
        expired_time = datetime.now() - timedelta(hours=1)
        with sqlite3.connect(temp_cache.db_path) as conn:
            conn.execute(
                """
                INSERT INTO openalex_cache (
                    issn, normalized_journal_name, openalex_id, display_name,
                    total_publications, expires_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("9999-9999", "expired_journal", "S999", "Expired", 100, expired_time),
            )
            conn.commit()

        # Verify both entries exist before cleanup
        with sqlite3.connect(temp_cache.db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM openalex_cache")
            assert cursor.fetchone()[0] == 2

        # Cleanup
        expired_count = temp_cache.cleanup_expired_entries()
        assert expired_count == 1

        # Verify valid entry still exists
        result = temp_cache.get_openalex_data(issn="0028-0836")
        assert result is not None

        # Verify expired entry is gone
        result = temp_cache.get_openalex_data(issn="9999-9999")
        assert result is None

    def test_get_ignores_expired_entries(self, temp_cache):
        """Test that get_openalex_data automatically ignores expired entries."""
        # Manually insert an expired entry
        expired_time = datetime.now() - timedelta(hours=1)
        with sqlite3.connect(temp_cache.db_path) as conn:
            conn.execute(
                """
                INSERT INTO openalex_cache (
                    issn, normalized_journal_name, openalex_id, display_name,
                    total_publications, expires_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("9999-9999", "expired_journal", "S999", "Expired", 100, expired_time),
            )
            conn.commit()

        # get_openalex_data should return None for expired entry
        result = temp_cache.get_openalex_data(issn="9999-9999")
        assert result is None

    def test_update_existing_entry(self, temp_cache, sample_openalex_data):
        """Test that setting an existing entry updates it."""
        # Set initial data
        temp_cache.set_openalex_data(
            issn="0028-0836",
            journal_name="nature",
            openalex_data=sample_openalex_data,
            ttl_hours=720,
        )

        # Update with modified data
        updated_data = sample_openalex_data.copy()
        updated_data["total_publications"] = 500000
        temp_cache.set_openalex_data(
            issn="0028-0836",
            journal_name="nature",
            openalex_data=updated_data,
            ttl_hours=720,
        )

        # Verify update
        result = temp_cache.get_openalex_data(issn="0028-0836")
        assert result["total_publications"] == 500000

        # Verify only one entry exists
        with sqlite3.connect(temp_cache.db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM openalex_cache")
            assert cursor.fetchone()[0] == 1

    def test_data_structure_preservation(self, temp_cache, sample_openalex_data):
        """Test that complex data structures are preserved."""
        temp_cache.set_openalex_data(
            issn="0028-0836",
            journal_name="nature",
            openalex_data=sample_openalex_data,
            ttl_hours=720,
        )

        result = temp_cache.get_openalex_data(issn="0028-0836")

        # Check that lists and dicts are preserved
        assert isinstance(result["issns"], list)
        assert result["issns"] == ["0028-0836", "1476-4687"]
        assert isinstance(result["recent_publications_by_year"], dict)
        assert result["recent_publications_by_year"][2023] == 5234

    def test_missing_optional_fields(self, temp_cache):
        """Test handling of missing optional fields."""
        minimal_data = {
            "openalex_id": "S123",
            "display_name": "Test Journal",
            "total_publications": 100,
            "recent_publications": 10,
            "fetched_at": datetime.now().isoformat(),
        }

        temp_cache.set_openalex_data(
            issn="1234-5678",
            journal_name=None,
            openalex_data=minimal_data,
            ttl_hours=720,
        )

        result = temp_cache.get_openalex_data(issn="1234-5678")
        assert result is not None
        assert result["openalex_id"] == "S123"
        assert result["publisher"] is None
        assert result["issns"] == []
        assert result["recent_publications_by_year"] == {}
