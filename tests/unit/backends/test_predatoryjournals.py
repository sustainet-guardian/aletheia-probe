# SPDX-License-Identifier: MIT
"""Tests for the PredatoryJournals backend."""

from unittest.mock import patch

import pytest

from aletheia_probe.backends.predatoryjournals import PredatoryJournalsBackend
from aletheia_probe.enums import AssessmentType
from aletheia_probe.models import BackendStatus, QueryInput


class TestPredatoryJournalsBackend:
    """Test cases for PredatoryJournalsBackend."""

    def test_get_name(self):
        """Test get_name returns 'predatoryjournals'."""
        backend = PredatoryJournalsBackend()
        assert backend.get_name() == "predatoryjournals"

    def test_get_description(self):
        """Test get_description returns expected string."""
        backend = PredatoryJournalsBackend()
        description = backend.get_description()
        assert "predatoryjournals.org" in description
        assert "predatory journals" in description.lower()

    def test_backend_configuration(self):
        """Test backend is configured correctly."""
        backend = PredatoryJournalsBackend()
        assert backend.source_name == "predatoryjournals"
        assert backend.list_type == AssessmentType.PREDATORY
        assert backend.cache_ttl_hours == 24 * 30  # Monthly cache

    @pytest.mark.asyncio
    async def test_query_journal_found(self):
        """Test querying a journal that exists in cache."""
        backend = PredatoryJournalsBackend()
        query_input = QueryInput(
            raw_input="Predatory Journal",
            normalized_name="predatory journal",
            identifiers={"issn": "1234-5678"},
        )

        mock_results = [
            {
                "journal_name": "Predatory Journal",
                "normalized_name": "predatory journal",
                "issn": "1234-5678",
                "publisher": "Predatory Publisher",
                "metadata": {"source_url": "http://example.com"},
            }
        ]

        with (
            patch.object(
                backend.journal_cache, "search_journals", return_value=mock_results
            ),
            patch.object(
                backend.journal_cache,
                "search_journals_by_name",
                return_value=mock_results,
            ),
        ):
            result = await backend.query(query_input)

            assert result.status == BackendStatus.FOUND
            assert result.assessment == AssessmentType.PREDATORY
            assert result.confidence > 0.9  # ISSN match gives high confidence
            assert result.data["source_data"]["journal_name"] == "Predatory Journal"

    @pytest.mark.asyncio
    async def test_query_journal_not_found(self):
        """Test querying a journal that doesn't exist in cache."""
        backend = PredatoryJournalsBackend()
        query_input = QueryInput(
            raw_input="Good Journal", normalized_name="good journal"
        )

        with (
            patch.object(backend.journal_cache, "search_journals", return_value=[]),
            patch.object(
                backend.journal_cache, "search_journals_by_name", return_value=[]
            ),
        ):
            result = await backend.query(query_input)

            assert result.status == BackendStatus.NOT_FOUND
            assert result.assessment is None
            assert result.confidence == 0.0

    def test_backend_inheritance(self):
        """Test that the backend inherits from CachedBackend."""
        from aletheia_probe.backends.base import CachedBackend

        backend = PredatoryJournalsBackend()
        assert isinstance(backend, CachedBackend)

    def test_backend_registration(self):
        """Test that the backend is properly registered."""
        from aletheia_probe.backends.base import get_backend_registry

        # Ensure registry is initialized
        registry = get_backend_registry()

        # Check if backend is in the registry
        assert "predatoryjournals" in registry.get_backend_names()

        # Check if factory creates the correct instance
        backend = registry.create_backend("predatoryjournals")
        assert isinstance(backend, PredatoryJournalsBackend)
