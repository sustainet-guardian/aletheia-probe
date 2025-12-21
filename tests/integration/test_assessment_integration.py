# SPDX-License-Identifier: MIT
"""Integration tests for end-to-end journal assessment workflows.

INTEGRATION TEST FILE: This file contains integration tests that verify
component interactions and end-to-end workflows. These are NOT predictable
unit tests - they may make real external API calls and use fuzzy assertions.

See README.md in this directory for details on integration test characteristics
and how to interpret test failures.

These tests validate complete assessment flows and component integration.
Tests that make real external API calls are marked as 'slow' and 'requires_network'.
Other tests focus on component interaction without external dependencies.
"""

import asyncio

import pytest

from aletheia_probe.dispatcher import QueryDispatcher
from aletheia_probe.enums import AssessmentType
from aletheia_probe.models import QueryInput
from aletheia_probe.normalizer import InputNormalizer


class TestAssessmentIntegration:
    """Integration tests for complete assessment workflows."""

    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.requires_network
    async def test_assess_well_known_legitimate_journal(self) -> None:
        """Test complete assessment of Nature journal (well-known legitimate).

        This test validates the entire assessment pipeline with a journal
        that should be found in multiple backend sources and classified
        as legitimate with high confidence.
        """
        dispatcher = QueryDispatcher()
        normalizer = InputNormalizer()

        # Normalize the input
        query = normalizer.normalize("Nature")

        # Perform assessment
        result = await dispatcher.assess_journal(query)

        # Assertions
        assert result is not None, "Assessment should return a result"
        assert result.assessment in [
            AssessmentType.LEGITIMATE,
            AssessmentType.UNKNOWN,
        ], f"Nature should be legitimate or unknown, got: {result.assessment}"

        # If found, confidence should be reasonable
        if result.assessment == AssessmentType.LEGITIMATE:
            assert result.confidence > 0.5, (
                f"Confidence should be > 0.5, got: {result.confidence}"
            )

        # Should have some backend results
        assert len(result.backend_results) > 0, (
            "Should have at least one backend result"
        )

        # Processing time should be reasonable
        assert result.processing_time > 0, "Processing time should be positive"
        assert result.processing_time < 60, (
            f"Processing should take < 60s, took: {result.processing_time}s"
        )

    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.requires_network
    async def test_assess_questionable_journal_pattern(self) -> None:
        """Test assessment of journal with predatory-like naming pattern.

        Tests a journal name with common predatory characteristics
        (generic name with 'International Journal of Advanced...').
        """
        dispatcher = QueryDispatcher()
        normalizer = InputNormalizer()

        # Use a generic pattern common in predatory journals
        query = normalizer.normalize(
            "International Journal of Advanced Computer Science"
        )

        # Perform assessment
        result = await dispatcher.assess_journal(query)

        # Assertions
        assert result is not None, "Assessment should return a result"
        # Note: This journal is actually classified as legitimate based on real data sources,
        # even though the name pattern appears suspicious. Real data trumps pattern matching.
        # Integration test: We verify component integration works, allowing UNKNOWN if backends
        # are unavailable, but expect LEGITIMATE when data sources are accessible.
        assert result.assessment in [
            AssessmentType.UNKNOWN,  # Acceptable if backends unavailable
            AssessmentType.LEGITIMATE,  # Expected when data sources accessible
        ], f"Should be legitimate or unknown, got: {result.assessment}"

        # Should have processed
        assert result.processing_time > 0, "Processing time should be positive"

    @pytest.mark.integration
    async def test_normalizer_to_dispatcher_integration(self) -> None:
        """Test integration between normalizer and dispatcher components.

        This validates that the normalizer output format is correctly
        consumed by the dispatcher without errors.
        """
        normalizer = InputNormalizer()

        # Test various input formats
        test_inputs = [
            "Nature",
            "Science (ISSN: 0036-8075)",
            "IEEE Computer",
            "Journal of Computer Science Research",
        ]

        for input_text in test_inputs:
            # Normalize
            query = normalizer.normalize(input_text)

            # Validate normalized output structure
            assert isinstance(query, QueryInput), (
                f"Normalizer should return QueryInput for: {input_text}"
            )
            assert query.raw_input == input_text
            assert query.normalized_name is not None
            assert isinstance(query.identifiers, dict)

    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.requires_network
    async def test_concurrent_assessments(self) -> None:
        """Test that concurrent assessments work correctly.

        Validates that multiple assessment requests can be processed
        concurrently without errors or data corruption.
        """
        dispatcher = QueryDispatcher()
        normalizer = InputNormalizer()

        # Prepare multiple queries
        test_journals = ["Nature", "Science", "Cell", "The Lancet", "PLOS ONE"]

        queries = [normalizer.normalize(journal) for journal in test_journals]

        # Run concurrent assessments
        results = await asyncio.gather(
            *[dispatcher.assess_journal(query) for query in queries],
            return_exceptions=True,
        )

        # Validate all succeeded
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                pytest.fail(
                    f"Assessment {i} ({test_journals[i]}) failed with: {result}"
                )

            assert result is not None, f"Result {i} should not be None"
            assert result.input_query == test_journals[i], (
                f"Input query mismatch for {i}"
            )
            assert result.processing_time > 0, f"Processing time invalid for {i}"
