# Backend Fallback Chain Standardization - Implementation Plan

## Problem Statement

Issue #233 implementation standardized infrastructure (exceptions, retries, confidence) but did not address the core concern: **inconsistent and unpredictable query fallback patterns** across backends.

**Current State:**
- Each backend implements fallback differently (ISSN→title, ISSN→eISSN, name→aliases)
- No visibility into which fallback strategy succeeded
- No structured logging of fallback attempts
- Difficult to debug why a query succeeded or failed
- No consistent pattern for developers to follow

**Goal:**
Replace all existing fallback implementations with a unified **QueryFallbackChain** abstraction that:
1. Documents each backend's fallback sequence explicitly
2. Logs all fallback attempts for debugging
3. Reports which strategy succeeded
4. Maintains API-specific flexibility while enforcing consistent structure

## Solution Approach

**Philosophy:** Complete replacement, breaking changes allowed, no backward compatibility.

**Replace** all existing fallback logic with a standardized QueryFallbackChain abstraction. Every backend MUST use this new system. All current ad-hoc fallback implementations will be removed and rewritten using the new infrastructure.

## Implementation Phases

### Phase 1: Core Fallback Chain Infrastructure

**Create:** `src/aletheia_probe/fallback_chain.py`

Define the fallback chain abstraction:

```python
from enum import Enum
from typing import Optional
from dataclasses import dataclass


class FallbackStrategy(Enum):
    """Standard fallback strategies used across backends."""

    ISSN = "issn"
    EISSN = "eissn"
    EXACT_NAME = "exact_name"
    NORMALIZED_NAME = "normalized_name"
    FUZZY_NAME = "fuzzy_name"
    RAW_INPUT = "raw_input"
    ALIASES = "aliases"
    EXACT_ALIASES = "exact_aliases"
    ACRONYMS = "acronyms"
    SUBSTRING_MATCH = "substring_match"
    WORD_SIMILARITY = "word_similarity"


@dataclass
class FallbackAttempt:
    """Single fallback attempt record."""

    strategy: FallbackStrategy
    success: bool
    query_value: Optional[str] = None
    match_confidence: Optional[float] = None


class QueryFallbackChain:
    """Documents and tracks query fallback attempts.

    This is the ONLY way backends should implement fallback logic.
    All backends MUST use this class to track their query attempts.

    Usage:
        chain = QueryFallbackChain([
            FallbackStrategy.ISSN,
            FallbackStrategy.NORMALIZED_NAME,
            FallbackStrategy.ALIASES
        ])

        # During query execution
        chain.log_attempt(FallbackStrategy.ISSN, False)
        chain.log_attempt(FallbackStrategy.NORMALIZED_NAME, True, confidence=0.85)

        # After query
        successful = chain.get_successful_strategy()
        all_attempts = chain.get_attempts()
    """

    def __init__(self, strategies: list[FallbackStrategy]):
        """Initialize fallback chain with ordered strategies.

        Args:
            strategies: Ordered list of fallback strategies this backend will try
        """
        self.strategies = strategies
        self._attempts: list[FallbackAttempt] = []

    def log_attempt(
        self,
        strategy: FallbackStrategy,
        success: bool,
        query_value: Optional[str] = None,
        match_confidence: Optional[float] = None,
    ) -> None:
        """Record a fallback attempt.

        Args:
            strategy: Which strategy was attempted
            success: Whether the strategy found a match
            query_value: Optional query value used (for debugging)
            match_confidence: Optional confidence score if match found
        """
        attempt = FallbackAttempt(strategy, success, query_value, match_confidence)
        self._attempts.append(attempt)

    def get_successful_strategy(self) -> Optional[FallbackStrategy]:
        """Return the strategy that succeeded, if any."""
        for attempt in self._attempts:
            if attempt.success:
                return attempt.strategy
        return None

    def get_attempts(self) -> list[FallbackAttempt]:
        """Return all logged attempts."""
        return self._attempts.copy()

    def get_attempt_summary(self) -> str:
        """Return human-readable summary of attempts.

        Returns:
            String like "ISSN(fail) → NORMALIZED_NAME(success, conf=0.85)"
        """
        parts = []
        for attempt in self._attempts:
            status = "success" if attempt.success else "fail"
            if attempt.match_confidence is not None:
                status = f"{status}, conf={attempt.match_confidence:.2f}"
            parts.append(f"{attempt.strategy.value}({status})")
        return " → ".join(parts) if parts else "no attempts"

    def has_attempts(self) -> bool:
        """Check if any attempts were logged."""
        return len(self._attempts) > 0

    def was_successful(self) -> bool:
        """Check if any attempt succeeded."""
        return self.get_successful_strategy() is not None
```

**Testing:** Create `tests/unit/test_fallback_chain.py`
- Test chain initialization
- Test attempt logging
- Test successful strategy detection
- Test attempt summary formatting
- Test edge cases (no attempts, multiple successes)

**Estimated effort:** 1 day

---

### Phase 2: Integrate with BackendResult (BREAKING CHANGE)

**Modify:** `src/aletheia_probe/backends/models.py`

Add fallback chain information to BackendResult (required field):

```python
from aletheia_probe.fallback_chain import QueryFallbackChain, FallbackStrategy

@dataclass
class BackendResult:
    """Result from a backend query."""

    # ... existing fields ...

    # NEW REQUIRED FIELDS
    fallback_chain: QueryFallbackChain  # No longer optional
    successful_strategy: Optional[FallbackStrategy] = None

    def __post_init__(self):
        """Extract successful strategy from chain."""
        if self.fallback_chain:
            self.successful_strategy = self.fallback_chain.get_successful_strategy()
```

**BREAKING CHANGE:** All BackendResult constructors must now include a fallback_chain.

**Testing:** Update `tests/unit/backends/test_result.py`
- Test BackendResult requires fallback_chain
- Test successful_strategy auto-populated
- Update all existing tests to provide fallback_chain

**Estimated effort:** 0.5 days

---

### Phase 3: Replace Base Backend Implementation (BREAKING CHANGE)

**Modify:** `src/aletheia_probe/backends/base.py`

**REMOVE** all existing fallback logic, **REPLACE** with fallback chain methods:

```python
from aletheia_probe.fallback_chain import QueryFallbackChain, FallbackStrategy
from abc import ABC, abstractmethod

class Backend(ABC):
    """Base class for all backends."""

    @abstractmethod
    def _get_fallback_strategies(self) -> list[FallbackStrategy]:
        """Define backend's fallback sequence.

        MUST be implemented by all subclasses.

        Returns:
            Ordered list of fallback strategies
        """
        pass


class ApiBackendWithCache(Backend, ABC):
    """Base class for backends with API calls and caching."""

    def _create_fallback_chain(self) -> QueryFallbackChain:
        """Create fallback chain for this backend.

        DO NOT override this method. Override _get_fallback_strategies() instead.

        Returns:
            QueryFallbackChain with backend-specific strategies
        """
        strategies = self._get_fallback_strategies()
        return QueryFallbackChain(strategies)

    def _log_fallback_attempt(
        self,
        chain: QueryFallbackChain,
        strategy: FallbackStrategy,
        success: bool,
        query_value: Optional[str] = None,
        confidence: Optional[float] = None,
    ) -> None:
        """Log a fallback attempt with sync logging.

        Args:
            chain: The fallback chain being used
            strategy: Strategy being attempted
            success: Whether it succeeded
            query_value: Optional query value for debugging
            confidence: Optional confidence if successful
        """
        chain.log_attempt(strategy, success, query_value, confidence)

        # Sync logger for debugging
        status = "succeeded" if success else "failed"
        msg = f"Fallback {strategy.value}: {status}"
        if query_value:
            msg += f" (query: {query_value[:50]})"
        if confidence is not None:
            msg += f" (confidence: {confidence:.2f})"

        self.sync_logger.debug(msg)


class CachedBackend(Backend, ABC):
    """Base class for cached backends.

    All cached backends use the same fallback sequence.
    """

    def _get_fallback_strategies(self) -> list[FallbackStrategy]:
        """Standard cached backend fallback: ISSN → EXACT_NAME → EXACT_ALIASES."""
        return [
            FallbackStrategy.ISSN,
            FallbackStrategy.EXACT_NAME,
            FallbackStrategy.EXACT_ALIASES
        ]

    def _create_fallback_chain(self) -> QueryFallbackChain:
        """Create fallback chain for cached backend."""
        strategies = self._get_fallback_strategies()
        return QueryFallbackChain(strategies)

    def _log_fallback_attempt(
        self,
        chain: QueryFallbackChain,
        strategy: FallbackStrategy,
        success: bool,
        query_value: Optional[str] = None,
        confidence: Optional[float] = None,
    ) -> None:
        """Log fallback attempt for cached backend."""
        chain.log_attempt(strategy, success, query_value, confidence)

        status = "succeeded" if success else "failed"
        self.sync_logger.debug(f"Fallback {strategy.value}: {status}")

    # REMOVE: All existing _search_by_issn, _search_exact_match logic
    # REPLACE: With new fallback-chain-driven implementation

    async def assess(
        self,
        query_input: BackendQueryInput,
        assessment_cache: AssessmentCache,
    ) -> BackendResult:
        """Standard cached backend assessment with fallback chain.

        All cached backends now use this implementation.
        DO NOT override unless you have a specific reason.
        """
        chain = self._create_fallback_chain()

        # ISSN fallback
        if issn := query_input.identifiers.get("issn"):
            results = self._search_by_issn(issn)
            issn_success = len(results) > 0
            self._log_fallback_attempt(
                chain, FallbackStrategy.ISSN, issn_success, issn
            )

            if issn_success:
                return self._build_result_from_cache(
                    results[0], fallback_chain=chain
                )

        # Exact name fallback
        if query_input.normalized_name:
            results = self._search_exact_match(query_input.normalized_name)
            name_success = len(results) > 0
            self._log_fallback_attempt(
                chain,
                FallbackStrategy.EXACT_NAME,
                name_success,
                query_input.normalized_name
            )

            if name_success:
                return self._build_result_from_cache(
                    results[0], fallback_chain=chain
                )

        # Exact alias fallback
        for alias in query_input.aliases:
            results = self._search_exact_match(alias)
            alias_success = len(results) > 0
            self._log_fallback_attempt(
                chain, FallbackStrategy.EXACT_ALIASES, alias_success, alias
            )

            if alias_success:
                return self._build_result_from_cache(
                    results[0], fallback_chain=chain
                )

        # Not found
        return BackendResult(
            status=BackendStatus.NOT_FOUND,
            confidence=0.0,
            fallback_chain=chain,
        )

    @abstractmethod
    def _build_result_from_cache(
        self, cache_entry: dict, fallback_chain: QueryFallbackChain
    ) -> BackendResult:
        """Build result from cache entry with fallback chain.

        Subclasses must implement this to construct their specific result.
        """
        pass
```

**BREAKING CHANGES:**
- All backends must implement `_get_fallback_strategies()`
- All backends must use fallback chain in their assess() methods
- CachedBackend provides standard implementation
- All custom fallback logic must be removed

**Testing:** Rewrite `tests/unit/backends/test_base.py`
- Test _get_fallback_strategies() must be implemented
- Test standard CachedBackend fallback flow
- Test _log_fallback_attempt() logging

**Estimated effort:** 1 day

---

### Phase 4: Rewrite DOAJ Backend (BREAKING CHANGE)

**Modify:** `src/aletheia_probe/backends/doaj.py`

**REMOVE** all existing fallback logic, **REPLACE** with fallback chain:

```python
from aletheia_probe.fallback_chain import FallbackStrategy

class DOAJBackend(ApiBackendWithCache):
    """DOAJ backend using standardized fallback chain."""

    def _get_fallback_strategies(self) -> list[FallbackStrategy]:
        """DOAJ fallback: ISSN → normalized title → fuzzy → aliases."""
        return [
            FallbackStrategy.ISSN,
            FallbackStrategy.NORMALIZED_NAME,
            FallbackStrategy.FUZZY_NAME,
            FallbackStrategy.ALIASES
        ]

    async def _query_api(
        self,
        query_input: BackendQueryInput,
        assessment_cache: AssessmentCache,
    ) -> BackendResult:
        """Query DOAJ API using standardized fallback chain."""

        chain = self._create_fallback_chain()

        # ISSN fallback
        if issn := query_input.identifiers.get("issn"):
            response = await self._fetch_journals([f"issn:{issn}"])
            issn_success = response and len(response.get("results", [])) > 0
            self._log_fallback_attempt(
                chain, FallbackStrategy.ISSN, issn_success, issn
            )

            if issn_success:
                result = await self._process_doaj_results(
                    response, query_input, assessment_cache
                )
                result.fallback_chain = chain
                return result

        # Normalized name fallback
        if query_input.normalized_name:
            title_query = f'title:"{query_input.normalized_name}"'
            response = await self._fetch_journals([title_query])
            title_success = response and len(response.get("results", [])) > 0
            self._log_fallback_attempt(
                chain,
                FallbackStrategy.NORMALIZED_NAME,
                title_success,
                query_input.normalized_name
            )

            if title_success:
                result = await self._process_doaj_results(
                    response, query_input, assessment_cache
                )
                result.fallback_chain = chain
                return result

        # Fuzzy matching fallback (if confidence from normalized was too low)
        # ... implement fuzzy logic with FallbackStrategy.FUZZY_NAME

        # Alias fallback
        for alias in query_input.aliases:
            alias_query = f'title:"{alias}"'
            response = await self._fetch_journals([alias_query])
            alias_success = response and len(response.get("results", [])) > 0
            self._log_fallback_attempt(
                chain, FallbackStrategy.ALIASES, alias_success, alias
            )

            if alias_success:
                result = await self._process_doaj_results(
                    response, query_input, assessment_cache
                )
                result.fallback_chain = chain
                return result

        # Not found
        return BackendResult(
            status=BackendStatus.NOT_FOUND,
            confidence=0.0,
            response_time_ms=0,
            fallback_chain=chain,
        )
```

**BREAKING CHANGES:**
- Removes all ad-hoc fallback logic
- All query attempts must go through fallback chain
- BackendResult must include fallback_chain

**Testing:** Rewrite `tests/unit/backends/test_doaj.py`
- Test fallback chain strategies defined correctly
- Test ISSN fallback
- Test title fallback
- Test alias fallback
- Test chain attached to all results

**Estimated effort:** 1.5 days

---

### Phase 5: Rewrite Crossref Analyzer (BREAKING CHANGE)

**Modify:** `src/aletheia_probe/backends/crossref_analyzer.py`

**REMOVE** existing fallback logic, **REPLACE** with fallback chain:

```python
class CrossrefAnalyzer(ApiBackendWithCache):
    """Crossref analyzer using standardized fallback chain."""

    def _get_fallback_strategies(self) -> list[FallbackStrategy]:
        """Crossref: ISSN → eISSN (API limitation: no title search)."""
        return [
            FallbackStrategy.ISSN,
            FallbackStrategy.EISSN
        ]

    async def _query_api(
        self,
        query_input: BackendQueryInput,
        assessment_cache: AssessmentCache,
    ) -> BackendResult:
        """Query Crossref using standardized fallback chain."""

        chain = self._create_fallback_chain()

        # ISSN fallback
        if issn := query_input.identifiers.get("issn"):
            journal = await self._fetch_journal(issn)
            issn_success = journal is not None
            self._log_fallback_attempt(
                chain, FallbackStrategy.ISSN, issn_success, issn
            )

            if issn_success:
                result = await self._analyze_journal(
                    journal, query_input, assessment_cache
                )
                result.fallback_chain = chain
                return result

        # eISSN fallback
        if eissn := query_input.identifiers.get("eissn"):
            journal = await self._fetch_journal(eissn)
            eissn_success = journal is not None
            self._log_fallback_attempt(
                chain, FallbackStrategy.EISSN, eissn_success, eissn
            )

            if eissn_success:
                result = await self._analyze_journal(
                    journal, query_input, assessment_cache
                )
                result.fallback_chain = chain
                return result

        # Not found
        return BackendResult(
            status=BackendStatus.NOT_FOUND,
            confidence=0.0,
            response_time_ms=0,
            fallback_chain=chain,
        )
```

**BREAKING CHANGES:**
- Removes all existing ISSN/eISSN fallback code
- Enforces fallback chain pattern

**Testing:** Rewrite `tests/unit/backends/test_crossref_analyzer.py`
- Test ISSN → eISSN fallback sequence
- Test chain shows no title attempts
- Test all results include fallback_chain

**Estimated effort:** 1 day

---

### Phase 6: Rewrite OpenAlex Analyzer (BREAKING CHANGE)

**Modify:** `src/aletheia_probe/backends/openalex_analyzer.py`

**REMOVE** _search_with_aliases() method, **REPLACE** with fallback chain:

```python
class OpenAlexAnalyzer(ApiBackendWithCache):
    """OpenAlex analyzer using standardized fallback chain."""

    def _get_fallback_strategies(self) -> list[FallbackStrategy]:
        """OpenAlex: name+ISSN → aliases → acronyms."""
        return [
            FallbackStrategy.NORMALIZED_NAME,
            FallbackStrategy.ISSN,
            FallbackStrategy.ALIASES,
            FallbackStrategy.ACRONYMS
        ]

    async def _query_api(
        self,
        query_input: BackendQueryInput,
        assessment_cache: AssessmentCache,
    ) -> BackendResult:
        """Query OpenAlex using standardized fallback chain."""

        chain = self._create_fallback_chain()

        # Primary: name + ISSN
        journal_name = query_input.normalized_name or query_input.raw_input
        issn = query_input.identifiers.get("issn")
        eissn = query_input.identifiers.get("eissn")

        openalex_data = await self.client.enrich_journal_data(
            journal_name=journal_name, issn=issn, eissn=eissn
        )

        primary_success = openalex_data is not None
        self._log_fallback_attempt(
            chain,
            FallbackStrategy.NORMALIZED_NAME,
            primary_success,
            journal_name
        )

        if openalex_data:
            result = await self._analyze_openalex_data(
                openalex_data, query_input, assessment_cache
            )
            result.fallback_chain = chain
            return result

        # Alias fallback
        for alias in query_input.aliases:
            openalex_data = await self.client.enrich_journal_data(
                journal_name=alias, issn=issn, eissn=eissn
            )

            alias_success = openalex_data is not None
            self._log_fallback_attempt(
                chain, FallbackStrategy.ALIASES, alias_success, alias
            )

            if openalex_data:
                result = await self._analyze_openalex_data(
                    openalex_data, query_input, assessment_cache
                )
                result.fallback_chain = chain
                return result

        # Not found
        return BackendResult(
            status=BackendStatus.NOT_FOUND,
            confidence=0.0,
            response_time_ms=0,
            fallback_chain=chain,
        )
```

**BREAKING CHANGES:**
- Removes _search_with_aliases() method
- Integrates alias fallback directly into _query_api() with chain
- All results must include fallback_chain

**Testing:** Rewrite `tests/unit/backends/test_openalex_analyzer.py`
- Test name → alias fallback sequence
- Test multiple alias attempts logged
- Test all results include chain

**Estimated effort:** 1 day

---

### Phase 7: Rewrite Retraction Watch (BREAKING CHANGE)

**Modify:** `src/aletheia_probe/backends/retraction_watch.py`

**REMOVE** existing fallback logic, **REPLACE** with fallback chain:

```python
class RetractionWatchBackend(ApiBackendWithCache, DataSyncCapable):
    """Retraction Watch using standardized fallback chain."""

    def _get_fallback_strategies(self) -> list[FallbackStrategy]:
        """Retraction Watch: ISSN → exact name → exact aliases."""
        return [
            FallbackStrategy.ISSN,
            FallbackStrategy.EXACT_NAME,
            FallbackStrategy.EXACT_ALIASES
        ]

    async def _query_api(
        self,
        query_input: BackendQueryInput,
        assessment_cache: AssessmentCache,
    ) -> BackendResult:
        """Query Retraction Watch using standardized fallback chain."""

        chain = self._create_fallback_chain()

        # ISSN fallback
        if issn := query_input.identifiers.get("issn"):
            journals = await self._search_journals(issn=issn)
            issn_success = len(journals) > 0
            self._log_fallback_attempt(
                chain, FallbackStrategy.ISSN, issn_success, issn
            )

            if issn_success:
                result = await self._process_retraction_data(
                    journals[0], query_input, assessment_cache
                )
                result.fallback_chain = chain
                return result

        # Exact name fallback
        if query_input.normalized_name:
            journals = await self._search_exact_match(
                query_input.normalized_name
            )
            name_success = len(journals) > 0
            self._log_fallback_attempt(
                chain,
                FallbackStrategy.EXACT_NAME,
                name_success,
                query_input.normalized_name
            )

            if name_success:
                result = await self._process_retraction_data(
                    journals[0], query_input, assessment_cache
                )
                result.fallback_chain = chain
                return result

        # Exact alias fallback
        for alias in query_input.aliases:
            journals = await self._search_exact_match(alias)
            alias_success = len(journals) > 0
            self._log_fallback_attempt(
                chain, FallbackStrategy.EXACT_ALIASES, alias_success, alias
            )

            if alias_success:
                result = await self._process_retraction_data(
                    journals[0], query_input, assessment_cache
                )
                result.fallback_chain = chain
                return result

        # Not found
        return BackendResult(
            status=BackendStatus.NOT_FOUND,
            confidence=0.0,
            response_time_ms=0,
            fallback_chain=chain,
        )
```

**BREAKING CHANGES:**
- Removes all existing fallback logic
- Enforces fallback chain pattern
- All results must include fallback_chain

**Testing:** Rewrite `tests/unit/backends/test_retraction_watch.py`
- Test ISSN → exact name → exact alias sequence
- Test strict exact matching preserved
- Test all results include chain

**Estimated effort:** 1 day

---

### Phase 8: Rewrite All Cached Backends (BREAKING CHANGE)

**Modify:** All 8 cached backends:
- `bealls.py`
- `predatoryjournals.py`
- `scopus.py`
- `algerian_ministry.py`
- `kscien_hijacked_journals.py`
- `kscien_publishers.py`
- `kscien_standalone_journals.py`
- `kscien_predatory_conferences.py`

**REMOVE** all custom assess() implementations. These backends now inherit the standard CachedBackend.assess() method.

**Only implement:** `_build_result_from_cache()`

```python
class BeallsListBackend(CachedBackend):
    """Beall's List using standardized fallback chain."""

    # REMOVE: assess() method - now inherited from CachedBackend

    def _build_result_from_cache(
        self, cache_entry: dict, fallback_chain: QueryFallbackChain
    ) -> BackendResult:
        """Build result from Beall's List cache entry."""
        return BackendResult(
            status=BackendStatus.FOUND,
            confidence=CONFIDENCE_HIGH,
            assessment=Assessment.PREDATORY,
            fallback_chain=fallback_chain,
            details={"source": "Beall's List", "entry": cache_entry},
        )
```

**BREAKING CHANGES:**
- All cached backends lose custom assess() implementations
- All use standard CachedBackend.assess() with fallback chain
- Must implement _build_result_from_cache()

**Pattern:** Apply this to all 8 cached backends. They are nearly identical.

**Testing:** Rewrite tests for all 8 backends
- Test standard fallback sequence (ISSN → EXACT_NAME → EXACT_ALIASES)
- Test _build_result_from_cache() called correctly
- Test all results include fallback_chain

**Estimated effort:** 2 days

---

### Phase 9: Enhance Sync Logging with Fallback Chain

**Modify:** `src/aletheia_probe/sync.py`

Add fallback chain reporting to sync operations:

```python
async def _sync_backend(
    self,
    backend: Backend,
    journals: list[Journal],
) -> dict:
    """Sync backend with fallback chain reporting."""

    # ... existing sync logic ...

    for journal in journals:
        result = await backend.assess(query_input, assessment_cache)

        # Log fallback chain summary (now required on all results)
        summary = result.fallback_chain.get_attempt_summary()
        self.sync_logger.info(
            f"{backend.name} [{journal.normalized_name}]: {summary}"
        )

        # If found, emphasize which strategy worked
        if result.successful_strategy:
            self.sync_logger.info(
                f"  → Found via {result.successful_strategy.value}"
            )

    # ... continue with existing logic ...
```

**BREAKING CHANGES:**
- Assumes all BackendResult objects have fallback_chain (now required)
- No null checks needed

**Testing:** Enhance `tests/integration/test_sync.py`
- Test sync logs contain fallback summaries
- Test successful strategy logged
- Test all backends report fallback chains

**Estimated effort:** 0.5 days

---

### Phase 10: Documentation and Standards

**Create/Update:**

1. **`dev-notes/FALLBACK_PATTERNS.md`** - New documentation:
   ```markdown
   # Backend Fallback Patterns

   ## Overview
   All backends MUST use the QueryFallbackChain abstraction for fallback logic.
   Custom fallback implementations are NOT allowed.

   ## Standard Fallback Strategies
   - FallbackStrategy.ISSN: Query by ISSN
   - FallbackStrategy.EISSN: Query by eISSN
   - FallbackStrategy.EXACT_NAME: Exact name match
   - FallbackStrategy.NORMALIZED_NAME: Normalized name match
   - FallbackStrategy.FUZZY_NAME: Fuzzy/similarity name match
   - FallbackStrategy.ALIASES: Alias matching
   - FallbackStrategy.EXACT_ALIASES: Exact alias matching
   - FallbackStrategy.ACRONYMS: Acronym expansion

   ## Backend-Specific Chains

   ### DOAJ
   ```python
   [ISSN, NORMALIZED_NAME, FUZZY_NAME, ALIASES]
   ```
   Tries ISSN first, falls back to title matching with graduated confidence.

   ### Crossref
   ```python
   [ISSN, EISSN]
   ```
   ISSN-only (API limitation: no title search endpoint).

   ### OpenAlex
   ```python
   [NORMALIZED_NAME, ISSN, ALIASES, ACRONYMS]
   ```
   Uses OpenAlex API's internal matching.

   ### Retraction Watch
   ```python
   [ISSN, EXACT_NAME, EXACT_ALIASES]
   ```
   Strict exact matching only.

   ### All Cached Backends
   ```python
   [ISSN, EXACT_NAME, EXACT_ALIASES]
   ```
   Standard cached backend fallback sequence.

   ## Implementation Requirements

   All backends MUST:
   1. Implement `_get_fallback_strategies()` to define their sequence
   2. Create fallback chain at start of assess/query
   3. Log every fallback attempt
   4. Attach fallback chain to BackendResult
   5. Use FallbackStrategy enum (not custom strings)

   ## Example Implementation

   ```python
   class MyBackend(ApiBackendWithCache):
       def _get_fallback_strategies(self) -> list[FallbackStrategy]:
           return [
               FallbackStrategy.ISSN,
               FallbackStrategy.NORMALIZED_NAME,
               FallbackStrategy.ALIASES
           ]

       async def _query_api(self, query_input, cache) -> BackendResult:
           chain = self._create_fallback_chain()

           # Try ISSN
           if issn := query_input.identifiers.get("issn"):
               result = self._try_issn_lookup(issn)
               self._log_fallback_attempt(
                   chain, FallbackStrategy.ISSN, result is not None, issn
               )
               if result:
                   result.fallback_chain = chain
                   return result

           # Continue with other strategies...

           return BackendResult(
               status=BackendStatus.NOT_FOUND,
               confidence=0.0,
               fallback_chain=chain
           )
   ```
   ```

2. **Update `dev-notes/CODING_STANDARDS.md`:**
   ```markdown
   ## Fallback Chain Usage (MANDATORY)

   All backends MUST use the QueryFallbackChain abstraction for fallback logic.

   **Required steps:**
   1. Implement `_get_fallback_strategies()` returning list[FallbackStrategy]
   2. Call `self._create_fallback_chain()` at start of assess/query
   3. Use `self._log_fallback_attempt()` for every attempt
   4. Attach fallback_chain to BackendResult before returning

   **Forbidden:**
   - Custom fallback logic outside of fallback chain
   - Not logging fallback attempts
   - Returning BackendResult without fallback_chain
   - Using custom strategy strings instead of FallbackStrategy enum
   ```

3. **Update `README.md`:**
   - Mention structured fallback tracking
   - Link to FALLBACK_PATTERNS.md

**Estimated effort:** 1 day

---

## Implementation Order

1. **Phase 1**: Core fallback chain infrastructure (1 day)
2. **Phase 2**: Integrate with BackendResult - BREAKING (0.5 days)
3. **Phase 3**: Replace base backend implementation - BREAKING (1 day)
4. **Phase 4**: Rewrite DOAJ backend - BREAKING (1.5 days)
5. **Phase 5**: Rewrite Crossref Analyzer - BREAKING (1 day)
6. **Phase 6**: Rewrite OpenAlex Analyzer - BREAKING (1 day)
7. **Phase 7**: Rewrite Retraction Watch - BREAKING (1 day)
8. **Phase 8**: Rewrite all cached backends - BREAKING (2 days)
9. **Phase 9**: Enhance sync logging (0.5 days)
10. **Phase 10**: Documentation and standards (1 day)

**Total Estimated Time:** 10.5 days (~2 weeks)

---

## Critical Files

### To Create
- `src/aletheia_probe/fallback_chain.py` (new infrastructure)
- `tests/unit/test_fallback_chain.py` (tests)
- `dev-notes/FALLBACK_PATTERNS.md` (documentation)

### To Modify (BREAKING CHANGES)
- `src/aletheia_probe/backends/result.py` (require fallback_chain)
- `src/aletheia_probe/backends/base.py` (replace fallback logic)
- `src/aletheia_probe/backends/doaj.py` (rewrite)
- `src/aletheia_probe/backends/crossref_analyzer.py` (rewrite)
- `src/aletheia_probe/backends/openalex_analyzer.py` (rewrite)
- `src/aletheia_probe/backends/retraction_watch.py` (rewrite)
- `src/aletheia_probe/backends/bealls.py` (rewrite)
- `src/aletheia_probe/backends/predatoryjournals.py` (rewrite)
- `src/aletheia_probe/backends/scopus.py` (rewrite)
- `src/aletheia_probe/backends/algerian_ministry.py` (rewrite)
- `src/aletheia_probe/backends/kscien_*.py` (4 backends, rewrite)
- `src/aletheia_probe/sync.py` (update logging)
- `dev-notes/CODING_STANDARDS.md` (enforce fallback chain)

### To Update (Tests)
- All backend test files must be updated for new fallback chain requirement

---

## Key Principles

✅ **DO:**
- **REPLACE** all existing fallback logic with QueryFallbackChain
- **REMOVE** all ad-hoc fallback implementations
- **ENFORCE** fallback chain in all backends (no exceptions)
- Log every fallback attempt without exception
- Use FallbackStrategy enum for type safety
- Make fallback_chain required field in BackendResult
- Update ALL tests for new structure
- Document all backend fallback sequences

❌ **DON'T:**
- Maintain any backward compatibility
- Allow any backend to skip fallback chain
- Leave any custom fallback logic in place
- Make fallback_chain optional
- Allow backends to return results without fallback chain

---

## Success Criteria

1. ✅ **ALL** backends use QueryFallbackChain (no exceptions)
2. ✅ **ALL** existing fallback logic removed
3. ✅ **ALL** backends implement _get_fallback_strategies()
4. ✅ **ALL** BackendResult objects include fallback_chain (required)
5. ✅ **ALL** fallback attempts logged to sync logger
6. ✅ **ALL** backends document their fallback sequence
7. ✅ **ALL** tests updated for new structure
8. ✅ Documentation enforces fallback chain usage
9. ✅ No query behavior changes (same success rates)
10. ✅ Sync logs show fallback progression for all queries

---

## Breaking Changes Summary

### For Backend Implementors
- Must implement `_get_fallback_strategies()`
- Must use fallback chain in all query methods
- Cannot use custom fallback logic
- Must attach fallback_chain to all results

### For Backend Users
- BackendResult now requires fallback_chain field
- No null checks needed (field is required)
- Can always access successful_strategy

### For Tests
- All tests must provide fallback_chain when constructing BackendResult
- All backend tests must verify fallback chain behavior

---

## Benefits

### Consistency
- **One pattern** for all backends (no exceptions)
- **Predictable** fallback behavior across all sources
- **Standard** logging format for all fallback attempts

### Debugging
- **Clear visibility** into every fallback attempt
- **Easy troubleshooting** when queries fail
- **Audit trail** for all query strategies

### Maintenance
- **Simple to understand** (one pattern to learn)
- **Easy to extend** (add new strategies to enum)
- **Type-safe** (enum prevents typos)
- **Enforced** (required by base class)

### For Users
- **Transparent** search behavior
- **Confidence** in thoroughness
- **Visibility** into why results were or weren't found

---

## Trade-offs

**Pros:**
- ✅ Complete standardization across all backends
- ✅ Excellent debugging and visibility
- ✅ Type-safe, enforceable pattern
- ✅ Clear documentation of all fallback sequences
- ✅ No hidden or inconsistent fallback logic

**Cons:**
- ⚠️ Breaking changes require updating all code
- ⚠️ All backends must be migrated simultaneously
- ⚠️ Minor performance overhead (fallback tracking)
- ⚠️ More rigid structure (less flexibility)

**Accepted:**
- Breaking changes are acceptable for this project
- Complete rewrite is better than partial migration
- Performance overhead is negligible
- Standardization outweighs flexibility concerns
