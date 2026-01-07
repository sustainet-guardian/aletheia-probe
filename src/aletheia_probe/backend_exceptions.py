# SPDX-License-Identifier: MIT
"""Standard exceptions for Aletheia Probe backends."""


class BackendError(Exception):
    """Base class for all backend-related exceptions."""

    def __init__(self, message: str, backend_name: str | None = None) -> None:
        self.backend_name = backend_name
        super().__init__(message)


class RateLimitError(BackendError):
    """Raised when a backend API rate limit is hit."""

    def __init__(
        self,
        message: str = "API rate limit exceeded",
        retry_after: int | None = None,
        backend_name: str | None = None,
    ) -> None:
        self.retry_after = retry_after
        msg = f"{message}. Retry after {retry_after}s" if retry_after else message
        super().__init__(msg, backend_name)


class BackendTimeoutError(BackendError):
    """Raised when a backend API request times out."""

    pass


class BackendConnectionError(BackendError):
    """Raised when a backend API connection fails."""

    pass


class BackendNotFoundError(BackendError):
    """Raised when a requested resource is not found in the backend."""

    pass


class BackendAuthenticationError(BackendError):
    """Raised when backend API authentication fails."""

    pass
