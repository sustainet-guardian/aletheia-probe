# SPDX-License-Identifier: MIT
"""Unit tests for CORE conference and journal backends."""

from unittest.mock import patch

from aletheia_probe.backends.core_conferences import CoreConferencesBackend
from aletheia_probe.backends.core_journals import CoreJournalsBackend
from aletheia_probe.enums import AssessmentType, EvidenceType


def test_core_conferences_backend_initialization():
    """Test CORE conference backend initialization and metadata."""
    backend = CoreConferencesBackend()
    assert backend.get_name() == "core_conferences"
    assert backend.source_name == "core_conferences"
    assert backend.list_type == AssessmentType.LEGITIMATE
    assert backend.cache_ttl_hours == 24 * 30


def test_core_journals_backend_initialization():
    """Test CORE journal backend initialization and metadata."""
    backend = CoreJournalsBackend()
    assert backend.get_name() == "core_journals"
    assert backend.source_name == "core_journals"
    assert backend.list_type == AssessmentType.LEGITIMATE
    assert backend.cache_ttl_hours == 24 * 30


def test_core_backends_evidence_type():
    """Test both CORE backends expose legitimate list evidence type."""
    assert CoreConferencesBackend().get_evidence_type() == EvidenceType.LEGITIMATE_LIST
    assert CoreJournalsBackend().get_evidence_type() == EvidenceType.LEGITIMATE_LIST


def test_core_backends_registration():
    """Test CORE backend factory registration."""
    from aletheia_probe.backends.base import get_backend_registry

    registry = get_backend_registry()
    conference_backend = registry.create_backend("core_conferences")
    journal_backend = registry.create_backend("core_journals")

    assert isinstance(conference_backend, CoreConferencesBackend)
    assert isinstance(journal_backend, CoreJournalsBackend)


def test_core_conferences_backend_get_data_source():
    """Test conference source creation and caching behavior."""
    backend = CoreConferencesBackend()

    with patch(
        "aletheia_probe.updater.sources.core.CoreConferenceSource"
    ) as mock_source:
        data_source = backend.get_data_source()
        assert data_source == mock_source.return_value
        mock_source.assert_called_once_with()

        second = backend.get_data_source()
        assert second == data_source
        mock_source.assert_called_once()


def test_core_journals_backend_get_data_source():
    """Test journal source creation and caching behavior."""
    backend = CoreJournalsBackend()

    with patch("aletheia_probe.updater.sources.core.CoreJournalSource") as mock_source:
        data_source = backend.get_data_source()
        assert data_source == mock_source.return_value
        mock_source.assert_called_once_with()

        second = backend.get_data_source()
        assert second == data_source
        mock_source.assert_called_once()
