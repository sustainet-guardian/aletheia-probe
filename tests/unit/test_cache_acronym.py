# SPDX-License-Identifier: MIT
"""Tests for the cache assessment module."""

import hashlib
import logging
import tempfile
from pathlib import Path

import pytest

from aletheia_probe.cache import AcronymCache
from aletheia_probe.cache.schema import init_database


# from aletheia_probe.models import AssessmentResult, BackendResult, BackendStatus


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
            acronym="ICML", full_name="International Conference on Machine Learning"
        )

        # Verify the mapping was stored (returns normalized lowercase form)
        result = temp_cache.get_full_name_for_acronym("ICML")
        assert result == "international conference on machine learning"

    def test_store_acronym_mapping_case_insensitive(self, temp_cache):
        """Test that acronym lookup is case-insensitive."""
        temp_cache.store_acronym_mapping(
            acronym="CVPR", full_name="Conference on Computer Vision"
        )

        # Should work with different cases (returns normalized lowercase form)
        assert (
            temp_cache.get_full_name_for_acronym("CVPR")
            == "conference on computer vision"
        )
        assert (
            temp_cache.get_full_name_for_acronym("cvpr")
            == "conference on computer vision"
        )
        assert (
            temp_cache.get_full_name_for_acronym("CvPr")
            == "conference on computer vision"
        )

    def test_store_acronym_mapping_no_warn_on_year_variation(self, temp_cache, caplog):
        """Test that no warning is logged for year variations of same conference."""
        caplog.set_level(logging.WARNING)

        # Store initial mapping with year
        temp_cache.store_acronym_mapping(
            acronym="CVPR",
            full_name="2022 IEEE/CVF Conference on Computer Vision and Pattern Recognition",
        )

        # Store same conference without year - should not warn
        temp_cache.store_acronym_mapping(
            acronym="CVPR",
            full_name="IEEE/CVF Conference on Computer Vision and Pattern Recognition",
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
        )

        # Store without ordinal - should not warn
        temp_cache.store_acronym_mapping(
            acronym="ICML", full_name="International Conference on Machine Learning"
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
            acronym="AI", full_name="Artificial Intelligence Conference"
        )

        # Store different conference with same acronym - should warn
        temp_cache.store_acronym_mapping(
            acronym="AI", full_name="Algorithms and Informatics Symposium"
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
            source="bibtex_extraction",
        )

        # Verify the mapping exists (source is tracked internally, returns normalized form)
        result = temp_cache.get_full_name_for_acronym("NeurIPS")
        assert result == "neural information processing systems"

    # ToDo: checks internals! This will be fixed when the
    #       acroym table / function is split between journals and conferences.
    def test_are_conference_names_equivalent_identical(self, temp_cache):
        """Test equivalence check for identical names."""
        assert temp_cache._are_conference_names_equivalent(
            "Machine Learning Conference", "Machine Learning Conference"
        )

    def test_are_conference_names_equivalent_case_insensitive(self, temp_cache):
        """Test equivalence check is case-insensitive."""
        assert temp_cache._are_conference_names_equivalent(
            "Machine Learning Conference", "machine learning conference"
        )

    def test_are_conference_names_equivalent_year_prefix(self, temp_cache):
        """Test equivalence with year prefix."""
        assert temp_cache._are_conference_names_equivalent(
            "2022 IEEE/CVF Conference on Computer Vision",
            "IEEE/CVF Conference on Computer Vision",
        )

    def test_are_conference_names_equivalent_year_suffix(self, temp_cache):
        """Test equivalence with year suffix."""
        assert temp_cache._are_conference_names_equivalent(
            "Conference on Machine Learning 2023",
            "Conference on Machine Learning",
        )

    def test_are_conference_names_equivalent_edition_markers(self, temp_cache):
        """Test equivalence with edition markers."""
        assert temp_cache._are_conference_names_equivalent(
            "2022 edition International Conference",
            "International Conference",
        )
        assert temp_cache._are_conference_names_equivalent(
            "International Conference edition 2022",
            "International Conference",
        )

    def test_are_conference_names_equivalent_ordinals(self, temp_cache):
        """Test equivalence with ordinal numbers."""
        assert temp_cache._are_conference_names_equivalent(
            "37th International Conference on Machine Learning",
            "International Conference on Machine Learning",
        )
        assert temp_cache._are_conference_names_equivalent(
            "1st Workshop on Neural Networks",
            "Workshop on Neural Networks",
        )
        assert temp_cache._are_conference_names_equivalent(
            "22nd Annual Conference",
            "Annual Conference",
        )

    def test_are_conference_names_equivalent_different_conferences(self, temp_cache):
        """Test that truly different conferences are not equivalent."""
        assert not temp_cache._are_conference_names_equivalent(
            "Artificial Intelligence Conference",
            "Algorithms and Informatics Symposium",
        )
        assert not temp_cache._are_conference_names_equivalent("AAAI", "AI Conference")

    def test_are_conference_names_equivalent_substring_with_length_check(
        self, temp_cache
    ):
        """Test that short substrings don't match to avoid false positives."""
        # Short names (< 10 chars) should not match via substring
        assert not temp_cache._are_conference_names_equivalent("AI", "AAAI")
        assert not temp_cache._are_conference_names_equivalent("ML", "ICML")

        # But longer names can match via substring after year/ordinal removal
        assert temp_cache._are_conference_names_equivalent(
            "International Conference on Machine Learning and Applications",
            "International Conference on Machine Learning",
        )

    def test_are_conference_names_equivalent_complex_variations(self, temp_cache):
        """Test complex real-world variations."""
        # Real example from issue #90
        assert temp_cache._are_conference_names_equivalent(
            "2022 IEEE/CVF Conference on Computer Vision and Pattern Recognition",
            "IEEE/CVF Conference on Computer Vision and Pattern Recognition",
        )

        # Multiple years in name
        assert temp_cache._are_conference_names_equivalent(
            "2023 25th International Conference",
            "International Conference",
        )

    def test_store_acronym_mapping_overwrites_with_latest(self, temp_cache):
        """Test that newer mappings overwrite older ones."""
        # Store initial mapping
        temp_cache.store_acronym_mapping(
            acronym="TEST", full_name="Test Conference 2022"
        )

        # Store updated mapping (equivalent, just different year)
        temp_cache.store_acronym_mapping(
            acronym="TEST", full_name="Test Conference 2023"
        )

        # Both normalize to the same generic form (years stripped)
        result = temp_cache.get_full_name_for_acronym("TEST")
        assert result == "test conference"
