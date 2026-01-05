# SPDX-License-Identifier: MIT
"""Protocol definitions for cross-validation capabilities."""

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from ..utils.dead_code import code_is_used


if TYPE_CHECKING:
    from ..models import BackendResult


@runtime_checkable
class CrossValidationCapable(Protocol):
    """Protocol for cross-validation between backend pairs.

    This protocol defines the interface for validators that can cross-validate
    results from two backends. It follows the same pattern as other capability
    protocols in the codebase (DataSyncCapable, ApiQueryCapable).

    Example implementations:
    - OpenAlex/CrossRef validator for consistency checks
    - OpenAlex/Retraction validator for research misconduct correlation
    - CrossRef/Scopus validator for metadata quality alignment
    """

    @code_is_used
    def validate(
        self, result1: "BackendResult", result2: "BackendResult"
    ) -> dict[str, Any]:
        """Cross-validate results from two backends.

        Args:
            result1: Result from the first backend
            result2: Result from the second backend

        Returns:
            Cross-validation result dictionary with confidence_adjustment,
            consistency_checks, reasoning, and agreement status
        """
        ...

    @property
    @code_is_used
    def supported_backend_pair(self) -> tuple[str, str]:
        """Get the backend pair this validator supports.

        Returns:
            Tuple of (backend1_name, backend2_name) that this validator
            can cross-validate. Order should not matter for validation.
        """
        ...
