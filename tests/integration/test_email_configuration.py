# SPDX-License-Identifier: MIT
"""Integration tests for email configuration functionality.

This test module validates the email configuration feature end-to-end,
testing actual backend creation with email parameters.
Tests for issue #47: Configuration of email does not work.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

import aletheia_probe.backends  # Import backends to register them
from aletheia_probe.backends.base import get_backend_registry
from aletheia_probe.config import ConfigManager
from aletheia_probe.dispatcher import QueryDispatcher
from aletheia_probe.models import ConfigBackend, QueryInput


class TestEmailConfigurationIntegration:
    """Integration tests for email configuration with real backend creation."""

    def test_backend_factory_creation_with_email(self):
        """Test that backend factories can create backends with email configuration.

        This tests the actual lambda factory functions that were broken in issue #47.
        """
        registry = get_backend_registry()
        test_email = "integration-test@example.com"
        test_cache_ttl = 6

        # Test crossref_analyzer backend creation with email
        crossref_backend = registry.create_backend(
            "crossref_analyzer", email=test_email, cache_ttl_hours=test_cache_ttl
        )
        assert crossref_backend.email == test_email
        assert crossref_backend.cache_ttl_hours == test_cache_ttl
        assert crossref_backend.get_name() == "crossref_analyzer"

        # Test openalex_analyzer backend creation with email
        openalex_backend = registry.create_backend(
            "openalex_analyzer", email=test_email, cache_ttl_hours=test_cache_ttl
        )
        assert openalex_backend.email == test_email
        assert openalex_backend.cache_ttl_hours == test_cache_ttl
        assert openalex_backend.get_name() == "openalex_analyzer"

        # Test cross_validator backend creation with email
        cross_validator_backend = registry.create_backend(
            "cross_validator", email=test_email, cache_ttl_hours=test_cache_ttl
        )
        assert cross_validator_backend.email == test_email
        assert cross_validator_backend.cache_ttl_hours == test_cache_ttl
        assert cross_validator_backend.get_name() == "cross_validator"

    def test_backend_factory_creation_with_defaults(self):
        """Test that backend factories work with default configuration."""
        registry = get_backend_registry()

        # Test creating backends without explicit parameters (should use defaults)
        crossref_backend = registry.create_backend("crossref_analyzer")
        assert crossref_backend.email == "noreply.aletheia-probe.org"
        assert crossref_backend.cache_ttl_hours == 24

        openalex_backend = registry.create_backend("openalex_analyzer")
        assert openalex_backend.email == "noreply.aletheia-probe.org"
        assert openalex_backend.cache_ttl_hours == 24

        cross_validator_backend = registry.create_backend("cross_validator")
        assert cross_validator_backend.email == "noreply.aletheia-probe.org"
        assert cross_validator_backend.cache_ttl_hours == 24

    def test_backend_factory_partial_override(self):
        """Test that backend factories work with partial parameter override."""
        registry = get_backend_registry()

        # Test with only email override
        backend1 = registry.create_backend(
            "crossref_analyzer", email="partial@test.com"
        )
        assert backend1.email == "partial@test.com"
        assert backend1.cache_ttl_hours == 24  # Should use default

        # Test with only cache_ttl_hours override
        backend2 = registry.create_backend("openalex_analyzer", cache_ttl_hours=48)
        assert backend2.email == "noreply.aletheia-probe.org"  # Should use default
        assert backend2.cache_ttl_hours == 48

    @pytest.mark.parametrize(
        "email",
        [
            "valid@example.com",
            "user.name@domain.co.uk",
            "test+tag@subdomain.example.org",
            "simple@test.io",
        ],
    )
    def test_valid_email_addresses(self, email):
        """Test that various valid email addresses work correctly."""
        registry = get_backend_registry()

        backend = registry.create_backend("crossref_analyzer", email=email)
        assert backend.email == email

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
        """Test that dispatcher correctly uses email from config file."""
        with patch(
            "aletheia_probe.dispatcher.get_config_manager"
        ) as mock_get_config_manager:
            config_manager = ConfigManager(Path(temp_config_file))
            config_manager.load_config()
            mock_get_config_manager.return_value = config_manager
            dispatcher = QueryDispatcher()

        # Test that get_enabled_backends creates backends with correct email
        with patch(
            "aletheia_probe.dispatcher.get_backend_registry"
        ) as mock_registry_func:
            mock_registry = Mock()
            mock_registry_func.return_value = mock_registry

            # Mock create_backend to track calls
            mock_backend = Mock()
            mock_backend.get_name.return_value = "crossref_analyzer"
            mock_registry.create_backend.return_value = mock_backend

            # Call dispatcher method that should trigger backend creation
            backends = dispatcher._get_enabled_backends()

            # Verify create_backend was called with email from config
            assert mock_registry.create_backend.call_count >= 1

            # Check that email was passed in the calls
            calls = mock_registry.create_backend.call_args_list
            email_calls = [call for call in calls if "email" in call[1]]
            assert len(email_calls) > 0

            # Verify the email value from config was used
            for call in email_calls:
                assert call[1]["email"] == "test-dispatcher@example.com"

    def test_dispatcher_backend_config_loading(self, temp_config_file):
        """Test that dispatcher correctly loads backend configurations with email."""
        config_manager = ConfigManager(Path(temp_config_file))
        config_manager._reset_cache()  # Clear any cached config
        config_manager.load_config()

        # Test crossref_analyzer config
        crossref_config = config_manager.get_backend_config("crossref_analyzer")
        assert crossref_config is not None
        assert crossref_config.email == "test-dispatcher@example.com"
        assert crossref_config.name == "crossref_analyzer"
        assert crossref_config.enabled is True

        # Test openalex_analyzer config
        openalex_config = config_manager.get_backend_config("openalex_analyzer")
        assert openalex_config is not None
        assert openalex_config.email == "test-dispatcher@example.com"
        assert openalex_config.name == "openalex_analyzer"
        assert openalex_config.enabled is True

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


class TestEmailValidation:
    """Tests for email address validation in configuration."""

    def test_config_backend_model_email_validation(self):
        """Test that ConfigBackend model accepts valid email addresses."""
        # Test valid emails
        valid_emails = [
            "test@example.com",
            "user.name@domain.co.uk",
            "test+tag@subdomain.example.org",
            "simple@test.io",
            None,  # None should be allowed
        ]

        for email in valid_emails:
            config = ConfigBackend(
                name="test_backend",
                enabled=True,
                weight=1.0,
                timeout=30,
                rate_limit=None,
                email=email,
                config={},
            )
            assert config.email == email

    def test_config_backend_model_invalid_email_validation(self):
        """Test that ConfigBackend model rejects obviously invalid email addresses."""
        # Note: Pydantic's EmailStr validation is quite permissive
        # These tests check for completely malformed addresses
        invalid_emails = [
            "",  # Empty string
            "@example.com",  # Missing local part
            "user@",  # Missing domain
            "invalid",  # No @ symbol
            "@",  # Just @ symbol
        ]

        for email in invalid_emails:
            with pytest.raises((ValueError, TypeError)):
                ConfigBackend(
                    name="test_backend",
                    enabled=True,
                    weight=1.0,
                    timeout=30,
                    rate_limit=None,
                    email=email,
                    config={},
                )

    def test_backend_email_parameter_types(self):
        """Test that backends handle different email parameter types correctly."""
        registry = get_backend_registry()

        # Test with string email
        backend1 = registry.create_backend("crossref_analyzer", email="string@test.com")
        assert backend1.email == "string@test.com"

        # Test that invalid types are accepted (no runtime type validation)
        # Note: Python type hints are not enforced at runtime
        backend2 = registry.create_backend("crossref_analyzer", email=123)
        assert backend2.email == 123  # Type hints don't prevent this
