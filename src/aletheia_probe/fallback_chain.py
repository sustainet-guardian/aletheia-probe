# SPDX-License-Identifier: MIT
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


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


class FallbackAttempt(BaseModel):
    """Single fallback attempt record."""

    strategy: FallbackStrategy
    success: bool
    query_value: str | None = None
    match_confidence: float | None = None


class QueryFallbackChain(BaseModel):
    """Documents and tracks query fallback attempts.

    This is the ONLY way backends should implement fallback logic.
    All backends MUST use this class to track their query attempts.

    Usage:
        chain = QueryFallbackChain(strategies=[
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

    strategies: list[FallbackStrategy]
    attempts: list[FallbackAttempt] = Field(default_factory=list)

    def __init__(self, strategies: list[FallbackStrategy] | None = None, **kwargs: Any):
        """Initialize with optional positional strategies argument."""
        if strategies is not None:
            kwargs["strategies"] = strategies
        super().__init__(**kwargs)

    def log_attempt(
        self,
        strategy: FallbackStrategy,
        success: bool,
        query_value: str | None = None,
        match_confidence: float | None = None,
    ) -> None:
        """Record a fallback attempt.

        Args:
            strategy: Which strategy was attempted
            success: Whether the strategy found a match
            query_value: Optional query value used (for debugging)
            match_confidence: Optional confidence score if match found
        """
        attempt = FallbackAttempt(
            strategy=strategy,
            success=success,
            query_value=query_value,
            match_confidence=match_confidence,
        )
        self.attempts.append(attempt)

    def get_successful_strategy(self) -> FallbackStrategy | None:
        """Return the strategy that succeeded, if any."""
        for attempt in self.attempts:
            if attempt.success:
                return attempt.strategy
        return None

    def get_attempts(self) -> list[FallbackAttempt]:
        """Return all logged attempts."""
        return self.attempts.copy()

    def get_attempt_summary(self) -> str:
        """Return human-readable summary of attempts.

        Returns:
            String like "ISSN(fail) → NORMALIZED_NAME(success, conf=0.85)"
        """
        parts = []
        for attempt in self.attempts:
            status = "success" if attempt.success else "fail"
            if attempt.match_confidence is not None:
                status = f"{status}, conf={attempt.match_confidence:.2f}"
            parts.append(f"{attempt.strategy.value}({status})")
        return " → ".join(parts) if parts else "no attempts"

    def has_attempts(self) -> bool:
        """Check if any attempts were logged."""
        return len(self.attempts) > 0

    def was_successful(self) -> bool:
        """Check if any attempt succeeded."""
        return self.get_successful_strategy() is not None
