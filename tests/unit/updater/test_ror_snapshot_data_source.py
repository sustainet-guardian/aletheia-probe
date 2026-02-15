# SPDX-License-Identifier: MIT
"""Tests for ROR snapshot data source."""

from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from aletheia_probe.enums import AssessmentType
from aletheia_probe.updater.sources.ror_snapshot import RorSnapshotSource


@pytest.fixture
def mocked_config():
    """Create mocked config manager for ROR URLs."""
    with patch("aletheia_probe.config.get_config_manager") as mock_config_manager:
        mock_config = Mock()
        mock_config.data_source_urls = Mock()
        mock_config.data_source_urls.ror_snapshot_archive_url = (
            "https://example.org/ror-data-v2.2-2026-01-29.zip"
        )
        mock_config.data_source_urls.ror_snapshot_concept_doi_url = (
            "https://zenodo.org/doi/10.5281/zenodo.6347574"
        )
        mock_config_manager.return_value.load_config.return_value = mock_config
        yield


def test_ror_source_basics(mocked_config):
    """Test source metadata."""
    source = RorSnapshotSource(data_dir=Path("/tmp/ror-test"))
    assert source.get_name() == "ror_snapshot"
    assert source.get_list_type() == AssessmentType.MIXED
    assert source.allow_empty_data_success is True


def test_should_update_no_last_update(mocked_config):
    """Test update decision when no prior update exists."""
    source = RorSnapshotSource(data_dir=Path("/tmp/ror-test"))
    with patch(
        "aletheia_probe.updater.sources.ror_snapshot.DataSourceManager"
    ) as mock_dsm:
        mock_cache = Mock()
        mock_cache.get_source_last_updated.return_value = None
        mock_dsm.return_value = mock_cache
        assert source.should_update() is True


def test_should_update_recent_update_skips(mocked_config):
    """Test update decision when source is fresh."""
    source = RorSnapshotSource(data_dir=Path("/tmp/ror-test"))
    with patch(
        "aletheia_probe.updater.sources.ror_snapshot.DataSourceManager"
    ) as mock_dsm:
        mock_cache = Mock()
        mock_cache.get_source_last_updated.return_value = datetime.now() - timedelta(
            days=5
        )
        mock_dsm.return_value = mock_cache
        assert source.should_update() is False


@pytest.mark.asyncio
async def test_fetch_data_runs_import_side_effect(mocked_config):
    """Test fetch_data download/import flow and empty return contract."""
    source = RorSnapshotSource(data_dir=Path("/tmp/ror-test"))

    with patch(
        "aletheia_probe.updater.sources.ror_snapshot.RorSnapshotImporter"
    ) as mock_importer_class:
        importer = mock_importer_class.return_value
        importer.download_archive = AsyncMock(
            return_value=Path("/tmp/ror-test/ror-data-v2.2-2026-01-29.zip")
        )
        importer.import_archive.return_value = 12
        with patch.object(
            source,
            "_resolve_latest_archive_details",
            new=AsyncMock(
                return_value=(
                    "https://zenodo.org/api/records/18419061/files/v2.2-2026-01-29-ror-data.zip/content",
                    "v2.2",
                    date(2026, 1, 29),
                )
            ),
        ):
            result = await source.fetch_data()

            assert result == []
            importer.download_archive.assert_awaited_once()
            importer.import_archive.assert_called_once()


def test_extract_metadata_from_archive_name():
    """Test metadata extraction from ROR archive filename."""
    ror_version, release_date = RorSnapshotSource._extract_metadata_from_archive_name(
        "ror-data-v2.2-2026-01-29.zip"
    )
    assert ror_version == "v2.2"
    assert release_date == date(2026, 1, 29)


def test_extract_metadata_from_archive_name_fallback():
    """Test metadata extraction fallback for unknown filename patterns."""
    ror_version, release_date = RorSnapshotSource._extract_metadata_from_archive_name(
        "ror-latest.zip"
    )
    assert ror_version == "unknown"
    assert isinstance(release_date, date)


def test_extract_doi_from_zenodo_url():
    """Test DOI extraction from Zenodo DOI URL."""
    doi = RorSnapshotSource._extract_doi(
        "https://zenodo.org/doi/10.5281/zenodo.6347574"
    )
    assert doi == "10.5281/zenodo.6347574"


def test_extract_doi_fallback_none():
    """Test DOI extraction returns None for non-DOI text."""
    assert RorSnapshotSource._extract_doi("not a doi") is None
