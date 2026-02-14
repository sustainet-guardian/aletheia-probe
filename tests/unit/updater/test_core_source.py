# SPDX-License-Identifier: MIT
"""Tests for CORE conference and journal data sources."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest

from aletheia_probe.enums import AssessmentType
from aletheia_probe.updater.sources.core import CoreConferenceSource, CoreJournalSource


@pytest.fixture
def mocked_config():
    """Create mocked config manager for CORE URLs."""
    with patch("aletheia_probe.config.get_config_manager") as mock_config_manager:
        mock_config = Mock()
        mock_config.data_source_urls = Mock()
        mock_config.data_source_urls.core_conference_rankings_url = (
            "https://portal.core.edu.au/conf-ranks/"
        )
        mock_config.data_source_urls.core_journal_rankings_url = (
            "https://portal.core.edu.au/jnl-ranks/"
        )
        mock_config.data_source_urls.core_conference_default_source = "ICORE2026"
        mock_config.data_source_urls.core_journal_default_source = "CORE2020"
        mock_config_manager.return_value.load_config.return_value = mock_config
        yield


def test_core_conference_source_basics(mocked_config):
    """Test source metadata for CORE conference source."""
    source = CoreConferenceSource()
    assert source.get_name() == "core_conferences"
    assert source.get_list_type() == AssessmentType.LEGITIMATE


def test_core_journal_source_basics(mocked_config):
    """Test source metadata for CORE journal source."""
    source = CoreJournalSource()
    assert source.get_name() == "core_journals"
    assert source.get_list_type() == AssessmentType.LEGITIMATE


def test_should_update_no_last_update(mocked_config):
    """Test update decision when no prior update exists."""
    source = CoreConferenceSource()
    with patch("aletheia_probe.updater.sources.core.DataSourceManager") as mock_dsm:
        mock_cache = Mock()
        mock_cache.get_source_last_updated.return_value = None
        mock_dsm.return_value = mock_cache
        assert source.should_update() is True


def test_should_update_recent_update_skips(mocked_config):
    """Test update decision when source is fresh."""
    source = CoreJournalSource()
    with patch("aletheia_probe.updater.sources.core.DataSourceManager") as mock_dsm:
        mock_cache = Mock()
        mock_cache.get_source_last_updated.return_value = datetime.now() - timedelta(
            days=10
        )
        mock_dsm.return_value = mock_cache
        assert source.should_update() is False


def test_parse_conference_entries_filters_unranked(mocked_config):
    """Test conference parser keeps only ranked CORE entries."""
    source = CoreConferenceSource()
    html = """
    Showing results 1 - 50 of 2
    <table>
      <tr class="evenrow">
        <td>Conference on Testing Systems</td>
        <td>CTS</td>
        <td>ICORE2026</td>
        <td>A</td>
      </tr>
      <tr class="oddrow">
        <td>Unknown Workshop</td>
        <td>UW</td>
        <td>ICORE2026</td>
        <td>Unranked</td>
      </tr>
    </table>
    """

    with patch(
        "aletheia_probe.updater.sources.core.input_normalizer.normalize"
    ) as norm:
        norm.return_value = Mock(normalized_name="conference on testing systems")
        entries = source._parse_entries(html)

    assert len(entries) == 1
    assert entries[0]["journal_name"] == "Conference on Testing Systems"
    assert entries[0]["metadata"]["core_rank"] == "A"
    assert entries[0]["metadata"]["core_entity_type"] == "conference"


def test_parse_journal_entries_filters_not_ranked(mocked_config):
    """Test journal parser keeps only ranked CORE entries."""
    source = CoreJournalSource()
    html = """
    Showing results 1 - 50 of 2
    <table>
      <tr class="evenrow">
        <td>Journal of Software Metrics</td>
        <td>CORE2020</td>
        <td>A*</td>
      </tr>
      <tr class="oddrow">
        <td>Non Ranked Journal</td>
        <td>CORE2020</td>
        <td>Not ranked</td>
      </tr>
    </table>
    """

    with patch(
        "aletheia_probe.updater.sources.core.input_normalizer.normalize"
    ) as norm:
        norm.return_value = Mock(normalized_name="journal of software metrics")
        entries = source._parse_entries(html)

    assert len(entries) == 1
    assert entries[0]["journal_name"] == "Journal of Software Metrics"
    assert entries[0]["metadata"]["core_rank"] == "A*"
    assert entries[0]["metadata"]["core_entity_type"] == "journal"


@pytest.mark.asyncio
async def test_fetch_data_paginates_and_deduplicates(mocked_config):
    """Test paginated fetch and deduplication by normalized name."""
    source = CoreConferenceSource()

    page_one = """
    Showing results 1 - 50 of 60
    <table>
      <tr class="evenrow">
        <td>Conference Alpha</td><td>CA</td><td>ICORE2026</td><td>A</td>
      </tr>
    </table>
    """
    page_two = """
    Showing results 51 - 60 of 60
    <table>
      <tr class="oddrow">
        <td>Conference Alpha</td><td>CA</td><td>ICORE2026</td><td>A</td>
      </tr>
      <tr class="evenrow">
        <td>Conference Beta</td><td>CB</td><td>ICORE2026</td><td>B</td>
      </tr>
    </table>
    """

    with (
        patch.object(
            source,
            "_fetch_page",
            new=AsyncMock(side_effect=[page_one, page_two]),
        ),
        patch("aletheia_probe.updater.sources.core.input_normalizer.normalize") as norm,
    ):
        norm.side_effect = [
            Mock(normalized_name="conference alpha"),
            Mock(normalized_name="conference alpha"),
            Mock(normalized_name="conference beta"),
        ]
        entries = await source.fetch_data()

    assert len(entries) == 2
    assert {entry["normalized_name"] for entry in entries} == {
        "conference alpha",
        "conference beta",
    }
