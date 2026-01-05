# SPDX-License-Identifier: MIT
"""Cross-validation registry for managing backend pair validators."""

import inspect
from collections.abc import Callable
from typing import Any

from ..models import BackendResult
from .protocols import CrossValidationCapable
from .validators import OpenAlexCrossRefValidator


class CrossValidationRegistry:
    """Registry for managing cross-validation validators with factory-based creation.

    This registry follows the same architectural patterns as BackendRegistry,
    using factory functions for validator creation with configuration support.
    """

    def __init__(self) -> None:
        """Initialize the cross-validation registry."""
        self._factories: dict[
            tuple[str, str], Callable[..., CrossValidationCapable]
        ] = {}
        self._default_configs: dict[tuple[str, str], dict[str, Any]] = {}

        # Register default validators
        self._register_default_validators()

    def _register_default_validators(self) -> None:
        """Register the default cross-validation validators."""
        # Register OpenAlex/CrossRef validator
        self.register_factory(
            "openalex_analyzer",
            "crossref_analyzer",
            lambda: OpenAlexCrossRefValidator(),
            default_config={},
        )

    def register_factory(
        self,
        backend1: str,
        backend2: str,
        factory: Callable[..., CrossValidationCapable],
        default_config: dict[str, Any] | None = None,
    ) -> None:
        """Register a validator factory function for a backend pair.

        Args:
            backend1: Name of the first backend
            backend2: Name of the second backend
            factory: Factory function that creates validator instances
            default_config: Default configuration values for the validator
        """
        pair_key = (backend1, backend2)
        self._factories[pair_key] = factory
        self._factories[(backend2, backend1)] = factory  # Order-independent

        config = default_config or {}
        self._default_configs[pair_key] = config
        self._default_configs[(backend2, backend1)] = config

    def create_validator(
        self, backend1: str, backend2: str, **config: Any
    ) -> CrossValidationCapable | None:
        """Create a validator instance with configuration.

        Args:
            backend1: Name of the first backend
            backend2: Name of the second backend
            **config: Configuration parameters to override defaults

        Returns:
            Validator instance configured with the provided parameters,
            or None if no validator is registered for this pair
        """
        pair_key = (backend1, backend2)
        if pair_key not in self._factories:
            return None

        # Merge provided config with defaults
        merged_config = {**self._default_configs[pair_key], **config}

        # Filter config parameters based on factory signature
        factory = self._factories[pair_key]
        filtered_config = self._filter_config_params(factory, merged_config)

        # Create validator instance using factory
        return factory(**filtered_config)

    def _filter_config_params(
        self, factory: Callable[..., CrossValidationCapable], config: dict[str, Any]
    ) -> dict[str, Any]:
        """Filter config parameters based on factory function signature.

        Args:
            factory: Validator factory function
            config: Configuration parameters to filter

        Returns:
            Filtered configuration with only parameters the factory accepts
        """
        try:
            sig = inspect.signature(factory)
            accepted_params = set(sig.parameters.keys())

            # Filter config to only include parameters the factory accepts
            filtered_config = {
                key: value for key, value in config.items() if key in accepted_params
            }

            return filtered_config
        except (AttributeError, ValueError, TypeError):
            # If signature inspection fails, return original config
            # This ensures backward compatibility
            return config

    def validate_pair(
        self,
        backend1: str,
        result1: BackendResult,
        backend2: str,
        result2: BackendResult,
        **config: Any,
    ) -> dict[str, Any] | None:
        """Cross-validate results from a pair of backends.

        Args:
            backend1: Name of the first backend
            result1: Result from the first backend
            backend2: Name of the second backend
            result2: Result from the second backend
            **config: Optional configuration for the validator

        Returns:
            Cross-validation result dictionary if validator exists, None otherwise
        """
        validator = self.create_validator(backend1, backend2, **config)
        if validator is None:
            return None

        return validator.validate(result1, result2)

    def get_registered_pairs(self) -> list[tuple[str, str]]:
        """Get all registered backend pairs.

        Returns:
            List of (backend1, backend2) tuples
        """
        # Return unique pairs (avoid duplicates from order-independence)
        unique_pairs: set[tuple[str, str]] = set()
        for backend1, backend2 in self._factories.keys():
            pair = tuple(sorted([backend1, backend2]))
            unique_pairs.add(pair)  # type: ignore[arg-type]
        return list(unique_pairs)

    def get_supported_params(self, backend1: str, backend2: str) -> set[str]:
        """Get the set of parameters supported by a validator.

        Args:
            backend1: Name of the first backend
            backend2: Name of the second backend

        Returns:
            Set of parameter names the validator factory accepts
        """
        pair_key = (backend1, backend2)
        if pair_key not in self._factories:
            return set()

        try:
            factory = self._factories[pair_key]
            sig = inspect.signature(factory)
            return set(sig.parameters.keys())
        except (KeyError, AttributeError, ValueError, TypeError):
            # If signature inspection fails, return empty set
            return set()


# Global cross-validation registry
_cross_validation_registry: CrossValidationRegistry | None = None


def get_cross_validation_registry() -> CrossValidationRegistry:
    """Get the global cross-validation registry instance.

    Returns:
        Global CrossValidationRegistry singleton
    """
    global _cross_validation_registry
    if _cross_validation_registry is None:
        _cross_validation_registry = CrossValidationRegistry()
    return _cross_validation_registry
