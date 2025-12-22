# SPDX-License-Identifier: MIT
"""Retry utilities for API calls."""

import asyncio
from collections.abc import Callable
from functools import wraps
from typing import Any

from .logging_config import get_detail_logger


detail_logger = get_detail_logger()


def async_retry_with_backoff(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator for retrying async functions with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        exponential_base: Base for exponential backoff calculation
        exceptions: Tuple of exception types to catch and retry

    Returns:
        Decorated async function

    Example:
        >>> @async_retry_with_backoff(max_retries=3)
        ... async def fetch_data():
        ...     return await api.get("/data")
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            delay = initial_delay

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_retries:
                        detail_logger.debug(
                            f"{func.__name__} failed after {max_retries} retries: {e}"
                        )
                        raise

                    detail_logger.debug(
                        f"{func.__name__} failed (attempt {attempt + 1}/{max_retries}): {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    await asyncio.sleep(delay)
                    delay = min(delay * exponential_base, max_delay)

            raise RuntimeError("Retry logic failed unexpectedly")

        return wrapper

    return decorator
