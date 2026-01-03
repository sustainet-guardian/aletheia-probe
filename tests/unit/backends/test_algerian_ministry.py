# SPDX-License-Identifier: MIT
"""Tests for Algerian Ministry backend."""

from unittest.mock import patch

import pytest

from aletheia_probe.backends.algerian_ministry import AlgerianMinistryBackend
from aletheia_probe.enums import AssessmentType, EvidenceType
from aletheia_probe.models import BackendStatus, QueryInput


class TestAlgerianMinistryBackend:
    """Test cases for AlgerianMinistryBackend."""

    def test_get_name(self):
        """Test get_name returns 'algerian_ministry'."""
        backend = AlgerianMinistryBackend()
        assert backend.get_name() == "algerian_ministry"

    def test_get_evidence_type(self):
        """Test that Algerian Ministry backend returns correct evidence type."""
        backend = AlgerianMinistryBackend()
        assert backend.get_evidence_type() == EvidenceType.PREDATORY_LIST

    def test_backend_configuration(self):
        """Test backend is configured correctly."""
        backend = AlgerianMinistryBackend()
        assert backend._source_name == "algerian_ministry"
        assert backend.list_type == AssessmentType.PREDATORY
        assert backend.cache_ttl_hours == 48  # 48-hour cache

    def test_initialization(self):
        """Test backend initializes properly."""
        backend = AlgerianMinistryBackend()
        assert backend.journal_cache is not None
        assert backend.assessment_cache is not None

    @pytest.mark.asyncio
    async def test_query_journal_found(self):
        """Test querying a journal that exists in cache."""
        backend = AlgerianMinistryBackend()
        query_input = QueryInput(
            raw_input="Predatory Journal",
            normalized_name="predatory journal",
            identifiers={"issn": "1234-5678"},
        )

        mock_journal = {
            "journal_name": "Predatory Journal",
            "issn": "1234-5678",
            "source": "algerian_ministry",
        }

        with patch.object(
            backend.journal_cache, "search_journals", return_value=[mock_journal]
        ):
            result = await backend.query(query_input)

            assert result.backend_name == "algerian_ministry"
            assert result.status == BackendStatus.FOUND
            assert result.assessment == AssessmentType.PREDATORY
            assert result.confidence > 0.0
            assert result.cached  # CachedBackend results are marked as cached

    @pytest.mark.asyncio
    async def test_query_journal_not_found(self):
        """Test querying a journal that doesn't exist in cache."""
        backend = AlgerianMinistryBackend()
        query_input = QueryInput(
            raw_input="Unknown Journal",
            normalized_name="unknown journal",
            identifiers={"issn": "9999-9999"},
        )

        with patch.object(backend.journal_cache, "search_journals", return_value=[]):
            with patch.object(backend, "_search_exact_match", return_value=[]):
                result = await backend.query(query_input)

                assert result.backend_name == "algerian_ministry"
                assert result.status == BackendStatus.NOT_FOUND
                assert result.assessment is None
                assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_query_by_name_match(self):
        """Test querying a journal by normalized name when ISSN not available."""
        backend = AlgerianMinistryBackend()
        query_input = QueryInput(
            raw_input="Predatory Journal",
            normalized_name="predatory journal",
            identifiers={},
        )

        mock_journal = {
            "journal_name": "Predatory Journal",
            "source": "algerian_ministry",
        }

        with patch.object(backend.journal_cache, "search_journals", return_value=[]):
            with patch.object(
                backend, "_search_exact_match", return_value=[mock_journal]
            ):
                result = await backend.query(query_input)

                assert result.backend_name == "algerian_ministry"
                assert result.status == BackendStatus.FOUND
                assert result.assessment == AssessmentType.PREDATORY
