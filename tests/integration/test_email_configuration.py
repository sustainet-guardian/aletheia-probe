# SPDX-License-Identifier: MIT
"""Integration tests for email configuration functionality.

INTEGRATION TEST FILE: This file contains integration tests that verify
component interactions and end-to-end workflows. These are NOT predictable
unit tests - they may make real external API calls and use fuzzy assertions.

See README.md in this directory for details on integration test characteristics
and how to interpret test failures.

This test module validates the email configuration feature end-to-end,
testing actual backend creation with email parameters.
Tests for issue #47: Configuration of email does not work.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

import aletheia_probe.backends  # Import backends to register them
from aletheia_probe.backends.base import get_backend_registry
from aletheia_probe.config import ConfigManager
from aletheia_probe.dispatcher import QueryDispatcher
from aletheia_probe.models import QueryInput


class TestEmailConfigurationIntegration:
    """Integration tests for email configuration with real backend creation."""

    def test_cross_validator_email_propagation(self):
        """Test that CrossValidatorBackend properly propagates email to sub-backends."""
        registry = get_backend_registry()
        test_email = "propagation-test@example.com"

        backend = registry.create_backend("cross_validator", email=test_email)

        # Verify email is stored on the main backend
        assert backend.email == test_email

        # Verify email is propagated to sub-backends
        assert backend.openalex_backend.email == test_email
        assert backend.crossref_backend.email == test_email


class TestDispatcherEmailConfiguration:
    """Integration tests for email configuration through the dispatcher."""

    @pytest.fixture
    def temp_config_file(self):
        """Create a temporary configuration file with email settings."""
        config_content = """
backends:
  crossref_analyzer:
    name: crossref_analyzer
    enabled: true
    weight: 1.0
    timeout: 30
    email: "test-dispatcher@example.com"
    config: {}
  openalex_analyzer:
    name: openalex_analyzer
    enabled: true
    weight: 1.0
    timeout: 30
    email: "test-dispatcher@example.com"
    config: {}
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(config_content)
            f.flush()  # Ensure content is written to disk
            temp_name = f.name
        yield temp_name
        os.unlink(temp_name)

    def test_dispatcher_with_email_config_file(self, temp_config_file):
        """Test that dispatcher correctly uses email from config file.

        This integration test uses real backends to verify email configuration
        flows correctly through the dispatcher → backend registry → backend chain.
        """
        # Only mock get_config_manager to inject our test config
        with patch(
            "aletheia_probe.dispatcher.get_config_manager"
        ) as mock_get_config_manager:
            config_manager = ConfigManager(Path(temp_config_file))
            config_manager.load_config()
            mock_get_config_manager.return_value = config_manager
            dispatcher = QueryDispatcher()

            # Use REAL backend registry and REAL backends (not mocked)
            backends = dispatcher._get_enabled_backends()

            # Verify real backends were created with correct email
            assert len(backends) >= 1, "Should create at least one backend"

            # Check that backends have the email from config
            for backend in backends:
                backend_name = backend.get_name()
                if backend_name in ["crossref_analyzer", "openalex_analyzer"]:
                    assert backend.email == "test-dispatcher@example.com", (
                        f"{backend_name} should have email from config"
                    )

    @pytest.mark.asyncio
    async def test_end_to_end_assessment_with_email(self, temp_config_file):
        """Test complete assessment flow with email configuration.

        This is an end-to-end test that verifies the email configuration
        works through the entire assessment pipeline.
        """
        # Mock external API calls to avoid actual network requests
        with (
            patch(
                "aletheia_probe.backends.crossref_analyzer.CrossrefAnalyzerBackend.query"
            ) as mock_crossref,
            patch(
                "aletheia_probe.backends.openalex_analyzer.OpenAlexAnalyzerBackend.query"
            ) as mock_openalex,
            patch(
                "aletheia_probe.dispatcher.get_config_manager"
            ) as mock_get_config_manager,
        ):
            # Configure mocks to return success responses
            mock_crossref.return_value = {
                "assessment": "predatory",
                "confidence": 0.8,
                "reasoning": "Test crossref assessment",
            }
            mock_openalex.return_value = {
                "assessment": "predatory",
                "confidence": 0.7,
                "reasoning": "Test openalex assessment",
            }

            # Setup dispatcher with email configuration
            config_manager = ConfigManager(Path(temp_config_file))
            config_manager.load_config()
            mock_get_config_manager.return_value = config_manager
            dispatcher = QueryDispatcher()

            # Create test query
            query = QueryInput(
                raw_input="Test Journal",
                normalized_name="Test Journal",
                identifiers={"issn": "1234-5678"},
            )

            # Run assessment - this should create backends with email configuration
            result = await dispatcher.assess_journal(query)

            # Verify assessment completed successfully
            assert result is not None
            assert len(result.backend_results) > 0

            # The key test: no "unexpected keyword argument 'email'" error should occur
            # If the lambda syntax was still broken, this test would fail with that error
