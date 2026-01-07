# SPDX-License-Identifier: MIT
"""Unit tests for the QueryFallbackChain and FallbackStrategy classes."""

from aletheia_probe.fallback_chain import (
    FallbackAttempt,
    FallbackStrategy,
    QueryFallbackChain,
)


class TestFallbackChain:
    """Tests for the QueryFallbackChain class."""

    def test_initialization(self):
        """Test that the chain is initialized with the correct strategies."""
        strategies = [
            FallbackStrategy.ISSN,
            FallbackStrategy.NORMALIZED_NAME,
            FallbackStrategy.ALIASES,
        ]
        chain = QueryFallbackChain(strategies)

        assert chain.strategies == strategies
        assert chain.get_attempts() == []
        assert not chain.has_attempts()
        assert not chain.was_successful()
        assert chain.get_successful_strategy() is None

    def test_log_attempt(self):
        """Test logging fallback attempts."""
        chain = QueryFallbackChain([FallbackStrategy.ISSN])

        # Log a failed attempt
        chain.log_attempt(
            strategy=FallbackStrategy.ISSN, success=False, query_value="1234-5678"
        )

        attempts = chain.get_attempts()
        assert len(attempts) == 1
        assert attempts[0].strategy == FallbackStrategy.ISSN
        assert attempts[0].success is False
        assert attempts[0].query_value == "1234-5678"
        assert attempts[0].match_confidence is None
        assert chain.has_attempts()

        # Log a successful attempt
        chain.log_attempt(
            strategy=FallbackStrategy.NORMALIZED_NAME,
            success=True,
            query_value="some journal",
            match_confidence=0.95,
        )

        attempts = chain.get_attempts()
        assert len(attempts) == 2
        assert attempts[1].strategy == FallbackStrategy.NORMALIZED_NAME
        assert attempts[1].success is True
        assert attempts[1].match_confidence == 0.95

    def test_successful_strategy_detection(self):
        """Test detection of the successful strategy."""
        chain = QueryFallbackChain(
            [FallbackStrategy.ISSN, FallbackStrategy.NORMALIZED_NAME]
        )

        # No attempts yet
        assert chain.get_successful_strategy() is None
        assert not chain.was_successful()

        # First attempt fails
        chain.log_attempt(FallbackStrategy.ISSN, False)
        assert chain.get_successful_strategy() is None
        assert not chain.was_successful()

        # Second attempt succeeds
        chain.log_attempt(FallbackStrategy.NORMALIZED_NAME, True)
        assert chain.get_successful_strategy() == FallbackStrategy.NORMALIZED_NAME
        assert chain.was_successful()

    def test_attempt_summary_formatting(self):
        """Test human-readable summary formatting."""
        chain = QueryFallbackChain([])

        # Case 1: No attempts
        assert chain.get_attempt_summary() == "no attempts"

        # Case 2: One failed attempt
        chain.log_attempt(FallbackStrategy.ISSN, False)
        assert chain.get_attempt_summary() == "issn(fail)"

        # Case 3: Mixed attempts with confidence
        chain.log_attempt(FallbackStrategy.NORMALIZED_NAME, True, match_confidence=0.85)
        expected = "issn(fail) → normalized_name(success, conf=0.85)"
        assert chain.get_attempt_summary() == expected

        # Case 4: Another attempt
        chain.log_attempt(FallbackStrategy.ALIASES, False)
        expected += " → aliases(fail)"
        assert chain.get_attempt_summary() == expected

    def test_edge_cases_multiple_successes(self):
        """Test behavior when multiple attempts are marked successful."""
        chain = QueryFallbackChain([FallbackStrategy.ISSN, FallbackStrategy.EISSN])

        # Although logical flow usually stops after success, the chain should record all.
        chain.log_attempt(FallbackStrategy.ISSN, True)
        chain.log_attempt(FallbackStrategy.EISSN, True)

        # Should return the first successful strategy
        assert chain.get_successful_strategy() == FallbackStrategy.ISSN
        assert chain.was_successful()

        summary = chain.get_attempt_summary()
        assert "issn(success)" in summary
        assert "eissn(success)" in summary

    def test_attempts_list_is_copy(self):
        """Test that get_attempts returns a copy, not the internal list."""
        chain = QueryFallbackChain([FallbackStrategy.ISSN])
        chain.log_attempt(FallbackStrategy.ISSN, False)

        attempts = chain.get_attempts()
        attempts.clear()

        assert len(chain.get_attempts()) == 1
