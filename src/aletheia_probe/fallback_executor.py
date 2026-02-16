# SPDX-License-Identifier: MIT
"""Automatic fallback chain execution framework for backend queries."""

import asyncio
import time
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from .backend_exceptions import (
    BackendAuthenticationError,
    BackendConnectionError,
    BackendError,
    BackendNotFoundError,
    BackendTimeoutError,
    RateLimitError,
)
from .fallback_chain import FallbackStrategy, QueryFallbackChain
from .models import BackendResult, QueryInput


T = TypeVar("T")


async def _call_async_or_sync_method(obj: Any, method_name: str, *args: Any) -> Any:
    """Helper to call a method that might be async or sync.

    Args:
        obj: Object containing the method
        method_name: Name of the method to call
        *args: Arguments to pass to the method

    Returns:
        Result of the method call
    """
    method = getattr(obj, method_name)
    if asyncio.iscoroutinefunction(method):
        return await method(*args)
    else:
        return method(*args)


def _get_response_time(start_time: float) -> float:
    """Return elapsed time in seconds from a start timestamp."""
    return time.time() - start_time


async def _build_error_result(
    backend: Any,
    exception: Exception,
    start_time: float,
    chain: QueryFallbackChain,
) -> BackendResult:
    """Build an error result for the current fallback chain state."""
    response_time = _get_response_time(start_time)
    error_result: BackendResult = await _call_async_or_sync_method(
        backend, "_build_error_result", exception, response_time, chain
    )
    return error_result


def _classify_strategy_exception(exception: Exception) -> tuple[str, str]:
    """Classify strategy exception handling behavior and log query value."""
    if isinstance(exception, RateLimitError):
        return "return", f"Rate limited: {exception}"
    if isinstance(
        exception,
        (
            BackendTimeoutError,
            BackendConnectionError,
            BackendAuthenticationError,
        ),
    ):
        return "return", f"System error: {exception}"
    if isinstance(exception, BackendError) and not isinstance(
        exception, BackendNotFoundError
    ):
        return "return", f"Backend error: {exception}"
    if isinstance(exception, BackendNotFoundError):
        return "continue", f"Not found: {exception}"
    return "return", f"System error: {exception}"


def automatic_fallback(
    strategies: list[FallbackStrategy],
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator that automatically executes fallback chain strategies.

    This decorator replaces manual if/elif chains in backend _query_api methods
    with automatic strategy execution. It creates a QueryFallbackChain, executes
    each strategy in sequence until one succeeds, and automatically logs all attempts.

    Args:
        strategies: List of fallback strategies to execute in order

    Returns:
        Decorated function that executes automatic fallback chain

    Example:
        @automatic_fallback([
            FallbackStrategy.ISSN,
            FallbackStrategy.NORMALIZED_NAME,
            FallbackStrategy.ALIASES,
        ])
        async def _query_api(self, query_input: QueryInput) -> BackendResult:
            pass  # Decorator handles all execution logic

    The backend must implement strategy handler methods like:
    - async def handle_issn_strategy(self, query_input: QueryInput) -> Any | None
    - async def handle_normalized_name_strategy(self, query_input: QueryInput) -> Any | None
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        """Decorate backend query functions with automatic fallback execution."""

        @wraps(func)
        async def wrapper(
            self: Any, query_input: QueryInput, *args: Any, **kwargs: Any
        ) -> BackendResult:
            """Execute fallback strategies and return the first usable result."""
            start_time = time.time()

            # Create fallback chain with planned strategies
            chain = QueryFallbackChain(strategies)

            # Get strategy executor for this backend
            executor = FallbackStrategyExecutor(self, query_input, chain)

            # Execute strategies in order until one succeeds
            result_data = None
            for strategy in strategies:
                try:
                    result_data = await executor.execute_strategy(strategy)
                    if result_data is not None:
                        # Success - log attempt and build result
                        confidence = await executor.calculate_confidence(
                            result_data, strategy
                        )
                        chain.log_attempt(
                            strategy,
                            success=True,
                            query_value=str(result_data),
                            match_confidence=confidence,
                        )

                        response_time = _get_response_time(start_time)

                        success_result: BackendResult = (
                            await _call_async_or_sync_method(
                                self,
                                "_build_success_result_with_chain",
                                result_data,
                                query_input,
                                chain,
                                response_time,
                            )
                        )
                        return success_result
                    else:
                        # Strategy failed - log failure
                        chain.log_attempt(strategy, success=False)

                except Exception as e:
                    action, query_value = _classify_strategy_exception(e)
                    chain.log_attempt(strategy, success=False, query_value=query_value)
                    if action == "continue":
                        continue

                    return await _build_error_result(self, e, start_time, chain)

            # All strategies failed - return not found result
            response_time = _get_response_time(start_time)

            not_found_result: BackendResult = await _call_async_or_sync_method(
                self,
                "_build_not_found_result_with_chain",
                query_input,
                chain,
                response_time,
            )
            return not_found_result

        return wrapper

    return decorator


class FallbackStrategyExecutor:
    """Executes fallback strategies automatically using backend-specific handlers.

    This class maps FallbackStrategy enum values to handler method names and
    executes them using the backend's specific implementations.
    """

    def __init__(
        self, backend: Any, query_input: QueryInput, chain: QueryFallbackChain
    ):
        """Initialize executor with backend instance and query context.

        Args:
            backend: Backend instance that implements strategy handlers
            query_input: Query input data
            chain: Fallback chain for logging attempts
        """
        self.backend = backend
        self.query_input = query_input
        self.chain = chain

        # Map strategies to handler method names
        self._strategy_handlers = {
            FallbackStrategy.ISSN: "handle_issn_strategy",
            FallbackStrategy.EISSN: "handle_eissn_strategy",
            FallbackStrategy.EXACT_NAME: "handle_exact_name_strategy",
            FallbackStrategy.NORMALIZED_NAME: "handle_normalized_name_strategy",
            FallbackStrategy.FUZZY_NAME: "handle_fuzzy_name_strategy",
            FallbackStrategy.RAW_INPUT: "handle_raw_input_strategy",
            FallbackStrategy.ALIASES: "handle_aliases_strategy",
            FallbackStrategy.EXACT_ALIASES: "handle_exact_aliases_strategy",
            FallbackStrategy.ACRONYMS: "handle_acronyms_strategy",
            FallbackStrategy.SUBSTRING_MATCH: "handle_substring_match_strategy",
            FallbackStrategy.WORD_SIMILARITY: "handle_word_similarity_strategy",
        }

    async def execute_strategy(self, strategy: FallbackStrategy) -> Any | None:
        """Execute a specific fallback strategy using the backend's handler.

        Args:
            strategy: The strategy to execute

        Returns:
            Result from strategy execution, or None if no match found

        Raises:
            ValueError: If strategy has no defined handler
            NotImplementedError: If backend doesn't implement the strategy handler
            Exception: If strategy execution fails
        """
        handler_name = self._strategy_handlers.get(strategy)
        if not handler_name:
            raise ValueError(f"No handler defined for strategy: {strategy}")

        # Check if backend implements this strategy handler
        if not hasattr(self.backend, handler_name):
            raise NotImplementedError(
                f"Backend {self.backend.get_name()} does not implement {handler_name}"
            )

        handler = getattr(self.backend, handler_name)
        return await handler(self.query_input)

    async def calculate_confidence(
        self, result_data: Any, strategy: FallbackStrategy
    ) -> float | None:
        """Calculate confidence score for the result using backend-specific logic.

        Args:
            result_data: Raw result data from strategy execution
            strategy: Strategy that produced the result

        Returns:
            Confidence score if backend implements calculation, None otherwise
        """
        # Check if backend has a confidence calculation method
        if hasattr(self.backend, "_calculate_match_confidence"):
            try:
                result = self.backend._calculate_match_confidence(
                    self.query_input, result_data
                )
                # Ensure result is float or None
                if isinstance(result, (int, float)):
                    return float(result)
                return None
            except Exception:
                # If confidence calculation fails, return None
                return None
        return None
