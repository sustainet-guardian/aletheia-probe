# SPDX-License-Identifier: MIT
"""Cross-validation registry for managing backend pair validators."""

from typing import Any

from ..models import BackendResult
from .validators import BaseValidator, OpenAlexCrossRefValidator


class CrossValidationRegistry:
    """Registry for managing cross-validation between backend pairs."""

    def __init__(self) -> None:
        """Initialize the cross-validation registry."""
        self._validators: dict[tuple[str, str], type[BaseValidator]] = {
            ("openalex_analyzer", "crossref_analyzer"): OpenAlexCrossRefValidator,
            (
                "crossref_analyzer",
                "openalex_analyzer",
            ): OpenAlexCrossRefValidator,  # Order-independent
        }

    def register_validator(
        self, backend1: str, backend2: str, validator_class: type[BaseValidator]
    ) -> None:
        """Register a validator for a pair of backends.

        Args:
            backend1: Name of the first backend
            backend2: Name of the second backend
            validator_class: Validator class to handle this pair
        """
        self._validators[(backend1, backend2)] = validator_class
        self._validators[(backend2, backend1)] = validator_class  # Order-independent

    def get_validator(self, backend1: str, backend2: str) -> type[BaseValidator] | None:
        """Get validator for a pair of backends.

        Args:
            backend1: Name of the first backend
            backend2: Name of the second backend

        Returns:
            Validator class if registered, None otherwise
        """
        return self._validators.get((backend1, backend2))

    def validate_pair(
        self,
        backend1: str,
        result1: BackendResult,
        backend2: str,
        result2: BackendResult,
    ) -> dict[str, Any] | None:
        """Cross-validate results from a pair of backends.

        Args:
            backend1: Name of the first backend
            result1: Result from the first backend
            backend2: Name of the second backend
            result2: Result from the second backend

        Returns:
            Cross-validation result dictionary if validator exists, None otherwise
        """
        validator_class = self.get_validator(backend1, backend2)
        if validator_class is None:
            return None

        validator = validator_class()
        return validator.validate(result1, result2)

    def get_registered_pairs(self) -> list[tuple[str, str]]:
        """Get all registered backend pairs.

        Returns:
            List of (backend1, backend2) tuples
        """
        # Return unique pairs (avoid duplicates from order-independence)
        unique_pairs: set[tuple[str, str]] = set()
        for backend1, backend2 in self._validators.keys():
            pair = tuple(sorted([backend1, backend2]))
            unique_pairs.add(pair)  # type: ignore[arg-type]
        return list(unique_pairs)
