# SPDX-License-Identifier: MIT
"""Performance tests for batch processing functionality.

This module contains performance benchmarks for BibTeX batch processing,
measuring processing time and memory usage for various file sizes.

These tests are mandatory and run as part of the quality checks.
Run them with:
    pytest tests/performance/ --benchmark-only
"""

import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

# Performance testing dependencies (required in dev group)
import psutil
import pytest

from aletheia_probe.batch_assessor import BibtexBatchAssessor
from aletheia_probe.enums import AssessmentType
from aletheia_probe.models import AssessmentResult


@pytest.mark.benchmark
class TestBatchProcessingPerformance:
    """Performance benchmarks for batch BibTeX processing."""

    @pytest.fixture
    def mock_dispatcher(self):
        """
        Create a mock query dispatcher that simulates fast responses.

        This allows us to test batch processing performance without
        being limited by actual backend API response times.
        """
        with patch("aletheia_probe.batch_assessor.query_dispatcher") as mock:
            # Configure mock to return results quickly
            mock.assess_journal = AsyncMock(
                return_value=AssessmentResult(
                    input_query="test",
                    assessment=AssessmentType.LEGITIMATE.value,
                    confidence=0.9,
                    overall_score=0.9,
                    venue_type="journal",
                    backend_results=[],
                    processing_time=0.01,
                )
            )
            yield mock

    def test_small_bibtex_processing_performance(
        self, benchmark, generated_bibtex_file, mock_dispatcher
    ):
        """
        Benchmark processing of small BibTeX file (10 entries).

        This test establishes a baseline for processing small bibliography files,
        which is the most common use case.
        """
        bibtex_file = generated_bibtex_file(10)
        assessor = BibtexBatchAssessor()

        def process_file():
            """Process the BibTeX file."""
            return asyncio.run(assessor.assess_bibtex_file(bibtex_file))

        result = benchmark(process_file)

        # Verify functionality
        assert result.total_entries == 10
        assert result.entries_with_journals == 10

    @pytest.mark.parametrize("entry_count", [10, 50])
    def test_bibtex_processing_scaling(
        self, benchmark, generated_bibtex_file, mock_dispatcher, entry_count
    ):
        """
        Test performance scaling with different file sizes.

        This test validates that processing time scales reasonably with
        the number of entries in the BibTeX file.

        Args:
            entry_count: Number of BibTeX entries to process
        """
        bibtex_file = generated_bibtex_file(entry_count)
        assessor = BibtexBatchAssessor()

        def process_file():
            """Process the BibTeX file."""
            return asyncio.run(assessor.assess_bibtex_file(bibtex_file))

        result = benchmark(process_file)

        # Verify functionality
        assert result.total_entries == entry_count
        assert result.entries_with_journals == entry_count

    def test_batch_processing_memory_usage(
        self, benchmark, generated_bibtex_file, mock_dispatcher, performance_baseline
    ):
        """
        Monitor memory usage during batch processing.

        This test ensures memory usage remains within acceptable bounds
        during batch processing operations.
        """
        # Use a moderate file size for memory testing
        bibtex_file = generated_bibtex_file(50)
        process = psutil.Process(os.getpid())

        # Get initial memory usage
        initial_memory_mb = process.memory_info().rss / 1024 / 1024

        def process_file():
            """Process the BibTeX file."""
            assessor = BibtexBatchAssessor()
            return asyncio.run(assessor.assess_bibtex_file(bibtex_file))

        # Run the benchmark and get the result
        result = benchmark(process_file)

        # Get peak memory usage
        peak_memory_mb = process.memory_info().rss / 1024 / 1024
        memory_increase_mb = peak_memory_mb - initial_memory_mb

        # Verify functionality
        assert result.total_entries == 50
        assert result.entries_with_journals == 50

        # Memory usage should be reasonable
        assert (
            memory_increase_mb < performance_baseline["batch_processing_max_memory_mb"]
        ), f"Memory increase {memory_increase_mb:.2f}MB exceeds baseline"
