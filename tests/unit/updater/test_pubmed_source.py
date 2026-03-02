# SPDX-License-Identifier: MIT
"""Unit tests for the PubMed NLM data source."""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from aletheia_probe.enums import AssessmentType
from aletheia_probe.updater.sources.pubmed import (
    PubMedNLMSource,
    _build_journal_entry,
    _normalize_issn,
    _parse_nlm_records,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAMPLE_MEDLINE_TEXT = """\
--------------------------------------------------------
JrId: 1
JournalTitle: New England Journal of Medicine
MedAbbr: N Engl J Med
ISSN (Print): 0028-4793
ISSN (Online): 1533-4406
IsoAbbr: N Engl J Med
NlmId: 0255562
--------------------------------------------------------
JrId: 2
JournalTitle: Lancet
MedAbbr: Lancet
ISSN (Print): 0140-6736
ISSN (Online): 1474-547X
IsoAbbr: Lancet
NlmId: 2985213R
--------------------------------------------------------
"""

_SAMPLE_CATALOG_TEXT = """\
--------------------------------------------------------
JrId: 1
JournalTitle: New England Journal of Medicine
MedAbbr: N Engl J Med
ISSN (Print): 0028-4793
ISSN (Online): 1533-4406
IsoAbbr: N Engl J Med
NlmId: 0255562
--------------------------------------------------------
JrId: 99
JournalTitle: Journal of Rare Biology
MedAbbr: J Rare Biol
ISSN (Print): 1234-5678
ISSN (Online):
IsoAbbr: J Rare Biol
NlmId: 9999999
--------------------------------------------------------
"""


def _normalized_name_result(name: str) -> Mock:
    """Build mock normalizer result with normalized_venue contract."""
    return Mock(normalized_venue=SimpleNamespace(name=name))


# ---------------------------------------------------------------------------
# _parse_nlm_records
# ---------------------------------------------------------------------------


def test_parse_nlm_records_returns_all_records():
    """Parser extracts one dict per journal record from sample text."""
    records = _parse_nlm_records(_SAMPLE_MEDLINE_TEXT)
    assert len(records) == 2
    assert records[0]["JournalTitle"] == "New England Journal of Medicine"
    assert records[1]["JournalTitle"] == "Lancet"


def test_parse_nlm_records_captures_issns():
    """Parser captures both print and online ISSNs."""
    records = _parse_nlm_records(_SAMPLE_MEDLINE_TEXT)
    assert records[0]["ISSN (Print)"] == "0028-4793"
    assert records[0]["ISSN (Online)"] == "1533-4406"


def test_parse_nlm_records_empty_text_returns_empty_list():
    """Parsing empty text yields no records."""
    assert _parse_nlm_records("") == []


def test_parse_nlm_records_only_delimiters_returns_empty_list():
    """Text with only delimiter lines and no field data yields no records."""
    text = f"{_parse_nlm_records.__module__}\n"  # not a delimiter
    records = _parse_nlm_records(
        "--------------------------------------------------------\n"
        "--------------------------------------------------------\n"
    )
    assert records == []


# ---------------------------------------------------------------------------
# _normalize_issn
# ---------------------------------------------------------------------------


def test_normalize_issn_valid_with_hyphen():
    """Valid ISSN with hyphen is returned unchanged."""
    result = _normalize_issn("0028-4793", "NEJM")
    assert result == "0028-4793"


def test_normalize_issn_empty_returns_none():
    """Empty string returns None."""
    assert _normalize_issn("", "NEJM") is None


def test_normalize_issn_whitespace_only_returns_none():
    """Whitespace-only string returns None."""
    assert _normalize_issn("   ", "NEJM") is None


def test_normalize_issn_invalid_returns_none():
    """Invalid ISSN checksum returns None."""
    # 1234-5671: correct check digit would be 9, not 1
    assert _normalize_issn("1234-5671", "Bad Journal") is None


# ---------------------------------------------------------------------------
# _build_journal_entry
# ---------------------------------------------------------------------------


def test_build_journal_entry_medline_flag():
    """is_medline flag is stored in metadata."""
    record = {
        "JournalTitle": "New England Journal of Medicine",
        "ISSN (Print)": "0028-4793",
        "ISSN (Online)": "1533-4406",
        "NlmId": "0255562",
        "MedAbbr": "N Engl J Med",
    }

    with patch(
        "aletheia_probe.updater.sources.pubmed.input_normalizer.normalize"
    ) as mock_norm:
        mock_norm.return_value = _normalized_name_result(
            "new england journal of medicine"
        )
        entry = _build_journal_entry(record, is_medline=True)

    assert entry is not None
    assert entry["journal_name"] == "New England Journal of Medicine"
    assert entry["metadata"]["is_medline"] is True
    assert entry["metadata"]["nlm_id"] == "0255562"
    assert entry["metadata"]["med_abbr"] == "N Engl J Med"


def test_build_journal_entry_nlm_catalog_flag():
    """is_medline is False for NLM-only entries."""
    record = {"JournalTitle": "Some Catalog Journal", "NlmId": "1111111"}

    with patch(
        "aletheia_probe.updater.sources.pubmed.input_normalizer.normalize"
    ) as mock_norm:
        mock_norm.return_value = _normalized_name_result("some catalog journal")
        entry = _build_journal_entry(record, is_medline=False)

    assert entry is not None
    assert entry["metadata"]["is_medline"] is False


def test_build_journal_entry_missing_title_returns_none():
    """Record with empty JournalTitle yields None."""
    record = {"JournalTitle": "", "ISSN (Print)": "0028-4793"}
    assert _build_journal_entry(record, is_medline=True) is None


def test_build_journal_entry_normalization_failure_returns_none():
    """Normalization exception causes entry to be skipped."""
    record = {"JournalTitle": "Bad Journal"}

    with patch(
        "aletheia_probe.updater.sources.pubmed.input_normalizer.normalize",
        side_effect=ValueError("normalization failed"),
    ):
        entry = _build_journal_entry(record, is_medline=True)

    assert entry is None


# ---------------------------------------------------------------------------
# PubMedNLMSource metadata
# ---------------------------------------------------------------------------


@pytest.fixture
def mocked_config():
    """Provide a minimal config mock for PubMedNLMSource construction."""
    with patch("aletheia_probe.config.get_config_manager") as mock_mgr:
        mock_config = Mock()
        mock_config.data_source_urls.pubmed_nlm_medline_url = (
            "https://ftp.ncbi.nlm.nih.gov/pubmed/J_Medline.txt"
        )
        mock_config.data_source_urls.pubmed_nlm_catalog_url = (
            "https://ftp.ncbi.nlm.nih.gov/pubmed/J_Entrez.txt"
        )
        mock_mgr.return_value.load_config.return_value = mock_config
        yield


def test_source_name(mocked_config):
    """Source identifier is 'pubmed_nlm'."""
    source = PubMedNLMSource()
    assert source.get_name() == "pubmed_nlm"


def test_source_list_type(mocked_config):
    """List type is LEGITIMATE."""
    source = PubMedNLMSource()
    assert source.get_list_type() == AssessmentType.LEGITIMATE


def test_should_update_no_previous_update(mocked_config):
    """should_update returns True when no prior update exists."""
    source = PubMedNLMSource()
    with patch("aletheia_probe.updater.sources.pubmed.DataSourceManager") as mock_dsm:
        mock_dsm.return_value.get_source_last_updated.return_value = None
        assert source.should_update() is True


def test_should_update_recent_returns_false(mocked_config):
    """should_update returns False when data is fresh (< 30 days old)."""
    source = PubMedNLMSource()
    with patch("aletheia_probe.updater.sources.pubmed.DataSourceManager") as mock_dsm:
        mock_dsm.return_value.get_source_last_updated.return_value = (
            datetime.now() - timedelta(days=10)
        )
        assert source.should_update() is False


def test_should_update_stale_returns_true(mocked_config):
    """should_update returns True when data is older than 30 days."""
    source = PubMedNLMSource()
    with patch("aletheia_probe.updater.sources.pubmed.DataSourceManager") as mock_dsm:
        mock_dsm.return_value.get_source_last_updated.return_value = (
            datetime.now() - timedelta(days=31)
        )
        assert source.should_update() is True


# ---------------------------------------------------------------------------
# PubMedNLMSource.fetch_data
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_data_deduplicates_medline_from_catalog(mocked_config):
    """Journals in MEDLINE are not duplicated from NLM Catalog."""
    source = PubMedNLMSource()

    with (
        patch.object(
            source,
            "_fetch_file",
            new=AsyncMock(side_effect=[_SAMPLE_MEDLINE_TEXT, _SAMPLE_CATALOG_TEXT]),
        ),
        patch(
            "aletheia_probe.updater.sources.pubmed.input_normalizer.normalize"
        ) as mock_norm,
    ):
        mock_norm.side_effect = [
            _normalized_name_result("new england journal of medicine"),
            _normalized_name_result("lancet"),
            # Catalog fetch: NEJM again (should be deduplicated by NlmId)
            _normalized_name_result("new england journal of medicine"),
            _normalized_name_result("journal of rare biology"),
        ]
        entries = await source.fetch_data()

    # NEJM (MEDLINE), Lancet (MEDLINE), Journal of Rare Biology (catalog only)
    assert len(entries) == 3
    names = {e["journal_name"] for e in entries}
    assert "New England Journal of Medicine" in names
    assert "Lancet" in names
    assert "Journal of Rare Biology" in names


@pytest.mark.asyncio
async def test_fetch_data_medline_entries_tagged(mocked_config):
    """MEDLINE entries have is_medline=True in metadata."""
    source = PubMedNLMSource()

    with (
        patch.object(
            source,
            "_fetch_file",
            new=AsyncMock(side_effect=[_SAMPLE_MEDLINE_TEXT, ""]),
        ),
        patch(
            "aletheia_probe.updater.sources.pubmed.input_normalizer.normalize"
        ) as mock_norm,
    ):
        mock_norm.side_effect = [
            _normalized_name_result("new england journal of medicine"),
            _normalized_name_result("lancet"),
        ]
        entries = await source.fetch_data()

    for entry in entries:
        assert entry["metadata"]["is_medline"] is True


@pytest.mark.asyncio
async def test_fetch_data_empty_files_return_empty_list(mocked_config):
    """Both files returning empty text yields no entries."""
    source = PubMedNLMSource()

    with patch.object(
        source,
        "_fetch_file",
        new=AsyncMock(return_value=""),
    ):
        entries = await source.fetch_data()

    assert entries == []
