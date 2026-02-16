# SPDX-License-Identifier: MIT
"""Tests for fallback executor automatic fallback behavior."""

import pytest

from aletheia_probe.backend_exceptions import (
    BackendAuthenticationError,
    BackendError,
    BackendNotFoundError,
    BackendTimeoutError,
    RateLimitError,
)
from aletheia_probe.enums import AssessmentType
from aletheia_probe.fallback_chain import FallbackStrategy
from aletheia_probe.fallback_executor import automatic_fallback
from aletheia_probe.models import BackendResult, BackendStatus, QueryInput


class DummyBackend:
    """Backend test double for automatic fallback behavior."""

    def __init__(self) -> None:
        self.recorded_error: Exception | None = None

    def get_name(self) -> str:
        """Return backend name for fallback executor diagnostics."""
        return "dummy"

    def _calculate_match_confidence(
        self, query_input: QueryInput, result_data: object
    ) -> float:
        """Provide deterministic confidence for successful strategy logging."""
        return 0.42

    def _build_success_result_with_chain(
        self,
        result_data: object,
        query_input: QueryInput,
        chain: object,
        response_time: float,
    ) -> BackendResult:
        """Build success result for decorated fallback flow."""
        return BackendResult(
            backend_name="dummy",
            status=BackendStatus.FOUND,
            confidence=0.9,
            assessment=AssessmentType.LEGITIMATE,
            response_time=response_time,
            fallback_chain=chain,
            data={"result": str(result_data)},
        )

    def _build_error_result(
        self,
        exception: Exception,
        response_time: float,
        chain: object,
    ) -> BackendResult:
        """Build error result and keep exception for assertions."""
        self.recorded_error = exception
        return BackendResult(
            backend_name="dummy",
            status=BackendStatus.ERROR,
            confidence=0.0,
            assessment=AssessmentType.UNKNOWN,
            response_time=response_time,
            fallback_chain=chain,
            error_message=str(exception),
        )

    def _build_not_found_result_with_chain(
        self,
        query_input: QueryInput,
        chain: object,
        response_time: float,
    ) -> BackendResult:
        """Build not-found result for exhausted strategies."""
        return BackendResult(
            backend_name="dummy",
            status=BackendStatus.NOT_FOUND,
            confidence=0.0,
            assessment=AssessmentType.UNKNOWN,
            response_time=response_time,
            fallback_chain=chain,
        )

    @automatic_fallback([FallbackStrategy.ISSN, FallbackStrategy.NORMALIZED_NAME])
    async def query(self, query_input: QueryInput) -> BackendResult:
        """Decorated query method used by tests."""
        raise AssertionError("Decorator should execute fallback logic")


@pytest.mark.asyncio
async def test_automatic_fallback_returns_success_on_first_strategy() -> None:
    """Return success when first strategy produces result data."""

    class FirstSuccessBackend(DummyBackend):
        async def handle_issn_strategy(self, query_input: QueryInput) -> object:
            return {"id": "issn-match"}

        async def handle_normalized_name_strategy(
            self, query_input: QueryInput
        ) -> object | None:
            return None

    backend = FirstSuccessBackend()
    result = await backend.query(QueryInput(raw_input="test"))

    assert result.status == BackendStatus.FOUND
    assert result.fallback_chain.attempts[0].strategy == FallbackStrategy.ISSN
    assert result.fallback_chain.attempts[0].success is True
    assert result.fallback_chain.attempts[0].match_confidence == 0.42


@pytest.mark.asyncio
async def test_automatic_fallback_continues_on_backend_not_found_error() -> None:
    """Continue to next strategy when BackendNotFoundError is raised."""

    class ContinueOnNotFoundBackend(DummyBackend):
        async def handle_issn_strategy(self, query_input: QueryInput) -> object:
            raise BackendNotFoundError("missing")

        async def handle_normalized_name_strategy(self, query_input: QueryInput) -> str:
            return "normalized-match"

    backend = ContinueOnNotFoundBackend()
    result = await backend.query(QueryInput(raw_input="test"))

    assert result.status == BackendStatus.FOUND
    assert len(result.fallback_chain.attempts) == 2
    assert result.fallback_chain.attempts[0].query_value == "Not found: missing"
    assert (
        result.fallback_chain.attempts[1].strategy == FallbackStrategy.NORMALIZED_NAME
    )
    assert result.fallback_chain.attempts[1].success is True


@pytest.mark.asyncio
async def test_automatic_fallback_returns_error_on_rate_limit() -> None:
    """Return error immediately when rate-limit exception is raised."""

    class RateLimitedBackend(DummyBackend):
        async def handle_issn_strategy(self, query_input: QueryInput) -> object:
            raise RateLimitError("limited")

        async def handle_normalized_name_strategy(
            self, query_input: QueryInput
        ) -> object | None:
            return "should-not-run"

    backend = RateLimitedBackend()
    result = await backend.query(QueryInput(raw_input="test"))

    assert result.status == BackendStatus.ERROR
    assert isinstance(backend.recorded_error, RateLimitError)
    assert len(result.fallback_chain.attempts) == 1
    assert result.fallback_chain.attempts[0].query_value == "Rate limited: limited"


@pytest.mark.asyncio
async def test_automatic_fallback_returns_error_on_backend_error() -> None:
    """Return error immediately for non-NotFound backend errors."""

    class BackendFailureBackend(DummyBackend):
        async def handle_issn_strategy(self, query_input: QueryInput) -> object:
            raise BackendAuthenticationError("bad auth")

        async def handle_normalized_name_strategy(
            self, query_input: QueryInput
        ) -> object | None:
            return "should-not-run"

    backend = BackendFailureBackend()
    result = await backend.query(QueryInput(raw_input="test"))

    assert result.status == BackendStatus.ERROR
    assert isinstance(backend.recorded_error, BackendAuthenticationError)
    assert result.fallback_chain.attempts[0].query_value == "System error: bad auth"


@pytest.mark.asyncio
async def test_automatic_fallback_returns_not_found_when_all_strategies_fail() -> None:
    """Return not found when all strategies return no result."""

    class NoMatchesBackend(DummyBackend):
        async def handle_issn_strategy(self, query_input: QueryInput) -> object | None:
            return None

        async def handle_normalized_name_strategy(
            self, query_input: QueryInput
        ) -> object | None:
            return None

    backend = NoMatchesBackend()
    result = await backend.query(QueryInput(raw_input="test"))

    assert result.status == BackendStatus.NOT_FOUND
    assert len(result.fallback_chain.attempts) == 2
    assert all(attempt.success is False for attempt in result.fallback_chain.attempts)


@pytest.mark.asyncio
async def test_automatic_fallback_returns_error_on_generic_exception() -> None:
    """Return error immediately for non-backend exceptions."""

    class GenericFailureBackend(DummyBackend):
        async def handle_issn_strategy(self, query_input: QueryInput) -> object:
            raise ValueError("boom")

        async def handle_normalized_name_strategy(
            self, query_input: QueryInput
        ) -> object | None:
            return "should-not-run"

    backend = GenericFailureBackend()
    result = await backend.query(QueryInput(raw_input="test"))

    assert result.status == BackendStatus.ERROR
    assert isinstance(backend.recorded_error, ValueError)
    assert result.fallback_chain.attempts[0].query_value == "System error: boom"
