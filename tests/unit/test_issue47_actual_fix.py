"""Test for the actual fix of issue #47.

Tests the real issue: CrossValidatorBackend was missing self.email = email in constructor.
"""

import pytest
from aletheia_probe.backends.base import get_backend_registry


class TestIssue47ActualFix:
    """Test the actual fix for issue #47: missing self.email attribute in CrossValidatorBackend."""

    def test_cross_validator_email_attribute_fix(self):
        """Test that CrossValidatorBackend properly stores the email attribute.

        This was the actual issue in #47. The constructor accepted an email parameter
        but didn't store it as self.email, causing AttributeError when accessing backend.email.
        """
        registry = get_backend_registry()

        # This was failing before the fix with: AttributeError: 'CrossValidatorBackend' object has no attribute 'email'
        backend = registry.create_backend("cross_validator", email="fix-test@example.com")

        # This line would fail without the self.email = email fix
        assert backend.email == "fix-test@example.com"

        # Verify email is also passed to sub-backends correctly
        assert backend.openalex_backend.email == "fix-test@example.com"
        assert backend.crossref_backend.email == "fix-test@example.com"

    def test_cross_validator_email_propagation(self):
        """Test that email configuration properly propagates to all components."""
        registry = get_backend_registry()

        test_email = "propagation-test@example.com"
        backend = registry.create_backend("cross_validator", email=test_email)

        # Main backend should store email
        assert hasattr(backend, 'email')
        assert backend.email == test_email

        # Sub-backends should also receive the email
        assert hasattr(backend.openalex_backend, 'email')
        assert backend.openalex_backend.email == test_email

        assert hasattr(backend.crossref_backend, 'email')
        assert backend.crossref_backend.email == test_email

    def test_other_backends_unaffected(self):
        """Test that the fix doesn't break other backends that were already working."""
        registry = get_backend_registry()

        # These backends were already working correctly before the fix
        crossref_backend = registry.create_backend("crossref_analyzer", email="test1@example.com")
        assert crossref_backend.email == "test1@example.com"

        openalex_backend = registry.create_backend("openalex_analyzer", email="test2@example.com")
        assert openalex_backend.email == "test2@example.com"

    def test_cross_validator_default_email(self):
        """Test that CrossValidatorBackend works with default email value."""
        registry = get_backend_registry()

        # Test with defaults (no email parameter)
        backend = registry.create_backend("cross_validator")

        # Should have default email
        assert backend.email == "noreply.aletheia-probe.org"
        assert backend.openalex_backend.email == "noreply.aletheia-probe.org"
        assert backend.crossref_backend.email == "noreply.aletheia-probe.org"

    def test_cross_validator_with_cache_ttl(self):
        """Test that CrossValidatorBackend correctly handles both email and cache_ttl_hours."""
        registry = get_backend_registry()

        backend = registry.create_backend(
            "cross_validator",
            email="cache-test@example.com",
            cache_ttl_hours=48
        )

        # Both parameters should be stored correctly
        assert backend.email == "cache-test@example.com"
        assert backend.cache_ttl_hours == 48

        # Sub-backends should get both parameters too
        assert backend.openalex_backend.email == "cache-test@example.com"
        assert backend.openalex_backend.cache_ttl_hours == 48
        assert backend.crossref_backend.email == "cache-test@example.com"
        assert backend.crossref_backend.cache_ttl_hours == 48