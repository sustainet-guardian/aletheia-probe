# SPDX-License-Identifier: MIT
"""Mixin providing default fallback strategy implementations for backends."""

from typing import Any

from ..models import QueryInput


class FallbackStrategyMixin:
    """Mixin providing common fallback strategy implementations for backends.

    This mixin provides default implementations for standard fallback strategies
    that can be reused across multiple backends. Backends inherit from this mixin
    and implement the abstract methods for their specific search logic.

    The mixin handles:
    - Strategy routing and parameter extraction
    - Common patterns like aliases iteration
    - Fallback logic between strategies

    Backends must implement:
    - _search_by_issn(issn: str) -> Any | None
    - _search_by_name(name: str, exact: bool = True) -> Any | None

    Optional methods (with default implementations):
    - _search_by_substring(name: str) -> Any | None
    - _search_by_similarity(name: str) -> Any | None
    """

    async def handle_issn_strategy(self, query_input: QueryInput) -> Any | None:
        """Default ISSN strategy implementation.

        Searches using the ISSN identifier if available.

        Args:
            query_input: Query input containing ISSN identifier

        Returns:
            Raw result data if found, None if no ISSN or no match
        """
        issn = query_input.identifiers.get("issn")
        if issn:
            return await self._search_by_issn(issn)
        return None

    async def handle_eissn_strategy(self, query_input: QueryInput) -> Any | None:
        """Default eISSN strategy implementation.

        Searches using the eISSN identifier if available.

        Args:
            query_input: Query input containing eISSN identifier

        Returns:
            Raw result data if found, None if no eISSN or no match
        """
        eissn = query_input.identifiers.get("eissn")
        if eissn:
            return await self._search_by_issn(eissn)
        return None

    async def handle_normalized_name_strategy(
        self, query_input: QueryInput
    ) -> Any | None:
        """Default normalized name strategy implementation.

        Searches using the normalized journal name with exact matching.

        Args:
            query_input: Query input with normalized journal name

        Returns:
            Raw result data if found, None if no normalized name or no match
        """
        if query_input.normalized_name:
            return await self._search_by_name(query_input.normalized_name, exact=True)
        return None

    async def handle_exact_name_strategy(self, query_input: QueryInput) -> Any | None:
        """Default exact name strategy implementation.

        For most backends, this is the same as normalized name strategy.

        Args:
            query_input: Query input with journal name

        Returns:
            Raw result data if found, None if no match
        """
        return await self.handle_normalized_name_strategy(query_input)

    async def handle_fuzzy_name_strategy(self, query_input: QueryInput) -> Any | None:
        """Default fuzzy name strategy implementation.

        Searches using the normalized journal name with fuzzy matching.

        Args:
            query_input: Query input with journal name for fuzzy matching

        Returns:
            Raw result data if found, None if no normalized name or no match
        """
        if query_input.normalized_name:
            return await self._search_by_name(query_input.normalized_name, exact=False)
        return None

    async def handle_raw_input_strategy(self, query_input: QueryInput) -> Any | None:
        """Default raw input strategy implementation.

        Searches using the original raw input text with exact matching.

        Args:
            query_input: Query input with original raw text

        Returns:
            Raw result data if found, None if no raw input or no match
        """
        return await self._search_by_name(query_input.raw_input, exact=True)

    async def handle_aliases_strategy(self, query_input: QueryInput) -> Any | None:
        """Default aliases strategy implementation.

        Iterates through all aliases and returns the first match found.

        Args:
            query_input: Query input with journal aliases

        Returns:
            Raw result data if found, None if no aliases or no match
        """
        for alias in query_input.aliases:
            result = await self._search_by_name(alias, exact=True)
            if result is not None:
                return result
        return None

    async def handle_exact_aliases_strategy(
        self, query_input: QueryInput
    ) -> Any | None:
        """Default exact aliases strategy implementation.

        For most backends, this is the same as the aliases strategy.

        Args:
            query_input: Query input with journal aliases for exact matching

        Returns:
            Raw result data if found, None if no aliases or no match
        """
        return await self.handle_aliases_strategy(query_input)

    async def handle_acronyms_strategy(self, query_input: QueryInput) -> Any | None:
        """Default acronyms strategy implementation.

        Most backends don't have special acronym handling, so this returns None.
        Backends with acronym-specific logic should override this method.

        Args:
            query_input: Query input with potential acronyms

        Returns:
            None (no acronym support by default)
        """
        return None

    async def handle_substring_match_strategy(
        self, query_input: QueryInput
    ) -> Any | None:
        """Default substring matching strategy.

        Uses the backend's substring search if available, otherwise falls back
        to fuzzy name search.

        Args:
            query_input: Query input for substring matching

        Returns:
            Raw result data if found, None if no normalized name or no match
        """
        if query_input.normalized_name:
            if hasattr(self, "_search_by_substring"):
                return await self._search_by_substring(query_input.normalized_name)
            else:
                # Fallback to fuzzy search if no substring method
                return await self._search_by_name(
                    query_input.normalized_name, exact=False
                )
        return None

    async def handle_word_similarity_strategy(
        self, query_input: QueryInput
    ) -> Any | None:
        """Default word similarity strategy.

        Uses the backend's similarity search if available, otherwise falls back
        to fuzzy name search.

        Args:
            query_input: Query input for similarity matching

        Returns:
            Raw result data if found, None if no normalized name or no match
        """
        if query_input.normalized_name:
            if hasattr(self, "_search_by_similarity"):
                return await self._search_by_similarity(query_input.normalized_name)
            else:
                # Fallback to fuzzy search if no similarity method
                return await self._search_by_name(
                    query_input.normalized_name, exact=False
                )
        return None

    # Abstract methods that backends must implement
    async def _search_by_issn(self, issn: str) -> Any | None:
        """Search by ISSN/eISSN - must be implemented by backend.

        Args:
            issn: ISSN or eISSN identifier to search for

        Returns:
            Raw result data if found, None if no match

        Raises:
            NotImplementedError: If backend doesn't implement this method
        """
        raise NotImplementedError(
            f"Backend {self.__class__.__name__} must implement _search_by_issn"
        )

    async def _search_by_name(self, name: str, exact: bool = True) -> Any | None:
        """Search by name - must be implemented by backend.

        Args:
            name: Journal name to search for
            exact: Whether to use exact matching (True) or fuzzy matching (False)

        Returns:
            Raw result data if found, None if no match

        Raises:
            NotImplementedError: If backend doesn't implement this method
        """
        raise NotImplementedError(
            f"Backend {self.__class__.__name__} must implement _search_by_name"
        )

    async def _search_by_substring(self, name: str) -> Any | None:
        """Search by substring - can be overridden by backend.

        Default implementation falls back to fuzzy name search.

        Args:
            name: Name to search for substring matches

        Returns:
            Raw result data if found, None if no match
        """
        return await self._search_by_name(name, exact=False)

    async def _search_by_similarity(self, name: str) -> Any | None:
        """Search by similarity - can be overridden by backend.

        Default implementation falls back to fuzzy name search.

        Args:
            name: Name to search for similarity matches

        Returns:
            Raw result data if found, None if no match
        """
        return await self._search_by_name(name, exact=False)
