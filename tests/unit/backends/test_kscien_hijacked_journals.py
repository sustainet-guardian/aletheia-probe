# SPDX-License-Identifier: MIT
"""Unit tests for the KscienHijackedJournalsBackend."""

from unittest.mock import patch

import pytest

from aletheia_probe.backends.kscien_hijacked_journals import (
    KscienHijackedJournalsBackend,
)
from aletheia_probe.enums import AssessmentType, EvidenceType
from aletheia_probe.models import BackendStatus, QueryInput


def test_kscien_hijacked_journals_backend_initialization():
    """Test backend initialization and metadata."""
    backend = KscienHijackedJournalsBackend()
    assert backend.get_name() == "kscien_hijacked_journals"
    assert backend.list_type == AssessmentType.HIJACKED
    assert backend.source_name == "kscien_hijacked_journals"
    assert backend.cache_ttl_hours == 24 * 7


def test_kscien_hijacked_journals_backend_evidence_type():
    """Test that the backend returns the correct evidence type."""
    backend = KscienHijackedJournalsBackend()
    assert backend.get_evidence_type() == EvidenceType.PREDATORY_LIST


def test_kscien_hijacked_journals_backend_registration():
    """Test that the backend is properly registered."""
    from aletheia_probe.backends.base import get_backend_registry

    registry = get_backend_registry()
    backend = registry.create_backend("kscien_hijacked_journals")
    assert isinstance(backend, KscienHijackedJournalsBackend)


@pytest.mark.asyncio
async def test_kscien_hijacked_journals_backend_query_found():
    """Test querying a journal that exists in cache."""
    backend = KscienHijackedJournalsBackend()
    query_input = QueryInput(
        raw_input="Hijacked Journal",
        normalized_name="hijacked journal",
        identifiers={"issn": "1234-5678"},
    )

    mock_journal = {
        "journal_name": "Hijacked Journal",
        "issn": "1234-5678",
        "source": "kscien_hijacked_journals",
    }

    with patch.object(
        backend.journal_cache, "search_journals", return_value=[mock_journal]
    ):
        result = await backend.query(query_input)

        assert result.backend_name == "kscien_hijacked_journals"
        assert result.status == BackendStatus.FOUND
        assert result.assessment == AssessmentType.HIJACKED
        assert result.confidence > 0.0
        assert result.cached


@pytest.mark.asyncio
async def test_kscien_hijacked_journals_backend_query_not_found():
    """Test querying a journal that doesn't exist in cache."""
    backend = KscienHijackedJournalsBackend()
    query_input = QueryInput(
        raw_input="Unknown Journal",
        normalized_name="unknown journal",
        identifiers={"issn": "9999-9999"},
    )

    with patch.object(backend.journal_cache, "search_journals", return_value=[]):
        with patch.object(backend, "_search_exact_match", return_value=[]):
            result = await backend.query(query_input)

            assert result.backend_name == "kscien_hijacked_journals"
            assert result.status == BackendStatus.NOT_FOUND
            assert result.assessment is None
            assert result.confidence == 0.0
