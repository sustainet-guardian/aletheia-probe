# SPDX-License-Identifier: MIT
"""Unit tests for the PubMed NLM backend."""

from unittest.mock import patch

import pytest

from aletheia_probe.backends.pubmed import (
    _CONFIDENCE_MEDLINE,
    _CONFIDENCE_NLM_CATALOG,
    PubMedBackend,
)
from aletheia_probe.enums import AssessmentType, EvidenceType
from aletheia_probe.models import (
    BackendStatus,
    NormalizedVenueInput,
    QueryInput,
    VenueType,
)


def _make_query(name: str, issn: str | None = None) -> QueryInput:
    """Build a minimal QueryInput for testing."""
    return QueryInput(
        raw_input=name,
        normalized_venue=NormalizedVenueInput(
            original_text=name,
            name=name.lower(),
            acronym=None,
            issn=issn,
            eissn=None,
            venue_type=VenueType.JOURNAL,
            aliases=[],
            input_identifiers={"issn": issn} if issn else {},
        ),
    )


class TestPubMedBackendInitialization:
    """Tests for PubMedBackend setup and metadata."""

    def test_backend_name(self):
        """Test get_name returns 'pubmed_nlm'."""
        backend = PubMedBackend()
        assert backend.get_name() == "pubmed_nlm"

    def test_source_name(self):
        """Test source_name attribute matches backend name."""
        backend = PubMedBackend()
        assert backend.source_name == "pubmed_nlm"

    def test_list_type(self):
        """Test list_type is LEGITIMATE."""
        backend = PubMedBackend()
        assert backend.list_type == AssessmentType.LEGITIMATE

    def test_evidence_type(self):
        """Test evidence type is LEGITIMATE_LIST."""
        backend = PubMedBackend()
        assert backend.get_evidence_type() == EvidenceType.LEGITIMATE_LIST

    def test_cache_ttl(self):
        """Test cache TTL is 30 days in hours."""
        backend = PubMedBackend()
        assert backend.cache_ttl_hours == 24 * 30

    def test_registry_registration(self):
        """Test backend is registered under 'pubmed_nlm'."""
        from aletheia_probe.backends.base import get_backend_registry

        registry = get_backend_registry()
        backend = registry.create_backend("pubmed_nlm")
        assert isinstance(backend, PubMedBackend)

    def test_data_source_factory(self):
        """Test data source is created and cached on first access."""
        from aletheia_probe.updater.sources.pubmed import PubMedNLMSource

        backend = PubMedBackend()
        with patch("aletheia_probe.backends.pubmed.PubMedNLMSource") as mock_source_cls:
            source = backend.get_data_source()
            assert source == mock_source_cls.return_value
            mock_source_cls.assert_called_once_with()

            second = backend.get_data_source()
            assert second is source
            mock_source_cls.assert_called_once()


class TestPubMedBackendConfidence:
    """Tests for per-entry confidence scoring."""

    def test_medline_entry_confidence(self):
        """MEDLINE-tagged entries return the higher confidence score."""
        backend = PubMedBackend()
        query = _make_query("New England Journal of Medicine", issn="0028-4793")
        raw_data = {
            "journal_name": "New England Journal of Medicine",
            "metadata": {"is_medline": True},
        }
        confidence = backend._calculate_match_confidence(query, raw_data)
        assert confidence == _CONFIDENCE_MEDLINE

    def test_nlm_catalog_only_entry_confidence(self):
        """NLM-Catalog-only entries return the lower confidence score."""
        backend = PubMedBackend()
        query = _make_query("Some NLM Journal")
        raw_data = {
            "journal_name": "Some NLM Journal",
            "metadata": {"is_medline": False},
        }
        confidence = backend._calculate_match_confidence(query, raw_data)
        assert confidence == _CONFIDENCE_NLM_CATALOG

    def test_missing_metadata_defaults_to_nlm_catalog_confidence(self):
        """Entries without metadata fall back to NLM Catalog confidence."""
        backend = PubMedBackend()
        query = _make_query("Some Journal")
        raw_data = {"journal_name": "Some Journal"}
        confidence = backend._calculate_match_confidence(query, raw_data)
        assert confidence == _CONFIDENCE_NLM_CATALOG

    def test_medline_confidence_higher_than_catalog(self):
        """MEDLINE confidence must be strictly greater than NLM Catalog confidence."""
        assert _CONFIDENCE_MEDLINE > _CONFIDENCE_NLM_CATALOG


class TestPubMedBackendQuery:
    """Tests for the query method via mocked cache."""

    @pytest.mark.asyncio
    async def test_query_found_medline(self):
        """Journal found in MEDLINE cache returns FOUND with higher confidence."""
        backend = PubMedBackend()
        query = _make_query("New England Journal of Medicine", issn="0028-4793")

        mock_journal = {
            "journal_name": "New England Journal of Medicine",
            "issn": "0028-4793",
            "source": "pubmed_nlm",
            "metadata": {"is_medline": True},
        }

        with patch.object(
            backend.journal_cache, "search_journals", return_value=[mock_journal]
        ):
            result = await backend.query(query)

        assert result.backend_name == "pubmed_nlm"
        assert result.status == BackendStatus.FOUND
        assert result.assessment == AssessmentType.LEGITIMATE
        assert result.confidence == _CONFIDENCE_MEDLINE
        assert result.cached is True

    @pytest.mark.asyncio
    async def test_query_found_nlm_catalog(self):
        """Journal found only in NLM Catalog returns FOUND with lower confidence."""
        backend = PubMedBackend()
        query = _make_query("Acta Crystallographica", issn="0108-7673")

        mock_journal = {
            "journal_name": "Acta Crystallographica",
            "issn": "0108-7673",
            "source": "pubmed_nlm",
            "metadata": {"is_medline": False},
        }

        with patch.object(
            backend.journal_cache, "search_journals", return_value=[mock_journal]
        ):
            result = await backend.query(query)

        assert result.backend_name == "pubmed_nlm"
        assert result.status == BackendStatus.FOUND
        assert result.assessment == AssessmentType.LEGITIMATE
        assert result.confidence == _CONFIDENCE_NLM_CATALOG

    @pytest.mark.asyncio
    async def test_query_not_found(self):
        """Non-biomedical journal returns NOT_FOUND with no negative signal."""
        backend = PubMedBackend()
        query = _make_query("Journal of Computer Science", issn="1549-3636")

        with patch.object(backend.journal_cache, "search_journals", return_value=[]):
            with patch.object(backend, "_search_exact_match", return_value=[]):
                result = await backend.query(query)

        assert result.backend_name == "pubmed_nlm"
        assert result.status == BackendStatus.NOT_FOUND
        assert result.assessment is None
        assert result.confidence == 0.0
