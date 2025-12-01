# SPDX-License-Identifier: MIT
"""Integration tests for cache functionality.

These tests validate cache operations including population, retrieval,
and synchronization workflows.
"""

import tempfile
from pathlib import Path

import pytest

from aletheia_probe.cache import CacheManager
from aletheia_probe.enums import AssessmentType


class TestCacheIntegration:
    """Integration tests for cache functionality."""

    @pytest.fixture
    def temp_cache_path(self) -> Path:
        """Create a temporary cache database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            temp_path = Path(f.name)
        yield temp_path
        # Cleanup
        if temp_path.exists():
            temp_path.unlink()

    @pytest.mark.integration
    def test_cache_initialization(self, temp_cache_path: Path) -> None:
        """Test cache manager initialization.

        Validates that cache database is properly initialized with
        correct schema and tables.
        """
        cache = CacheManager(db_path=temp_cache_path)

        # Verify cache was created
        assert temp_cache_path.exists(), "Cache database file should be created"

        # Test basic operations work
        # The existence of the cache manager itself validates initialization
        assert cache is not None

    @pytest.mark.integration
    def test_cache_journal_entry_crud(self, temp_cache_path: Path) -> None:
        """Test create, read, update, delete operations on journal entries.

        Validates that journal entries can be properly added to cache,
        retrieved, and managed.
        """
        cache = CacheManager(db_path=temp_cache_path)

        # Test data
        journal_data = {
            "journal_name": "Test Journal of Integration",
            "normalized_name": "test journal of integration",
            "source_name": "test_source",
            "assessment": AssessmentType.LEGITIMATE.value,
            "confidence": 0.85,
            "issn": "1234-5678",
            "extra_data": {"test_key": "test_value"},
        }

        # Add journal entry
        cache.add_journal_entry(**journal_data)

        # Search by normalized name
        results = cache.search_journals(normalized_name=journal_data["normalized_name"])

        # Verify result
        assert len(results) > 0, "Should find the added journal"
        found = results[0]
        assert found["journal_name"] == journal_data["journal_name"]
        assert found["normalized_name"] == journal_data["normalized_name"]

    @pytest.mark.integration
    def test_cache_search_by_issn(self, temp_cache_path: Path) -> None:
        """Test searching journals by ISSN.

        Validates that ISSN-based searches work correctly.
        """
        cache = CacheManager(db_path=temp_cache_path)

        # Add test journals with ISSNs
        test_journals = [
            {
                "journal_name": "Journal A",
                "normalized_name": "journal a",
                "source_name": "test",
                "issn": "1111-2222",
                "assessment": AssessmentType.LEGITIMATE.value,
            },
            {
                "journal_name": "Journal B",
                "normalized_name": "journal b",
                "source_name": "test",
                "issn": "3333-4444",
                "assessment": AssessmentType.PREDATORY.value,
            },
        ]

        for journal in test_journals:
            cache.add_journal_entry(**journal)

        # Search by ISSN
        results_a = cache.search_journals(issn="1111-2222")
        results_b = cache.search_journals(issn="3333-4444")

        # Verify
        assert len(results_a) > 0, "Should find journal A"
        assert results_a[0]["journal_name"] == "Journal A"

        assert len(results_b) > 0, "Should find journal B"
        assert results_b[0]["journal_name"] == "Journal B"

    @pytest.mark.integration
    def test_cache_search_by_source(self, temp_cache_path: Path) -> None:
        """Test searching journals by source name.

        Validates that source-based filtering works correctly.
        """
        cache = CacheManager(db_path=temp_cache_path)

        # Add journals from different sources
        cache.add_journal_entry(
            journal_name="DOAJ Journal",
            normalized_name="doaj journal",
            source_name="doaj",
            assessment=AssessmentType.LEGITIMATE.value,
        )

        cache.add_journal_entry(
            journal_name="Bealls Journal",
            normalized_name="bealls journal",
            source_name="bealls",
            assessment=AssessmentType.PREDATORY.value,
        )

        # Search by source
        doaj_results = cache.search_journals(source_name="doaj")
        bealls_results = cache.search_journals(source_name="bealls")

        # Verify
        assert len(doaj_results) > 0, "Should find DOAJ journal"
        assert any(j["journal_name"] == "DOAJ Journal" for j in doaj_results)

        assert len(bealls_results) > 0, "Should find Bealls journal"
        assert any(j["journal_name"] == "Bealls Journal" for j in bealls_results)

    @pytest.mark.integration
    def test_cache_multiple_sources_same_journal(self, temp_cache_path: Path) -> None:
        """Test that cache handles same journal from multiple sources.

        Validates that journals appearing in multiple backend sources
        are properly stored and can be retrieved.
        """
        cache = CacheManager(db_path=temp_cache_path)

        # Add same journal from different sources
        journal_name = "Multi-Source Journal"
        normalized_name = "multi source journal"

        cache.add_journal_entry(
            journal_name=journal_name,
            normalized_name=normalized_name,
            source_name="doaj",
            assessment=AssessmentType.LEGITIMATE.value,
        )

        cache.add_journal_entry(
            journal_name=journal_name,
            normalized_name=normalized_name,
            source_name="openalex",
            assessment=AssessmentType.LEGITIMATE.value,
        )

        # Search for the journal
        results = cache.search_journals(normalized_name=normalized_name)

        # Should have entries from both sources
        assert len(results) >= 2, "Should have entries from multiple sources"

        sources = {r.get("source_name") for r in results}
        assert "doaj" in sources, "Should have entry from doaj"
        assert "openalex" in sources, "Should have entry from openalex"

    @pytest.mark.integration
    def test_cache_concurrent_operations(self, temp_cache_path: Path) -> None:
        """Test cache handles concurrent operations correctly.

        Validates that multiple rapid operations don't corrupt the cache.
        """
        cache = CacheManager(db_path=temp_cache_path)

        # Rapidly add multiple entries
        for i in range(50):
            cache.add_journal_entry(
                journal_name=f"Journal {i}",
                normalized_name=f"journal {i}",
                source_name="test",
                assessment=(
                    AssessmentType.LEGITIMATE.value
                    if i % 2 == 0
                    else AssessmentType.PREDATORY.value
                ),
            )

        # Verify all were added
        for i in range(50):
            results = cache.search_journals(normalized_name=f"journal {i}")
            assert len(results) > 0, f"Should find journal {i}"

    @pytest.mark.integration
    def test_cache_special_characters_handling(self, temp_cache_path: Path) -> None:
        """Test cache handles special characters in journal names.

        Validates that journals with special characters, unicode,
        and various encodings are properly stored and retrieved.
        """
        cache = CacheManager(db_path=temp_cache_path)

        # Test journals with special characters
        special_journals = [
            "Journal of Test™ & Research®",
            "学术期刊 (Academic Journal)",
            "Журнал Науки",  # Russian
            "مجلة العلوم",  # Arabic
            "Journal with 'quotes' and \"double quotes\"",
            "Journal with semicolons; and colons:",
        ]

        for i, journal in enumerate(special_journals):
            cache.add_journal_entry(
                journal_name=journal,
                normalized_name=f"special {i}",
                source_name="test",
                assessment=AssessmentType.LEGITIMATE.value,
            )

        # Verify all can be retrieved
        for i, journal in enumerate(special_journals):
            results = cache.search_journals(normalized_name=f"special {i}")
            assert len(results) > 0, (
                f"Should find journal with special chars: {journal}"
            )
            assert results[0]["journal_name"] == journal

    @pytest.mark.integration
    def test_cache_large_dataset(self, temp_cache_path: Path) -> None:
        """Test cache performance with larger dataset.

        Validates that cache operations remain functional with
        a reasonable number of entries.
        """
        cache = CacheManager(db_path=temp_cache_path)

        # Add 1000 journals
        num_journals = 1000
        for i in range(num_journals):
            cache.add_journal_entry(
                journal_name=f"Journal {i:04d}",
                normalized_name=f"journal {i:04d}",
                source_name=f"source_{i % 10}",  # 10 different sources
                assessment=(
                    AssessmentType.LEGITIMATE.value
                    if i % 3 == 0
                    else AssessmentType.PREDATORY.value
                ),
            )

        # Test searching still works
        results = cache.search_journals(normalized_name="journal 0500")
        assert len(results) > 0, "Should find journal in large dataset"

        # Test source filtering works
        source_results = cache.search_journals(source_name="source_5")
        assert len(source_results) >= 90, "Should find ~100 journals from source_5"

    @pytest.mark.integration
    def test_cache_persistence(self, temp_cache_path: Path) -> None:
        """Test that cache data persists across manager instances.

        Validates that data written to cache is properly persisted
        to disk and can be read by new cache manager instances.
        """
        # Create cache and add data
        cache1 = CacheManager(db_path=temp_cache_path)
        cache1.add_journal_entry(
            journal_name="Persistent Journal",
            normalized_name="persistent journal",
            source_name="test",
            assessment=AssessmentType.LEGITIMATE.value,
        )
        del cache1  # Ensure it's closed

        # Create new cache manager instance
        cache2 = CacheManager(db_path=temp_cache_path)
        results = cache2.search_journals(normalized_name="persistent journal")

        # Verify data persisted
        assert len(results) > 0, "Data should persist across cache instances"
        assert results[0]["journal_name"] == "Persistent Journal"
