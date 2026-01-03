# SPDX-License-Identifier: MIT
"""Unit tests for the KscienPredatoryConferencesBackend."""

from unittest.mock import patch

import pytest

from aletheia_probe.backends.kscien_predatory_conferences import (
    KscienPredatoryConferencesBackend,
)
from aletheia_probe.enums import AssessmentType, EvidenceType
from aletheia_probe.models import BackendStatus, QueryInput


def test_kscien_predatory_conferences_backend_initialization():
    """Test backend initialization and metadata."""
    backend = KscienPredatoryConferencesBackend()
    assert backend.get_name() == "kscien_predatory_conferences"
    assert backend.list_type == AssessmentType.PREDATORY
    assert backend.source_name == "kscien_predatory_conferences"
    assert backend.cache_ttl_hours == 24 * 7


def test_kscien_predatory_conferences_backend_evidence_type():
    """Test that the backend returns the correct evidence type."""
    backend = KscienPredatoryConferencesBackend()
    assert backend.get_evidence_type() == EvidenceType.PREDATORY_LIST


def test_kscien_predatory_conferences_backend_registration():
    """Test that the backend is properly registered."""
    from aletheia_probe.backends.base import get_backend_registry

    registry = get_backend_registry()
    backend = registry.create_backend("kscien_predatory_conferences")
    assert isinstance(backend, KscienPredatoryConferencesBackend)


@pytest.mark.asyncio
async def test_kscien_predatory_conferences_backend_query_found():
    """Test querying a conference that exists in cache."""
    backend = KscienPredatoryConferencesBackend()
    query_input = QueryInput(
        raw_input="Predatory Conference",
        normalized_name="predatory conference",
        identifiers={"issn": "1234-5678"},
    )

    mock_journal = {
        "journal_name": "Predatory Conference",
        "issn": "1234-5678",
        "source": "kscien_predatory_conferences",
    }

    with patch.object(
        backend.journal_cache, "search_journals", return_value=[mock_journal]
    ):
        result = await backend.query(query_input)

        assert result.backend_name == "kscien_predatory_conferences"
        assert result.status == BackendStatus.FOUND
        assert result.assessment == AssessmentType.PREDATORY
        assert result.confidence > 0.0
        assert result.cached


@pytest.mark.asyncio
async def test_kscien_predatory_conferences_backend_query_not_found():
    """Test querying a conference that doesn't exist in cache."""
    backend = KscienPredatoryConferencesBackend()
    query_input = QueryInput(
        raw_input="Unknown Conference",
        normalized_name="unknown conference",
        identifiers={"issn": "9999-9999"},
    )

    with patch.object(backend.journal_cache, "search_journals", return_value=[]):
        with patch.object(backend, "_search_exact_match", return_value=[]):
            result = await backend.query(query_input)

            assert result.backend_name == "kscien_predatory_conferences"
            assert result.status == BackendStatus.NOT_FOUND
            assert result.assessment is None
            assert result.confidence == 0.0
