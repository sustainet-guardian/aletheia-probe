# SPDX-License-Identifier: MIT
"""Tests for the acronym exporter module."""

import json
import tempfile
from pathlib import Path

import pytest

from aletheia_probe.acronym_exporter import (
    AcronymExporter,
    AcronymExportRecord,
    ExportOptions,
    ExportStatistics,
)
from aletheia_probe.cache import AcronymCache
from aletheia_probe.cache.schema import init_database


@pytest.fixture
def temp_cache():
    """Create a temporary cache for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        cache_path = Path(f.name)

    init_database(cache_path)

    cache = AcronymCache(cache_path)
    yield cache

    cache_path.unlink(missing_ok=True)


@pytest.fixture
def populated_cache(temp_cache):
    """Create a cache with sample acronym data."""
    # Add conference acronyms
    temp_cache.store_acronym_mapping(
        acronym="ICML",
        full_name="International Conference on Machine Learning",
        entity_type="conference",
        source="bibtex_extraction",
    )
    temp_cache.store_acronym_mapping(
        acronym="NeurIPS",
        full_name="Conference on Neural Information Processing Systems",
        entity_type="conference",
        source="bibtex_extraction",
    )
    temp_cache.store_acronym_mapping(
        acronym="CVPR",
        full_name="Conference on Computer Vision and Pattern Recognition",
        entity_type="conference",
        source="bibtex_extraction",
    )

    # Add journal acronyms
    temp_cache.store_acronym_mapping(
        acronym="JMLR",
        full_name="Journal of Machine Learning Research",
        entity_type="journal",
        source="bibtex_extraction",
    )
    temp_cache.store_acronym_mapping(
        acronym="TPAMI",
        full_name="IEEE Transactions on Pattern Analysis and Machine Intelligence",
        entity_type="journal",
        source="bibtex_extraction",
    )

    # Add an ambiguous acronym by marking existing
    temp_cache.mark_acronym_as_ambiguous("ICML", "conference")

    return temp_cache


@pytest.fixture
def temp_output_path():
    """Create a temporary output path for export tests."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        output_path = Path(f.name)

    yield output_path

    output_path.unlink(missing_ok=True)


class TestAcronymExportRecord:
    """Tests for AcronymExportRecord dataclass."""

    def test_to_variant_dict(self):
        """Test converting record to variant dictionary."""
        record = AcronymExportRecord(
            acronym="ICML",
            entity_type="conference",
            variant_name="international conference on machine learning",
            normalized_name="international conference on machine learning",
            usage_count=42,
            is_ambiguous=False,
        )

        result = record.to_variant_dict()

        # Should only include variant-level fields
        assert "acronym" not in result
        assert "entity_type" not in result
        assert "is_ambiguous" not in result  # Moved to entity_type level
        assert result["variant_name"] == "international conference on machine learning"
        assert (
            result["normalized_name"] == "international conference on machine learning"
        )
        assert result["count"] == 42


class TestExportStatistics:
    """Tests for ExportStatistics dataclass."""

    def test_to_dict_empty(self):
        """Test converting empty statistics to dictionary."""
        stats = ExportStatistics()

        result = stats.to_dict()

        assert result["total_records"] == 0
        assert result["unique_acronyms"] == 0
        assert result["by_entity_type"] == {}
        assert result["ambiguous_count"] == 0
        assert result["ambiguity_rate"] == 0.0

    def test_to_dict_with_data(self):
        """Test converting populated statistics to dictionary."""
        stats = ExportStatistics(
            total_records=100,
            unique_acronyms=80,
            by_entity_type={"conference": 60, "journal": 40},
            ambiguous_count=5,
            ambiguity_rate=0.0625,
        )

        result = stats.to_dict()

        assert result["total_records"] == 100
        assert result["unique_acronyms"] == 80
        assert result["by_entity_type"] == {"conference": 60, "journal": 40}
        assert result["ambiguous_count"] == 5
        assert result["ambiguity_rate"] == 0.0625


class TestAcronymExporter:
    """Tests for AcronymExporter class."""

    def test_fetch_all_variants_empty(self, temp_cache):
        """Test fetching variants from empty cache."""
        exporter = AcronymExporter(temp_cache)

        records = exporter.fetch_all_variants()

        assert records == []

    def test_fetch_all_variants_with_data(self, populated_cache):
        """Test fetching variants from populated cache."""
        exporter = AcronymExporter(populated_cache)

        records = exporter.fetch_all_variants()

        assert len(records) == 5
        acronyms = {r.acronym for r in records}
        assert "ICML" in acronyms
        assert "NeurIPS" in acronyms
        assert "CVPR" in acronyms
        assert "JMLR" in acronyms
        assert "TPAMI" in acronyms

    def test_fetch_all_variants_with_min_usage_filter(self, populated_cache):
        """Test filtering by minimum usage count."""
        exporter = AcronymExporter(populated_cache)

        # All entries have usage_count=1, so min_usage=2 should return empty
        records = exporter.fetch_all_variants(min_usage_count=2)

        assert records == []

    def test_fetch_all_variants_with_entity_type_filter(self, populated_cache):
        """Test filtering by entity type."""
        exporter = AcronymExporter(populated_cache)

        records = exporter.fetch_all_variants(entity_type="conference")

        assert len(records) == 3
        for record in records:
            assert record.entity_type == "conference"

        records = exporter.fetch_all_variants(entity_type="journal")

        assert len(records) == 2
        for record in records:
            assert record.entity_type == "journal"

    def test_compute_statistics_empty(self, temp_cache):
        """Test computing statistics from empty records."""
        exporter = AcronymExporter(temp_cache)

        stats = exporter.compute_statistics([])

        assert stats.total_records == 0
        assert stats.unique_acronyms == 0
        assert stats.by_entity_type == {}
        assert stats.ambiguous_count == 0
        assert stats.ambiguity_rate == 0.0

    def test_compute_statistics_with_data(self, populated_cache):
        """Test computing statistics from populated records."""
        exporter = AcronymExporter(populated_cache)
        records = exporter.fetch_all_variants()

        stats = exporter.compute_statistics(records)

        assert stats.total_records == 5
        assert stats.unique_acronyms == 5
        assert stats.by_entity_type["conference"] == 3
        assert stats.by_entity_type["journal"] == 2
        assert stats.ambiguous_count == 1  # ICML marked as ambiguous
        assert stats.ambiguity_rate == 0.2  # 1/5

    def test_export_to_json_creates_valid_file(self, populated_cache, temp_output_path):
        """Test that export creates a valid JSON file."""
        exporter = AcronymExporter(populated_cache)
        options = ExportOptions(output_path=temp_output_path)

        exporter.export_to_json(options)

        assert temp_output_path.exists()

        with temp_output_path.open() as f:
            data = json.load(f)

        assert "metadata" in data
        assert "statistics" in data
        assert "acronyms" in data

    def test_export_to_json_metadata(self, populated_cache, temp_output_path):
        """Test that export metadata is correct."""
        exporter = AcronymExporter(populated_cache)
        options = ExportOptions(
            output_path=temp_output_path,
            min_usage_count=1,
            entity_type_filter=None,
        )

        result = exporter.export_to_json(options)

        metadata = result["metadata"]
        assert "generated_at" in metadata
        assert metadata["generator"] == "aletheia-probe"
        assert "version" in metadata
        assert metadata["parameters"]["min_usage_count"] == 1
        assert metadata["parameters"]["entity_type_filter"] is None
        assert metadata["license"] == "CC-BY-4.0"

    def test_export_to_json_statistics(self, populated_cache, temp_output_path):
        """Test that export statistics are correct."""
        exporter = AcronymExporter(populated_cache)
        options = ExportOptions(output_path=temp_output_path)

        result = exporter.export_to_json(options)

        stats = result["statistics"]
        assert stats["total_records"] == 5
        assert stats["unique_acronyms"] == 5
        assert "conference" in stats["by_entity_type"]
        assert "journal" in stats["by_entity_type"]

    def test_export_to_json_acronyms(self, populated_cache, temp_output_path):
        """Test that exported acronyms have hierarchical structure."""
        exporter = AcronymExporter(populated_cache)
        options = ExportOptions(output_path=temp_output_path)

        result = exporter.export_to_json(options)

        acronyms = result["acronyms"]

        # Should be a dict keyed by acronym
        assert isinstance(acronyms, dict)
        assert len(acronyms) == 5  # 5 unique acronyms

        # Check structure: acronym -> entity_type -> {is_ambiguous, variants}
        assert "ICML" in acronyms
        assert "conference" in acronyms["ICML"]
        assert "is_ambiguous" in acronyms["ICML"]["conference"]
        assert "variants" in acronyms["ICML"]["conference"]
        assert isinstance(acronyms["ICML"]["conference"]["variants"], list)

        # Check that each variant has expected fields
        for acronym_key, entity_types in acronyms.items():
            for entity_type, entity_data in entity_types.items():
                assert "is_ambiguous" in entity_data
                assert "variants" in entity_data
                for variant in entity_data["variants"]:
                    assert "acronym" not in variant
                    assert "entity_type" not in variant
                    assert "is_ambiguous" not in variant  # At entity_type level
                    assert "variant_name" in variant
                    assert "normalized_name" in variant
                    assert "count" in variant

    def test_export_to_json_with_entity_type_filter(
        self, populated_cache, temp_output_path
    ):
        """Test export with entity type filter."""
        exporter = AcronymExporter(populated_cache)
        options = ExportOptions(
            output_path=temp_output_path,
            entity_type_filter="conference",
        )

        result = exporter.export_to_json(options)

        assert result["statistics"]["total_records"] == 3
        # All acronyms should only have "conference" entity type
        for acronym_key, entity_types in result["acronyms"].items():
            assert list(entity_types.keys()) == ["conference"]
            assert "is_ambiguous" in entity_types["conference"]
            assert "variants" in entity_types["conference"]

    def test_export_to_json_creates_parent_directories(self, populated_cache):
        """Test that export creates parent directories if needed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            nested_path = Path(tmpdir) / "subdir" / "another" / "output.json"

            exporter = AcronymExporter(populated_cache)
            options = ExportOptions(output_path=nested_path)

            exporter.export_to_json(options)

            assert nested_path.exists()

    def test_export_to_json_returns_data(self, populated_cache, temp_output_path):
        """Test that export returns the data structure."""
        exporter = AcronymExporter(populated_cache)
        options = ExportOptions(output_path=temp_output_path)

        result = exporter.export_to_json(options)

        assert isinstance(result, dict)
        assert "metadata" in result
        assert "statistics" in result
        assert "acronyms" in result


class TestGetAllVariantsForExport:
    """Tests for the get_all_variants_for_export method in AcronymCache."""

    def test_get_all_variants_for_export_empty(self, temp_cache):
        """Test fetching from empty database."""
        result = temp_cache.get_all_variants_for_export()

        assert result == []

    def test_get_all_variants_for_export_returns_all_fields(self, populated_cache):
        """Test that all required fields are returned."""
        result = populated_cache.get_all_variants_for_export()

        assert len(result) > 0

        for variant in result:
            assert "acronym" in variant
            assert "entity_type" in variant
            assert "variant_name" in variant
            assert "normalized_name" in variant
            assert "usage_count" in variant
            assert "is_canonical" in variant
            assert "is_ambiguous" in variant

    def test_get_all_variants_for_export_min_usage_filter(self, populated_cache):
        """Test minimum usage count filter."""
        # All test entries have usage_count=1
        result = populated_cache.get_all_variants_for_export(min_usage_count=1)
        assert len(result) == 5

        result = populated_cache.get_all_variants_for_export(min_usage_count=2)
        assert len(result) == 0

    def test_get_all_variants_for_export_entity_type_filter(self, populated_cache):
        """Test entity type filter."""
        result = populated_cache.get_all_variants_for_export(entity_type="conference")
        assert len(result) == 3
        assert all(v["entity_type"] == "conference" for v in result)

        result = populated_cache.get_all_variants_for_export(entity_type="journal")
        assert len(result) == 2
        assert all(v["entity_type"] == "journal" for v in result)

    def test_get_all_variants_for_export_combined_filters(self, populated_cache):
        """Test combining multiple filters."""
        result = populated_cache.get_all_variants_for_export(
            min_usage_count=1,
            entity_type="conference",
        )

        assert len(result) == 3
        assert all(v["entity_type"] == "conference" for v in result)
        assert all(v["usage_count"] >= 1 for v in result)

    def test_get_all_variants_for_export_sorted_by_acronym(self, populated_cache):
        """Test that results are sorted by acronym."""
        result = populated_cache.get_all_variants_for_export()

        acronyms = [v["acronym"] for v in result]
        assert acronyms == sorted(acronyms)
