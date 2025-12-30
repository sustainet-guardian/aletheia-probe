"""Dead code detection utilities.

This module provides decorators for marking code that should be excluded
from dead code detection.
"""

from typing import Callable, TypeVar

F = TypeVar("F", bound=Callable)


def code_is_used(func: F) -> F:
    """Mark a function/method as used to exclude from dead code detection.

    This is a no-op decorator with zero runtime overhead. It serves as a marker
    for the dead code detection script to indicate that a function is called
    in ways that cannot be detected by runtime tracing.

    Use this decorator when:
    - Function is called via framework magic (e.g., Pydantic validators)
    - Function is called dynamically (e.g., via getattr, exec, or reflection)
    - Function is an entry point for external plugins or extensions
    - Function is called from generated code
    - Function is a Python magic method (__init__, __str__, etc.)

    Example:
        @code_is_used
        def __str__(self) -> str:
            return "MyClass"

        @code_is_used
        @field_validator('email')
        def validate_email(cls, value: str) -> str:
            return value.strip()

    Args:
        func: The function to mark as used

    Returns:
        The unmodified function (zero runtime overhead)
    """
    return func
