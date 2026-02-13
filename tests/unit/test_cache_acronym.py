# SPDX-License-Identifier: MIT
"""Tests for AcronymCache — venue_acronyms table and variant lookup."""

import json
import logging
import tempfile
from pathlib import Path

import pytest

from aletheia_probe.cache import AcronymCache
from aletheia_probe.cache.schema import init_database


@pytest.fixture
def temp_cache():
    """Create a temporary cache for testing with all cache components."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        cache_path = Path(f.name)

    # Initialize database schema
    init_database(cache_path)

    cache = AcronymCache(cache_path)
    yield cache

    # Cleanup
    cache_path.unlink(missing_ok=True)


class TestAcronymMapping:
    """Test cases for conference acronym mapping functionality."""

    def test_store_acronym_mapping_new_entry(self, temp_cache):
        """Test storing a new acronym mapping."""
        temp_cache.store_acronym_mapping(
            acronym="ICML",
            full_name="International Conference on Machine Learning",
            entity_type="conference",
        )

        # Verify the mapping was stored (returns normalized lowercase form)
        result = temp_cache.get_full_name_for_acronym("ICML", "conference")
        assert result == "international conference on machine learning"

    def test_store_acronym_mapping_case_insensitive(self, temp_cache):
        """Test that acronym lookup is case-insensitive."""
        temp_cache.store_acronym_mapping(
            acronym="CVPR",
            full_name="Conference on Computer Vision",
            entity_type="conference",
        )

        # Should work with different cases (returns normalized lowercase form)
        assert (
            temp_cache.get_full_name_for_acronym("CVPR", "conference")
            == "conference on computer vision"
        )
        assert (
            temp_cache.get_full_name_for_acronym("cvpr", "conference")
            == "conference on computer vision"
        )
        assert (
            temp_cache.get_full_name_for_acronym("CvPr", "conference")
            == "conference on computer vision"
        )

    def test_store_acronym_mapping_no_warn_on_year_variation(self, temp_cache, caplog):
        """Test that no warning is logged for year variations of same conference."""
        caplog.set_level(logging.WARNING)

        # Store initial mapping with year
        temp_cache.store_acronym_mapping(
            acronym="CVPR",
            full_name="2022 IEEE/CVF Conference on Computer Vision and Pattern Recognition",
            entity_type="conference",
        )

        # Store same conference without year - should not warn
        temp_cache.store_acronym_mapping(
            acronym="CVPR",
            full_name="IEEE/CVF Conference on Computer Vision and Pattern Recognition",
            entity_type="conference",
        )

        # Verify no warning was logged
        warnings = [
            record for record in caplog.records if record.levelname == "WARNING"
        ]
        assert len(warnings) == 0

    def test_store_acronym_mapping_no_warn_on_ordinal_variation(
        self, temp_cache, caplog
    ):
        """Test that no warning is logged for ordinal variations."""
        caplog.set_level(logging.WARNING)

        # Store with ordinal
        temp_cache.store_acronym_mapping(
            acronym="ICML",
            full_name="37th International Conference on Machine Learning",
            entity_type="conference",
        )

        # Store without ordinal - should not warn
        temp_cache.store_acronym_mapping(
            acronym="ICML",
            full_name="International Conference on Machine Learning",
            entity_type="conference",
        )

        # Verify no warning was logged
        warnings = [
            record for record in caplog.records if record.levelname == "WARNING"
        ]
        assert len(warnings) == 0

    def test_store_acronym_mapping_warns_on_different_conferences(
        self, temp_cache, caplog
    ):
        """Test that warning is logged when acronym maps to truly different conferences."""
        caplog.set_level(logging.WARNING)

        # Store first conference
        temp_cache.store_acronym_mapping(
            acronym="AI",
            full_name="Artificial Intelligence Conference",
            entity_type="conference",
        )

        # Store different conference with same acronym - should warn
        temp_cache.store_acronym_mapping(
            acronym="AI",
            full_name="Algorithms and Informatics Symposium",
            entity_type="conference",
        )

        # Verify warning was logged
        warnings = [
            record for record in caplog.records if record.levelname == "WARNING"
        ]
        assert len(warnings) == 1
        assert "already maps to" in warnings[0].message
        assert "artificial intelligence conference" in warnings[0].message

    def test_store_acronym_mapping_source_tracking(self, temp_cache):
        """Test that the source of acronym mappings is tracked."""
        temp_cache.store_acronym_mapping(
            acronym="NeurIPS",
            full_name="Neural Information Processing Systems",
            entity_type="conference",
            source="bibtex_extraction",
        )

        # Verify the mapping exists (source is tracked internally, returns normalized form)
        result = temp_cache.get_full_name_for_acronym("NeurIPS", "conference")
        assert result == "neural information processing systems"

    def test_store_acronym_mapping_overwrites_with_latest(self, temp_cache):
        """Test that newer mappings overwrite older ones."""
        # Store initial mapping
        temp_cache.store_acronym_mapping(
            acronym="TEST", full_name="Test Conference 2022", entity_type="conference"
        )

        # Store updated mapping (equivalent, just different year)
        temp_cache.store_acronym_mapping(
            acronym="TEST", full_name="Test Conference 2023", entity_type="conference"
        )

        # Both normalize to the same generic form (years stripped)
        result = temp_cache.get_full_name_for_acronym("TEST", "conference")
        assert result == "test conference"


@pytest.fixture
def preloaded_cache(temp_cache):
    """AcronymCache with pipeline-format entries (import_acronyms)."""
    entries = [
        {
            "acronym": "ICML",
            "entity_type": "conference",
            "canonical": "international conference on machine learning",
            "confidence_score": 0.95,
            "issn": [],
            "variants": [
                "international conference on machine learning",
                "proc. int. conf. mach. learn.",
                "icml proceedings",
            ],
        },
        {
            "acronym": "TOSN",
            "entity_type": "journal",
            "canonical": "acm transactions on sensor networks",
            "confidence_score": 0.89,
            "issn": ["1550-4859", "1550-4867"],
            "variants": [
                "acm transactions on sensor networks",
                "acm trans. sens. networks",
                "transactions on sensor networks",
            ],
        },
    ]
    temp_cache.import_acronyms(entries)
    return temp_cache


class TestImportAcronyms:
    """Tests for bulk import via import_acronyms()."""

    def test_import_returns_count(self, temp_cache):
        """import_acronyms returns number of rows inserted."""
        entries = [
            {
                "acronym": "AAAI",
                "entity_type": "conference",
                "canonical": "aaai conference on artificial intelligence",
                "confidence_score": 0.9,
                "issn": [],
                "variants": ["aaai conference on artificial intelligence"],
            }
        ]
        assert temp_cache.import_acronyms(entries) == 1

    def test_import_empty_list(self, temp_cache):
        assert temp_cache.import_acronyms([]) == 0

    def test_import_skips_incomplete_entries(self, temp_cache):
        entries = [
            {"acronym": "X", "entity_type": "conference"},  # missing canonical
            {
                "acronym": "AAAI",
                "entity_type": "conference",
                "canonical": "aaai conference on artificial intelligence",
                "issn": [],
                "variants": [],
            },
        ]
        assert temp_cache.import_acronyms(entries) == 1

    def test_import_upsert_replaces_canonical(self, temp_cache):
        """Re-importing the same acronym replaces the existing row."""
        temp_cache.import_acronyms(
            [
                {
                    "acronym": "AAAI",
                    "entity_type": "conference",
                    "canonical": "old canonical name",
                    "issn": [],
                    "variants": [],
                }
            ]
        )
        temp_cache.import_acronyms(
            [
                {
                    "acronym": "AAAI",
                    "entity_type": "conference",
                    "canonical": "aaai conference on artificial intelligence",
                    "issn": [],
                    "variants": [],
                }
            ]
        )
        assert (
            temp_cache.get_full_name_for_acronym("AAAI", "conference")
            == "aaai conference on artificial intelligence"
        )
        assert temp_cache.get_acronym_stats()["total_count"] == 1

    def test_import_from_v2_json_file(self, temp_cache, tmp_path):
        """import_from_file reads a v2.0 pipeline JSON file."""
        data = {
            "version": "2.0",
            "acronyms": [
                {
                    "acronym": "CVPR",
                    "entity_type": "conference",
                    "canonical": "ieee conference on computer vision and pattern recognition",
                    "confidence_score": 0.92,
                    "issn": [],
                    "variants": [
                        "ieee conference on computer vision and pattern recognition",
                        "cvpr proceedings",
                    ],
                }
            ],
        }
        json_path = tmp_path / "acronyms-2025-01.json"
        json_path.write_text(json.dumps(data), encoding="utf-8")

        count = temp_cache.import_from_file(json_path)
        assert count == 1
        assert (
            temp_cache.get_full_name_for_acronym("CVPR", "conference")
            == "ieee conference on computer vision and pattern recognition"
        )


class TestGetCanonicalForVariant:
    """Tests for variant-based reverse lookup (get_canonical_for_variant)."""

    def test_abbreviated_variant_found(self, preloaded_cache):
        result = preloaded_cache.get_canonical_for_variant(
            "acm trans. sens. networks", "journal"
        )
        assert result == "acm transactions on sensor networks"

    def test_variant_case_insensitive(self, preloaded_cache):
        result = preloaded_cache.get_canonical_for_variant(
            "ACM Trans. Sens. Networks", "journal"
        )
        assert result == "acm transactions on sensor networks"

    def test_canonical_itself_is_a_variant(self, preloaded_cache):
        """Canonical form should also be findable via get_canonical_for_variant."""
        result = preloaded_cache.get_canonical_for_variant(
            "acm transactions on sensor networks", "journal"
        )
        assert result == "acm transactions on sensor networks"

    def test_conference_abbreviated_variant(self, preloaded_cache):
        result = preloaded_cache.get_canonical_for_variant(
            "proc. int. conf. mach. learn.", "conference"
        )
        assert result == "international conference on machine learning"

    def test_no_match_returns_none(self, preloaded_cache):
        result = preloaded_cache.get_canonical_for_variant(
            "nonexistent abbreviated form", "conference"
        )
        assert result is None

    def test_wrong_entity_type_returns_none(self, preloaded_cache):
        # TOSN variants belong to 'journal'; querying as 'conference' should fail
        result = preloaded_cache.get_canonical_for_variant(
            "acm trans. sens. networks", "conference"
        )
        assert result is None

    def test_leading_trailing_whitespace_stripped(self, preloaded_cache):
        result = preloaded_cache.get_canonical_for_variant(
            "  acm trans. sens. networks  ", "journal"
        )
        assert result == "acm transactions on sensor networks"


class TestGetVariants:
    """Tests for get_variants()."""

    def test_variants_returned(self, preloaded_cache):
        variants = preloaded_cache.get_variants("TOSN", "journal")
        assert "acm trans. sens. networks" in variants
        assert "transactions on sensor networks" in variants

    def test_variants_not_found(self, preloaded_cache):
        assert preloaded_cache.get_variants("UNKNOWN", "journal") == []


class TestStats:
    """Tests for get_acronym_stats() and clear_acronym_database()."""

    def test_stats_total(self, preloaded_cache):
        assert preloaded_cache.get_acronym_stats()["total_count"] == 2

    def test_stats_by_entity_type(self, preloaded_cache):
        assert (
            preloaded_cache.get_acronym_stats(entity_type="journal")["total_count"] == 1
        )
        assert (
            preloaded_cache.get_acronym_stats(entity_type="conference")["total_count"]
            == 1
        )

    def test_clear_all(self, preloaded_cache):
        deleted = preloaded_cache.clear_acronym_database()
        assert deleted == 2
        assert preloaded_cache.get_acronym_stats()["total_count"] == 0

    def test_clear_by_entity_type(self, preloaded_cache):
        deleted = preloaded_cache.clear_acronym_database(entity_type="journal")
        assert deleted == 1
        assert preloaded_cache.get_acronym_stats()["total_count"] == 1
