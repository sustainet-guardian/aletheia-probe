# SPDX-License-Identifier: MIT
"""Abstract base class and utilities for journal assessment backends."""

import asyncio
import hashlib
import inspect
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from ..cache import get_cache_manager
from ..enums import AssessmentType, EvidenceType
from ..models import AssessmentResult, BackendResult, BackendStatus, QueryInput


class Backend(ABC):
    """Abstract base class for all journal assessment backends."""

    def __init__(self, cache_ttl_hours: int = 24):
        """Initialize backend with cache TTL."""
        self.cache_ttl_hours = cache_ttl_hours

    @abstractmethod
    async def query(self, query_input: QueryInput) -> BackendResult:
        """Query the backend with normalized input and return result.

        Args:
            query_input: Normalized query input with journal information

        Returns:
            BackendResult with assessment data and metadata
        """
        pass

    @abstractmethod
    def get_name(self) -> str:
        """Return the human-readable name of this backend."""
        pass

    @abstractmethod
    def get_description(self) -> str:
        """Return a description of what this backend checks."""
        pass

    @abstractmethod
    def get_evidence_type(self) -> EvidenceType:
        """Return the type of evidence this backend provides."""
        pass

    async def query_with_timeout(
        self, query_input: QueryInput, timeout: int = 10
    ) -> BackendResult:
        """Query with timeout handling.

        Args:
            query_input: Query input data
            timeout: Timeout in seconds

        Returns:
            BackendResult, with status TIMEOUT if the query times out
        """
        start_time = time.time()

        try:
            result = await asyncio.wait_for(self.query(query_input), timeout=timeout)
            return result
        except asyncio.TimeoutError:
            response_time = time.time() - start_time
            return BackendResult(
                backend_name=self.get_name(),
                status=BackendStatus.TIMEOUT,
                confidence=0.0,
                assessment=None,
                error_message=f"Query timed out after {timeout} seconds",
                response_time=response_time,
                cached=False,  # Timeout from live query
            )
        except Exception as e:
            response_time = time.time() - start_time
            return BackendResult(
                backend_name=self.get_name(),
                status=BackendStatus.ERROR,
                confidence=0.0,
                assessment=None,
                error_message=str(e),
                response_time=response_time,
                cached=False,  # Error from live query
            )


class CachedBackend(Backend):
    """Base class for backends that use local cached data."""

    def __init__(
        self, source_name: str, list_type: AssessmentType, cache_ttl_hours: int = 24
    ):
        super().__init__(cache_ttl_hours)
        self.source_name = source_name
        self.list_type = list_type

    def get_evidence_type(self) -> EvidenceType:
        """Return evidence type based on list type."""
        if self.list_type == AssessmentType.PREDATORY:
            return EvidenceType.PREDATORY_LIST
        elif self.list_type == AssessmentType.LEGITIMATE:
            return EvidenceType.LEGITIMATE_LIST
        else:
            # Default to heuristic for unknown list types
            return EvidenceType.HEURISTIC

    async def query(self, query_input: QueryInput) -> BackendResult:
        """Query cached data for journal information."""
        start_time = time.time()

        try:
            # Search by ISSN first (most reliable)
            if query_input.identifiers.get("issn"):
                results = get_cache_manager().search_journals(
                    issn=query_input.identifiers["issn"],
                    source_name=self.source_name,
                    assessment=self.list_type,
                )
            else:
                results = []

            # If no ISSN match, try exact normalized name match
            if not results and query_input.normalized_name:
                results = self._search_exact_match(query_input.normalized_name)

            # Try aliases for exact matches only
            if not results:
                for alias in query_input.aliases:
                    results = self._search_exact_match(alias)
                    if results:
                        break

            response_time = time.time() - start_time

            if results:
                # Found in cache
                confidence = self._calculate_confidence(query_input, results[0])
                assessment = self.list_type  # 'predatory' or 'legitimate'

                return BackendResult(
                    backend_name=self.get_name(),
                    status=BackendStatus.FOUND,
                    confidence=confidence,
                    assessment=assessment,
                    data={
                        "matches": len(results),
                        "source_data": results[0] if results else None,
                    },
                    sources=[self.source_name],
                    error_message=None,
                    response_time=response_time,
                    cached=True,  # CachedBackend results are always from local cache
                )
            else:
                # Not found in cache
                return BackendResult(
                    backend_name=self.get_name(),
                    status=BackendStatus.NOT_FOUND,
                    confidence=0.0,
                    assessment=None,
                    data={"searched_in": self.source_name},
                    sources=[self.source_name],
                    error_message=None,
                    response_time=response_time,
                    cached=True,  # Still searched local cache, just no match
                )

        except Exception as e:
            return BackendResult(
                backend_name=self.get_name(),
                status=BackendStatus.ERROR,
                confidence=0.0,
                assessment=None,
                error_message=str(e),
                response_time=time.time() - start_time,
                cached=False,  # Error occurred before cache lookup
            )

    def _search_exact_match(self, name: str) -> list[dict[str, Any]]:
        """Search for exact journal name matches using optimized SQL query."""
        # Use optimized cache manager method with SQL WHERE clause
        return get_cache_manager().search_journals_by_name(
            name=name, source_name=self.source_name, assessment=self.list_type
        )

    def _calculate_confidence(
        self, query_input: QueryInput, match: dict[str, Any]
    ) -> float:
        """Calculate confidence based on match quality - exact matches only."""

        # High confidence for exact ISSN match
        if (
            query_input.identifiers.get("issn")
            and match.get("issn") == query_input.identifiers["issn"]
        ):
            return 0.95

        # High confidence for exact name match (case insensitive)
        if query_input.normalized_name:
            query_name = query_input.normalized_name.lower().strip()
            match_name = match.get("normalized_name", "").lower().strip()
            original_name = match.get("journal_name", "").lower().strip()

            if query_name == match_name or query_name == original_name:
                return 0.90

        # If we get here, it means we have a match but it's not exact
        # This shouldn't happen with our new exact matching, so low confidence
        return 0.3


class HybridBackend(Backend):
    """Base class for backends that check cache first, then fallback to API."""

    def __init__(self, cache_ttl_hours: int = 24):
        super().__init__(cache_ttl_hours)

    def get_evidence_type(self) -> EvidenceType:
        """HybridBackend provides heuristic evidence by default."""
        return EvidenceType.HEURISTIC

    async def query(self, query_input: QueryInput) -> BackendResult:
        """Check cache first, then query live API if needed."""
        start_time = time.time()

        # Generate cache key for this query
        cache_key = self._generate_cache_key(query_input)

        # Try cache first
        cached_result = get_cache_manager().get_cached_assessment(cache_key)
        if cached_result:
            # Update the cached result to indicate it came from cache
            cache_lookup_time = time.time() - start_time
            for backend_result in cached_result.backend_results:
                if backend_result.backend_name == self.get_name():
                    backend_result.cached = True
                    backend_result.response_time = cache_lookup_time
                    backend_result.data = {**backend_result.data, "from_cache": True}
                    return backend_result

        # Cache miss - query the live API
        result = await self._query_api(query_input)

        # Cache the result if successful
        if result.status in [BackendStatus.FOUND, BackendStatus.NOT_FOUND]:
            # For caching, we need to create a minimal AssessmentResult
            assessment_result = AssessmentResult(
                input_query=query_input.raw_input,
                assessment=result.assessment or "unknown",
                confidence=result.confidence,
                overall_score=result.confidence,
                backend_results=[result],
                metadata=None,
                processing_time=result.response_time,
            )
            get_cache_manager().cache_assessment_result(
                cache_key,
                query_input.raw_input,
                assessment_result,
                self.cache_ttl_hours,
            )

        return result

    @abstractmethod
    async def _query_api(self, query_input: QueryInput) -> BackendResult:
        """Query the live API. Must be implemented by subclasses."""
        pass

    def _generate_cache_key(self, query_input: QueryInput) -> str:
        """Generate a cache key for the query."""
        # Use normalized name and identifiers to create a consistent key
        key_parts = [
            self.get_name(),
            query_input.normalized_name or "",
            query_input.identifiers.get("issn", ""),
            query_input.identifiers.get("doi", ""),
        ]
        key_string = "|".join(key_parts)
        return hashlib.md5(key_string.encode(), usedforsecurity=False).hexdigest()  # nosec B324 - MD5 used for cache key, not security

    async def query_with_timeout(
        self, query_input: QueryInput, timeout: int = 10
    ) -> BackendResult:
        """Query with timeout handling.

        Args:
            query_input: Query input data
            timeout: Timeout in seconds

        Returns:
            BackendResult, with status TIMEOUT if the query times out
        """
        start_time = time.time()

        try:
            result = await asyncio.wait_for(self.query(query_input), timeout=timeout)
            return result
        except asyncio.TimeoutError:
            response_time = time.time() - start_time
            return BackendResult(
                backend_name=self.get_name(),
                status=BackendStatus.TIMEOUT,
                confidence=0.0,
                assessment=None,
                error_message=f"Query timed out after {timeout} seconds",
                response_time=response_time,
                cached=False,  # Timeout from query (cache or API)
            )
        except Exception as e:
            response_time = time.time() - start_time
            return BackendResult(
                backend_name=self.get_name(),
                status=BackendStatus.ERROR,
                confidence=0.0,
                assessment=None,
                error_message=str(e),
                response_time=response_time,
                cached=False,  # Error from query (cache or API)
            )


class BackendRegistry:
    """Registry for managing available backends with factory-based creation."""

    def __init__(self) -> None:
        self._factories: dict[str, Callable[..., Backend]] = {}
        self._default_configs: dict[str, dict[str, Any]] = {}

    def register_factory(
        self,
        name: str,
        factory: Callable[..., Backend],
        default_config: dict[str, Any] | None = None,
    ) -> None:
        """Register a backend factory function.

        Args:
            name: Backend name (must match backend.get_name())
            factory: Factory function that creates backend instances
            default_config: Default configuration values
        """
        self._factories[name] = factory
        self._default_configs[name] = default_config or {}

    def create_backend(self, name: str, **config: Any) -> Backend:
        """Create a backend instance with configuration.

        Args:
            name: Backend name
            **config: Configuration parameters to override defaults

        Returns:
            Backend instance configured with the provided parameters
        """
        if name not in self._factories:
            raise ValueError(f"Backend '{name}' not found")

        # Merge provided config with defaults
        merged_config = {**self._default_configs[name], **config}

        # Filter config parameters based on factory signature
        factory = self._factories[name]
        filtered_config = self._filter_config_params(factory, merged_config)

        # Create backend instance using factory
        return factory(**filtered_config)

    def _filter_config_params(
        self, factory: Callable[..., Backend], config: dict[str, Any]
    ) -> dict[str, Any]:
        """Filter config parameters based on factory function signature.

        Args:
            factory: Backend factory function
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
        except Exception:
            # If signature inspection fails, return original config
            # This ensures backward compatibility
            return config

    def get_supported_params(self, name: str) -> set[str]:
        """Get the set of parameters supported by a backend.

        Args:
            name: Backend name

        Returns:
            Set of parameter names the backend accepts
        """
        if name not in self._factories:
            return set()

        try:
            factory = self._factories[name]
            sig = inspect.signature(factory)
            return set(sig.parameters.keys())
        except Exception:
            # If signature inspection fails, return empty set
            return set()

    def get_backend(self, name: str) -> Backend:
        """Get a backend by name with default configuration."""
        return self.create_backend(name)

    def get_all_backends(self) -> list[Backend]:
        """Get all registered backends with default configuration."""
        backends: list[Backend] = []

        # Create default instances from factories
        for name in self._factories:
            try:
                backends.append(self.create_backend(name))
            except Exception:
                # Skip backends that fail to create with default config
                pass

        return backends

    def get_backend_names(self) -> list[str]:
        """Get names of all registered backends."""
        return list(self._factories.keys())

    def list_all(self) -> list[Backend]:
        """List all registered backends (alias for get_all_backends)."""
        return self.get_all_backends()


# Global backend registry with factory pattern
_backend_registry_instance: BackendRegistry | None = None


def get_backend_registry() -> BackendRegistry:
    """Get or create the global backend registry instance.

    Returns:
        The global BackendRegistry instance
    """
    global _backend_registry_instance
    if _backend_registry_instance is None:
        _backend_registry_instance = BackendRegistry()
    return _backend_registry_instance


def set_backend_registry(registry: BackendRegistry) -> None:
    """Set the backend registry instance (primarily for testing).

    Args:
        registry: BackendRegistry instance to use globally
    """
    global _backend_registry_instance
    _backend_registry_instance = registry


def reset_backend_registry() -> None:
    """Reset the backend registry instance (primarily for testing)."""
    global _backend_registry_instance
    _backend_registry_instance = None
