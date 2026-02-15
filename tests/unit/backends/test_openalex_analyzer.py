# SPDX-License-Identifier: MIT
"""Tests for OpenAlex analyzer backend."""

from aletheia_probe.backends.openalex_analyzer import OpenAlexAnalyzerBackend


class TestOpenAlexAnalyzerReasoning:
    """Tests for OpenAlex reasoning generation."""

    def test_generate_reasoning_skips_empty_indicator_headers(self):
        """Do not render indicator headers when flags are empty or blank."""
        backend = OpenAlexAnalyzerBackend()
        metrics = {"total_publications": 100, "years_active": 10, "citation_ratio": 2.5}

        reasoning = backend._generate_reasoning(
            red_flags=["", "   "],
            green_flags=["  "],
            metrics=metrics,
        )

        assert "Positive indicators:" not in reasoning
        assert "Warning signs:" not in reasoning
        assert "Mixed or insufficient signals for clear assessment" in reasoning
