# SPDX-License-Identifier: MIT
"""Unit tests for KscienPublishersBackend class."""

import pytest

import aletheia_probe.backends  # Import backends to register them
from aletheia_probe.backends.base import get_backend_registry
from aletheia_probe.backends.kscien_publishers import KscienPublishersBackend
from aletheia_probe.enums import AssessmentType


class TestKscienPublishersBackend:
    """Tests for KscienPublishersBackend functionality."""

    def test_initialization(self):
        """Test that KscienPublishersBackend initializes correctly."""
        backend = KscienPublishersBackend()

        # Test that initialization sets correct parameters
        assert backend._source_name == "kscien_publishers"
        assert backend.list_type == AssessmentType.PREDATORY
        assert backend.cache_ttl_hours == 24 * 7  # Weekly cache

    def test_get_name(self):
        """Test that get_name returns correct backend identifier."""
        backend = KscienPublishersBackend()
        assert backend.get_name() == "kscien_publishers"

    def test_backend_registration(self):
        """Test that backend is properly registered in backend registry."""
        registry = get_backend_registry()

        # Test that backend can be created from registry
        backend = registry.create_backend("kscien_publishers")
        assert isinstance(backend, KscienPublishersBackend)
        assert backend.get_name() == "kscien_publishers"

    def test_backend_available_in_registry(self):
        """Test that backend is available in the registry."""
        registry = get_backend_registry()

        # Test that backend is listed in registry
        backend_instance = registry.get_backend("kscien_publishers")
        assert backend_instance is not None
        assert isinstance(backend_instance, KscienPublishersBackend)
