# SPDX-License-Identifier: MIT
"""Unit tests for DBLP venues backend."""

from unittest.mock import patch

from aletheia_probe.backends.dblp_venues import DblpVenuesBackend
from aletheia_probe.enums import AssessmentType, EvidenceType


def test_dblp_venues_backend_initialization():
    """Test backend initialization and metadata."""
    backend = DblpVenuesBackend()
    assert backend.get_name() == "dblp_venues"
    assert backend.source_name == "dblp_venues"
    assert backend.list_type == AssessmentType.LEGITIMATE
    assert backend.cache_ttl_hours == 24 * 30


def test_dblp_venues_backend_evidence_type():
    """Test that backend exposes legitimate list evidence type."""
    backend = DblpVenuesBackend()
    assert backend.get_evidence_type() == EvidenceType.LEGITIMATE_LIST


def test_dblp_venues_backend_registration():
    """Test backend factory registration."""
    from aletheia_probe.backends.base import get_backend_registry

    registry = get_backend_registry()
    backend = registry.create_backend("dblp_venues")
    assert isinstance(backend, DblpVenuesBackend)


def test_dblp_venues_backend_get_data_source():
    """Test source creation and caching behavior."""
    backend = DblpVenuesBackend()

    with patch("aletheia_probe.updater.sources.dblp.DblpVenueSource") as mock_source:
        data_source = backend.get_data_source()
        assert data_source == mock_source.return_value
        mock_source.assert_called_once_with()

        second = backend.get_data_source()
        assert second == data_source
        mock_source.assert_called_once()
