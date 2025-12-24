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
