# SPDX-License-Identifier: MIT
"""Unit tests for the KscienHijackedJournalsBackend."""

import pytest

from aletheia_probe.backends.kscien_hijacked_journals import (
    KscienHijackedJournalsBackend,
)
from aletheia_probe.enums import AssessmentType, EvidenceType


def test_kscien_hijacked_journals_backend_initialization():
    """Test backend initialization and metadata."""
    backend = KscienHijackedJournalsBackend()
    assert backend.get_name() == "kscien_hijacked_journals"
    assert backend.list_type == AssessmentType.HIJACKED
    assert backend.source_name == "kscien_hijacked_journals"


def test_kscien_hijacked_journals_backend_evidence_type():
    """Test that the backend returns the correct evidence type."""
    backend = KscienHijackedJournalsBackend()
    assert backend.get_evidence_type() == EvidenceType.PREDATORY_LIST


@pytest.mark.asyncio
async def test_kscien_hijacked_journals_backend_query_interface():
    """Test that the query method exists (it's inherited)."""
    backend = KscienHijackedJournalsBackend()
    assert hasattr(backend, "query")
