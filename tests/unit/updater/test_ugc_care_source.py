# SPDX-License-Identifier: MIT
"""Tests for UGC-CARE data sources."""

from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest

from aletheia_probe.enums import AssessmentType
from aletheia_probe.updater.sources.ugc_care import (
    UgcCareClonedGroup2Source,
    UgcCareClonedSource,
    UgcCareDelistedGroup2Source,
)


@pytest.fixture
def mocked_config():
    """Create mocked config manager for UGC-CARE URLs."""
    with patch("aletheia_probe.config.get_config_manager") as mock_config_manager:
        mock_config = Mock()
        mock_config.data_source_urls = Mock()
        mock_config.data_source_urls.ugc_care_cloned_url = (
            "https://ugccare.unipune.ac.in/Apps1/User/Web/CloneJournalsNew"
        )
        mock_config.data_source_urls.ugc_care_cloned_group2_url = (
            "https://ugccare.unipune.ac.in/Apps1/User/Web/CloneJournalsGroupIINew"
        )
        mock_config.data_source_urls.ugc_care_delisted_group2_url = (
            "https://ugccare.unipune.ac.in/Apps1/User/Web/ScopusDelisted"
        )
        mock_config_manager.return_value.load_config.return_value = mock_config
        yield


def test_cloned_source_basics(mocked_config):
    """Test basic source metadata for UGC cloned list."""
    source = UgcCareClonedSource()
    assert source.get_name() == "ugc_care_cloned"
    assert source.get_list_type() == AssessmentType.PREDATORY


def test_delisted_source_basics(mocked_config):
    """Test basic source metadata for UGC delisted list."""
    source = UgcCareDelistedGroup2Source()
    assert source.get_name() == "ugc_care_delisted_group2"
    assert source.get_list_type() == AssessmentType.PREDATORY


def test_cloned_group2_source_basics(mocked_config):
    """Test basic source metadata for UGC cloned Group II list."""
    source = UgcCareClonedGroup2Source()
    assert source.get_name() == "ugc_care_cloned_group2"
    assert source.get_list_type() == AssessmentType.PREDATORY


def test_should_update_no_last_update(mocked_config):
    """Test update decision when no prior update exists."""
    source = UgcCareDelistedGroup2Source()
    with patch("aletheia_probe.updater.sources.ugc_care.DataSourceManager") as mock_dsm:
        mock_cache = Mock()
        mock_cache.get_source_last_updated.return_value = None
        mock_dsm.return_value = mock_cache
        assert source.should_update() is True


def test_should_update_recent_update_skips(mocked_config):
    """Test update decision when source is fresh."""
    source = UgcCareClonedSource()
    with patch("aletheia_probe.updater.sources.ugc_care.DataSourceManager") as mock_dsm:
        mock_cache = Mock()
        mock_cache.get_source_last_updated.return_value = datetime.now() - timedelta(
            days=10
        )
        mock_dsm.return_value = mock_cache
        assert source.should_update() is False


def test_parse_delisted_group2_table(mocked_config):
    """Test delisted table parser extracts journal rows correctly."""
    source = UgcCareDelistedGroup2Source()
    html = """
    <table>
      <tr>
        <th>Sr. No.</th><th>Journal Title</th><th>Publisher</th>
        <th>ISSN</th><th>E-ISSN</th><th>Coverage</th>
      </tr>
      <tr>
        <td>1</td><td>Journal of Delisted Science</td><td>Delisted Pub</td>
        <td>1234-567X</td><td>2345-6789</td><td>2020-2024</td>
      </tr>
    </table>
    """

    entries = source._parse_entries(html)

    assert len(entries) == 1
    assert entries[0]["journal_name"] == "Journal of Delisted Science"
    assert entries[0]["publisher"] == "Delisted Pub"
    assert entries[0]["issn"] == "1234-567X"
    assert entries[0]["eissn"] == "2345-6789"
    assert entries[0]["metadata"]["ugc_status"] == "delisted_group_ii"


def test_parse_cloned_list_records(mocked_config):
    """Test cloned records parser extracts cloned title from each record."""
    source = UgcCareClonedSource()
    html = """
    <div>
      1 Title - Original Journal URL : http://orig.example
      Publisher : Original Publisher ISSN : 1111-2222
      Title - Cloned Journal URL : http://clone.example
      Publisher : Fake Publisher ISSN : 3333-4444
    </div>
    <div>
      2 Title - Another Original URL : http://orig2.example
      Publisher : Legit House ISSN : 5555-6666
      Title - Another Cloned URL : http://clone2.example
      Publisher : Bad House ISSN : 7777-8888
    </div>
    """

    entries = source._parse_entries(html)

    assert len(entries) == 2
    assert entries[0]["journal_name"] == "Cloned Journal"
    assert entries[0]["publisher"] == "Fake Publisher"
    assert entries[0]["metadata"]["ugc_status"] == "cloned_group_i"
    assert entries[0]["metadata"]["original_title"] == "Original Journal"
    assert entries[1]["journal_name"] == "Another Cloned"


def test_parse_cloned_group2_list_records(mocked_config):
    """Test Group II cloned parser uses Group II status metadata."""
    source = UgcCareClonedGroup2Source()
    html = """
    <div>
      1 Title - Original Journal URL : http://orig.example
      Publisher : Original Publisher ISSN : 1111-2222
      Title - Cloned Journal URL : http://clone.example
      Publisher : Fake Publisher ISSN : 3333-4444
    </div>
    """

    entries = source._parse_entries(html)

    assert len(entries) == 1
    assert entries[0]["journal_name"] == "Cloned Journal"
    assert entries[0]["metadata"]["ugc_status"] == "cloned_group_ii"
