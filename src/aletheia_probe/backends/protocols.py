# SPDX-License-Identifier: MIT
"""Protocol definitions for backend capabilities and interfaces."""

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from ..utils.dead_code import code_is_used


if TYPE_CHECKING:
    from ..models import BackendResult, QueryInput
    from ..updater.core import DataSource


@runtime_checkable
class DataSyncCapable(Protocol):
    """Protocol for backends that can synchronize with external data sources.

    This protocol defines the interface for backends that need to sync data
    from external sources before being able to answer queries. It separates
    data synchronization concerns from query behavior, allowing any backend
    to opt into data sync capabilities without inheritance constraints.

    Example implementations:
    - Backends with static data sources (CachedBackend subclasses)
    - Hybrid backends that need local data sync (e.g., RetractionWatchBackend)
    """

    @property
    @code_is_used
    def source_name(self) -> str:
        """Name of the data source for synchronization.

        Returns:
            The name identifier for this backend's data source,
            matching a registered DataSource implementation.
        """
        ...

    @code_is_used
    def get_data_source(self) -> "DataSource | None":
        """Get the data source instance for synchronization.

        Returns:
            DataSource instance capable of fetching external data,
            or None if data source is not available or not needed.
        """
        ...

    @code_is_used
    def needs_sync(self) -> bool:
        """Check if backend requires data synchronization.

        This method should check the current state of local data
        and determine whether a sync operation is needed.

        Returns:
            True if backend data needs to be synced, False otherwise.
        """
        ...


@runtime_checkable
class ApiQueryCapable(Protocol):
    """Protocol for backends that can query live APIs with cache-first behavior.

    This protocol defines the interface for backends that implement a cache-first
    strategy: check cache first, then fallback to live API queries if cache misses.
    Results from API calls are automatically cached for future queries.

    Example implementations:
    - API-only backends (DOAJ, OpenAlex, Crossref analyzers)
    - Hybrid backends with local data + API calls (RetractionWatch)
    """

    @code_is_used
    async def _query_api(self, query_input: "QueryInput") -> "BackendResult":
        """Query the live API when cache misses.

        This method is called by the cache-first query logic when no cached
        result is found. Implementation should query the external API and
        return a BackendResult with the findings.

        Args:
            query_input: Normalized query input with journal information

        Returns:
            BackendResult with status, confidence, assessment, and data
        """
        ...

    @code_is_used
    def _generate_cache_key(self, query_input: "QueryInput") -> str:
        """Generate a cache key for the query.

        Creates a consistent cache key based on the query parameters.
        This key is used to store and retrieve cached API results.

        Args:
            query_input: Query input to generate key for

        Returns:
            String cache key (typically MD5 hash of query components)
        """
        ...
