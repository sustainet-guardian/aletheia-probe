# SPDX-License-Identifier: MIT
"""Tests for DBLP conference source."""

import gzip
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest
from defusedxml import ElementTree as DefusedET

from aletheia_probe.enums import AssessmentType
from aletheia_probe.updater.sources.dblp import DblpVenueSource


@pytest.fixture
def source(tmp_path: Path) -> DblpVenueSource:
    """Create DBLP source with test-friendly thresholds."""
    with patch("aletheia_probe.config.get_config_manager") as mock_config_manager:
        mock_config = Mock()
        mock_config.data_source_urls = Mock()
        mock_config.data_source_urls.dblp_xml_dump_url = (
            "https://dblp.org/xml/dblp.xml.gz"
        )
        mock_config_manager.return_value.load_config.return_value = mock_config

        return DblpVenueSource(
            data_dir=tmp_path / "dblp",
            min_entries_for_series=1,
            min_active_years=1,
            update_interval_days=30,
        )


def _write_gz(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write(content)


def test_get_name(source: DblpVenueSource):
    """Test source name."""
    assert source.get_name() == "dblp_venues"


def test_get_list_type(source: DblpVenueSource):
    """Test source list type."""
    assert source.get_list_type() == AssessmentType.LEGITIMATE


def test_should_update_when_dump_missing(source: DblpVenueSource):
    """Test update required when local dump file is missing."""
    with patch("aletheia_probe.updater.sources.dblp.DataSourceManager") as manager_cls:
        manager = Mock()
        manager.get_source_last_updated.return_value = datetime.now() - timedelta(
            days=1
        )
        manager_cls.return_value = manager
        assert source.should_update() is True


def test_should_update_recent_update(source: DblpVenueSource):
    """Test update skipped when source is fresh."""
    _write_gz(source.dump_path, "<dblp/>")
    with patch("aletheia_probe.updater.sources.dblp.DataSourceManager") as manager_cls:
        manager = Mock()
        manager.get_source_last_updated.return_value = datetime.now() - timedelta(
            days=2
        )
        manager_cls.return_value = manager
        assert source.should_update() is False


def test_parse_dump_file_extracts_conference_entries(source: DblpVenueSource):
    """Test parsing minimal DBLP XML into conference entries."""
    xml_content = """
<dblp>
  <proceedings key="conf/testconf/2024">
    <title>Proceedings of the Test Conference 2024</title>
    <booktitle>TestConf</booktitle>
    <year>2024</year>
  </proceedings>
  <inproceedings key="conf/testconf/2024/p1">
    <booktitle>TestConf</booktitle>
    <year>2024</year>
  </inproceedings>
  <article key="journals/tosem/Example">
    <title>Example Journal Article</title>
    <journal>ACM Transactions on Software Engineering and Methodology</journal>
    <year>2024</year>
    <issn>1049-331X</issn>
  </article>
</dblp>
"""
    _write_gz(source.dump_path, xml_content)

    journals = source._parse_dump_file()
    assert len(journals) >= 2

    conference_entries = [
        j
        for j in journals
        if j.get("metadata", {}).get("dblp_entry_type") == "conference"
    ]
    assert conference_entries
    first_conf = conference_entries[0]
    assert "journal_name" in first_conf
    assert "normalized_name" in first_conf
    assert first_conf["metadata"]["dblp_series"] == "testconf"
    assert first_conf["metadata"]["dblp_entry_count"] >= 2

    journal_entries = [
        j for j in journals if j.get("metadata", {}).get("dblp_entry_type") == "journal"
    ]
    assert journal_entries
    first_journal = journal_entries[0]
    assert first_journal["metadata"]["dblp_series"] == "tosem"


def test_parse_dump_file_handles_named_xml_entities(source: DblpVenueSource):
    """Test parser supports DBLP named entities like &uuml;."""
    xml_content = """
<dblp>
  <proceedings key="conf/entityconf/2024">
    <title>Proceedings M&uuml;nchen 2024</title>
    <booktitle>EntityConf</booktitle>
    <year>2024</year>
  </proceedings>
</dblp>
"""
    _write_gz(source.dump_path, xml_content)

    journals = source._parse_dump_file()
    assert journals


@pytest.mark.asyncio
async def test_fetch_data_uses_download_and_parse(source: DblpVenueSource):
    """Test fetch_data orchestration when local dump is missing."""
    with (
        patch.object(source, "_download_dump", new=AsyncMock()) as download_mock,
        patch.object(
            source,
            "_parse_dump_file",
            return_value=[{"journal_name": "Test", "normalized_name": "test"}],
        ) as parse_mock,
    ):
        result = await source.fetch_data()
        download_mock.assert_awaited_once()
        parse_mock.assert_called_once_with()
        assert len(result) == 1


@pytest.mark.asyncio
async def test_fetch_data_skips_download_when_dump_exists(source: DblpVenueSource):
    """Test fetch_data reuses local dump when it is present and parseable."""
    _write_gz(source.dump_path, "<dblp></dblp>")

    with (
        patch.object(source, "_download_dump", new=AsyncMock()) as download_mock,
        patch.object(
            source,
            "_parse_dump_file",
            return_value=[{"journal_name": "Cached", "normalized_name": "cached"}],
        ) as parse_mock,
    ):
        result = await source.fetch_data()
        download_mock.assert_not_awaited()
        parse_mock.assert_called_once_with()
        assert len(result) == 1


@pytest.mark.asyncio
async def test_fetch_data_redownloads_when_existing_dump_invalid(
    source: DblpVenueSource,
):
    """Test fetch_data re-downloads when existing local dump cannot be parsed."""
    _write_gz(source.dump_path, "<dblp><broken>")

    with (
        patch.object(source, "_download_dump", new=AsyncMock()) as download_mock,
        patch.object(
            source,
            "_parse_dump_file",
            side_effect=[
                DefusedET.ParseError("invalid xml"),
                [{"journal_name": "Recovered", "normalized_name": "recovered"}],
            ],
        ) as parse_mock,
    ):
        result = await source.fetch_data()
        download_mock.assert_awaited_once()
        assert parse_mock.call_count == 2
        assert len(result) == 1
