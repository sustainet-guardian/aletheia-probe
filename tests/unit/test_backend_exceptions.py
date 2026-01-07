# SPDX-License-Identifier: MIT
"""Tests for backend exceptions."""

from aletheia_probe.backend_exceptions import (
    BackendAuthenticationError,
    BackendConnectionError,
    BackendError,
    BackendNotFoundError,
    BackendTimeoutError,
    RateLimitError,
)


class TestBackendExceptions:
    """Tests for backend exception hierarchy and behavior."""

    def test_backend_error_base(self) -> None:
        """Test base BackendError initialization."""
        err = BackendError("Something failed", backend_name="test_backend")
        assert str(err) == "Something failed"
        assert err.backend_name == "test_backend"

    def test_backend_error_no_name(self) -> None:
        """Test BackendError without backend name."""
        err = BackendError("Something failed")
        assert str(err) == "Something failed"
        assert err.backend_name is None

    def test_rate_limit_error_default(self) -> None:
        """Test RateLimitError with defaults."""
        err = RateLimitError()
        assert "API rate limit exceeded" in str(err)
        assert err.retry_after is None
        assert err.backend_name is None

    def test_rate_limit_error_with_retry(self) -> None:
        """Test RateLimitError with retry_after."""
        err = RateLimitError(retry_after=60, backend_name="doaj")
        assert "Retry after 60s" in str(err)
        assert err.retry_after == 60
        assert err.backend_name == "doaj"

    def test_rate_limit_error_custom_message(self) -> None:
        """Test RateLimitError with custom message."""
        err = RateLimitError(message="Slow down", retry_after=10)
        assert "Slow down" in str(err)
        assert "Retry after 10s" in str(err)

    def test_inheritance(self) -> None:
        """Test that all specific exceptions inherit from BackendError."""
        assert issubclass(RateLimitError, BackendError)
        assert issubclass(BackendTimeoutError, BackendError)
        assert issubclass(BackendConnectionError, BackendError)
        assert issubclass(BackendNotFoundError, BackendError)
        assert issubclass(BackendAuthenticationError, BackendError)

    def test_subclass_initialization(self) -> None:
        """Test initialization of simple subclasses."""
        err = BackendTimeoutError("Timed out", backend_name="openalex")
        assert isinstance(err, BackendError)
        assert str(err) == "Timed out"
        assert err.backend_name == "openalex"
