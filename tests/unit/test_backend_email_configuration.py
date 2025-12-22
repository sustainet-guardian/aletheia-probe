# SPDX-License-Identifier: MIT
"""Unit tests for backend email configuration.

This test module validates that backends can be properly configured with email
parameters. This functionality was added to fix issue #47 where email configuration
was failing with a lambda syntax error.

Historical context (issue #47):
"Configuration of email does not work" - Error: <lambda>() got an unexpected
keyword argument 'email'
"""

import tempfile
from pathlib import Path

import pytest

import aletheia_probe.backends  # Import backends to register them
from aletheia_probe.backends.base import get_backend_registry
from aletheia_probe.config import ConfigManager


class TestBackendEmailConfiguration:
    """Tests for backend email configuration functionality.

    These tests verify that backends can be properly created and configured
    with email parameters. Originally created to validate the fix for issue #47.
    """

    def test_backend_registry_create_backend_with_email_crossref(self):
        """Test that crossref_analyzer backend can be created with email parameter.

        This was the exact failing scenario from issue #47.
        """
        registry = get_backend_registry()

        # This should NOT raise "got an unexpected keyword argument 'email'"
        backend = registry.create_backend(
            "crossref_analyzer", email="issue47-test@example.com", cache_ttl_hours=12
        )

        assert backend.email == "issue47-test@example.com"
        assert backend.cache_ttl_hours == 12
        assert backend.get_name() == "crossref_analyzer"

    def test_backend_registry_create_backend_with_email_openalex(self):
        """Test that openalex_analyzer backend can be created with email parameter."""
        registry = get_backend_registry()

        backend = registry.create_backend(
            "openalex_analyzer", email="issue47-openalex@example.com", cache_ttl_hours=8
        )

        assert backend.email == "issue47-openalex@example.com"
        assert backend.cache_ttl_hours == 8
        assert backend.get_name() == "openalex_analyzer"

    def test_backend_registry_create_backend_with_email_cross_validator(self):
        """Test that cross_validator backend can be created with email parameter."""
        registry = get_backend_registry()

        backend = registry.create_backend(
            "cross_validator", email="issue47-cv@example.com", cache_ttl_hours=16
        )

        assert backend.email == "issue47-cv@example.com"
        assert backend.cache_ttl_hours == 16
        assert backend.get_name() == "cross_validator"

        # Also test that email is propagated to sub-backends
        assert backend.openalex_backend.email == "issue47-cv@example.com"
        assert backend.crossref_backend.email == "issue47-cv@example.com"

    def test_lambda_syntax_fix_verification(self):
        """Test that verifies the lambda syntax is fixed in all three backends.

        The original issue #47 was invalid Python lambda syntax in the factory
        registrations. This test verifies that the lambda functions can be called
        with keyword arguments.
        """
        registry = get_backend_registry()

        # Get the factories directly (this is internal testing)
        crossref_factory = registry._factories.get("crossref_analyzer")
        openalex_factory = registry._factories.get("openalex_analyzer")
        cross_validator_factory = registry._factories.get("cross_validator")

        assert crossref_factory is not None
        assert openalex_factory is not None
        assert cross_validator_factory is not None

        # Test calling factories with keyword arguments (this would fail with broken lambda syntax)
        crossref_backend = crossref_factory(
            email="lambda-test@example.com", cache_ttl_hours=5
        )
        openalex_backend = openalex_factory(
            email="lambda-test@example.com", cache_ttl_hours=5
        )
        cv_backend = cross_validator_factory(
            email="lambda-test@example.com", cache_ttl_hours=5
        )

        assert crossref_backend.email == "lambda-test@example.com"
        assert openalex_backend.email == "lambda-test@example.com"
        assert cv_backend.email == "lambda-test@example.com"

    def test_config_file_email_configuration(self):
        """Test that email configuration can be loaded from a config file.

        This tests the end-to-end config loading that would be used in real scenarios.
        """
        config_content = """
backends:
  crossref_analyzer:
    name: crossref_analyzer
    enabled: true
    weight: 1.0
    timeout: 30
    email: config-file-test@example.com
    config: {}
"""

        # Create temporary config file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(config_content)
            config_file = Path(f.name)

        try:
            # Load config
            config_manager = ConfigManager(config_file)
            config_manager.load_config()

            # Test that backend config has the email
            backend_config = config_manager.get_backend_config("crossref_analyzer")
            assert backend_config is not None
            assert backend_config.email == "config-file-test@example.com"
            assert backend_config.name == "crossref_analyzer"
            assert backend_config.enabled is True
        finally:
            config_file.unlink()  # Clean up

    def test_original_error_scenario_simulation(self):
        """Simulate the original error scenario that would have occurred.

        Before the fix for issue #47, this would result in:
        "Error during assessment: <lambda>() got an unexpected keyword argument 'email'"
        """
        registry = get_backend_registry()

        # Simulate what the dispatcher would do when email is configured
        config_params = {"email": "original-error-test@example.com"}

        # This should work now (would fail before the fix)
        backend = registry.create_backend("crossref_analyzer", **config_params)
        assert backend.email == "original-error-test@example.com"

        backend = registry.create_backend("openalex_analyzer", **config_params)
        assert backend.email == "original-error-test@example.com"

        backend = registry.create_backend("cross_validator", **config_params)
        assert backend.email == "original-error-test@example.com"

    def test_email_parameter_merging_with_defaults(self):
        """Test that email parameters are properly merged with default configuration."""
        registry = get_backend_registry()

        # Test with only email (should use default cache_ttl_hours)
        backend1 = registry.create_backend(
            "crossref_analyzer", email="merge-test1@example.com"
        )
        assert backend1.email == "merge-test1@example.com"
        assert backend1.cache_ttl_hours == 24  # Default value

        # Test with only cache_ttl_hours (should use default email)
        backend2 = registry.create_backend("crossref_analyzer", cache_ttl_hours=48)
        assert backend2.email == "noreply@aletheia-probe.org"  # Default value
        assert backend2.cache_ttl_hours == 48

        # Test with both parameters
        backend3 = registry.create_backend(
            "crossref_analyzer", email="merge-test3@example.com", cache_ttl_hours=72
        )
        assert backend3.email == "merge-test3@example.com"
        assert backend3.cache_ttl_hours == 72

    def test_no_regression_with_backends_without_email(self):
        """Test that backends without email configuration still work correctly.

        Make sure our fix didn't break backends that don't use email parameters.
        """
        registry = get_backend_registry()

        # Test backends that don't use email parameters
        doaj_backend = registry.get_backend("doaj")
        assert doaj_backend is not None
        assert doaj_backend.get_name() == "doaj"

        scopus_backend = registry.get_backend("scopus")
        assert scopus_backend is not None
        assert scopus_backend.get_name() == "scopus"

        # These should not have email attributes and shouldn't cause errors
        assert not hasattr(doaj_backend, "email") or doaj_backend.email is None
        assert not hasattr(scopus_backend, "email") or scopus_backend.email is None


class TestEmailConfigurationValidation:
    """Tests for email validation and edge cases."""

    @pytest.mark.parametrize(
        "email",
        [
            "user@example.com",
            "test.user+tag@subdomain.example.org",
            "simple@test.co.uk",
            "name@domain.info",
        ],
    )
    def test_valid_email_formats(self, email):
        """Test that various valid email formats work with backend creation."""
        registry = get_backend_registry()

        backend = registry.create_backend("crossref_analyzer", email=email)
        assert backend.email == email

    def test_empty_email_handling(self):
        """Test behavior with empty or None email values."""
        registry = get_backend_registry()

        # Test with default (no email parameter)
        backend1 = registry.create_backend("crossref_analyzer")
        assert backend1.email == "noreply@aletheia-probe.org"

        # Test with explicit None - this should work and use None as the email value
        # The backend accepts None as a valid email value
        backend2 = registry.create_backend("crossref_analyzer", email=None)
        assert backend2.email is None

    def test_invalid_email_type_handling(self):
        """Test behavior with different email types.

        The current implementation accepts various types and converts them to strings.
        This documents the actual behavior rather than enforcing strict validation.
        """
        registry = get_backend_registry()

        # The backend currently accepts various types and converts them
        # This is the actual behavior - document it in tests
        backend1 = registry.create_backend("crossref_analyzer", email=123)
        assert backend1.email == 123  # Gets stored as-is

        backend2 = registry.create_backend("crossref_analyzer", email=[])
        assert backend2.email == []  # Gets stored as-is

        backend3 = registry.create_backend("crossref_analyzer", email={})
        assert backend3.email == {}  # Gets stored as-is

        # Note: In a production system, you might want stricter email validation
        # but this test documents the current permissive behavior
