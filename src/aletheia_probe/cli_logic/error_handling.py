# SPDX-License-Identifier: MIT
"""Shared CLI error handling utilities."""

import functools
import sys
import traceback
from collections.abc import Callable
from typing import Any, TypeVar

from ..logging_config import get_status_logger
from ..utils.dead_code import code_is_used


F = TypeVar("F", bound=Callable[..., Any])


@code_is_used  # This is called in error scenarios
def handle_cli_exception(
    exception: Exception, verbose: bool = False, context: str = ""
) -> None:
    """Handle CLI exceptions with consistent logging and exit behavior."""
    status_logger = get_status_logger()

    if isinstance(exception, FileNotFoundError):
        status_logger.error(f"Error: File not found: {exception}")
    elif isinstance(exception, ValueError):
        status_logger.error(f"Error: {exception}")
    elif isinstance(
        exception, (OSError, KeyError, RuntimeError, AttributeError, UnicodeDecodeError)
    ):
        if verbose:
            status_logger.error(
                f"Unexpected error{f' in {context}' if context else ''}: {exception}"
            )
            traceback.print_exc()
        else:
            status_logger.error("An unexpected error occurred. Use -v for details.")
    else:
        if verbose:
            status_logger.error(
                f"Error{f' in {context}' if context else ''}: {exception}"
            )
            traceback.print_exc()
        else:
            status_logger.error(f"Error: {exception}")

    sys.exit(1)


def handle_cli_errors(func: F) -> F:
    """Decorator to handle common CLI error patterns."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        status_logger = get_status_logger()
        verbose = kwargs.get("verbose", False)

        try:
            return func(*args, **kwargs)
        except Exception as e:
            if verbose:
                status_logger.error(f"Error in {func.__name__}: {e}")
                traceback.print_exc()
            else:
                status_logger.error(f"Error: {e}")
            sys.exit(1)

    return wrapper  # type: ignore
