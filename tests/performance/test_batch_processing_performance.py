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
import threading
import time
from unittest.mock import AsyncMock, patch

# Performance testing dependencies (required in dev group)
import psutil
import pytest

from aletheia_probe.batch_assessor import BibtexBatchAssessor
from aletheia_probe.enums import AssessmentType
from aletheia_probe.models import AssessmentResult, BibtexAssessmentResult


# Conversion factor for bytes to megabytes
BYTES_TO_MB = 1024 * 1024

# Memory test configuration constants
MEMORY_TEST_ENTRY_COUNT = 50  # Number of BibTeX entries to process in memory test
MEMORY_SAMPLE_INTERVAL = 0.05  # Time in seconds between memory samples (50ms)
MONITOR_THREAD_TIMEOUT = 1.0  # Timeout in seconds for joining monitor thread


@pytest.fixture
def mock_dispatcher():
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


@pytest.mark.benchmark
class TestBatchProcessingPerformance:
    """Performance benchmarks for batch BibTeX processing."""

    def _run_scaling_test(
        self,
        benchmark,
        generated_bibtex_file,
        mock_dispatcher,
        performance_baseline,
        entry_count: int,
    ) -> BibtexAssessmentResult:
        """
        Common test logic for scaling tests.

        Args:
            benchmark: pytest-benchmark fixture
            generated_bibtex_file: Fixture for generating BibTeX files
            mock_dispatcher: Mock query dispatcher fixture
            performance_baseline: Performance baseline targets
            entry_count: Number of BibTeX entries to process

        Returns:
            BibtexAssessmentResult from the benchmark run
        """
        bibtex_file = generated_bibtex_file(entry_count)
        assessor = BibtexBatchAssessor()

        def process_file() -> BibtexAssessmentResult:
            """Process the BibTeX file."""
            return asyncio.run(assessor.assess_bibtex_file(bibtex_file))

        result = benchmark(process_file)

        # Verify functionality
        assert result.total_entries == entry_count
        assert result.entries_with_journals == entry_count

        # Assert timing requirements
        mean_time = benchmark.stats["mean"]
        max_time = performance_baseline["batch_entries_max_time"].get(entry_count)
        if max_time is not None:
            assert mean_time < max_time, (
                f"Mean processing time {mean_time:.2f}s exceeds baseline {max_time:.2f}s for {entry_count} entries"
            )

        return result

    @pytest.mark.parametrize("entry_count", [10])
    def test_bibtex_processing_scaling(
        self,
        benchmark,
        generated_bibtex_file,
        mock_dispatcher,
        performance_baseline,
        entry_count,
    ):
        """
        Test performance scaling with minimal file size for fast feedback.

        This test provides quick performance feedback during development
        without adding significant time to the quality checks.

        Args:
            entry_count: Number of BibTeX entries to process
        """
        self._run_scaling_test(
            benchmark,
            generated_bibtex_file,
            mock_dispatcher,
            performance_baseline,
            entry_count,
        )

    @pytest.mark.benchmark_comprehensive
    @pytest.mark.parametrize("entry_count", [10, 50, 100, 200, 500])
    def test_bibtex_processing_scaling_comprehensive(
        self,
        benchmark,
        generated_bibtex_file,
        mock_dispatcher,
        performance_baseline,
        entry_count,
    ):
        """
        Comprehensive performance scaling test with multiple data points.

        This test runs with various file sizes to understand how performance
        scales with input size. It provides detailed scaling analysis but
        takes longer to run, so it's excluded from regular quality checks
        and runs on a weekly schedule in CI/CD.

        Args:
            entry_count: Number of BibTeX entries to process
        """
        self._run_scaling_test(
            benchmark,
            generated_bibtex_file,
            mock_dispatcher,
            performance_baseline,
            entry_count,
        )

    def test_batch_processing_memory_usage(
        self, benchmark, generated_bibtex_file, mock_dispatcher, performance_baseline
    ):
        """
        Monitor memory usage during batch processing.

        This test ensures memory usage remains within acceptable bounds
        during batch processing operations. It continuously monitors memory
        to capture actual peak usage, not just before/after snapshots.
        """
        # Use a moderate file size for memory testing
        bibtex_file = generated_bibtex_file(MEMORY_TEST_ENTRY_COUNT)
        process = psutil.Process(os.getpid())

        # Get initial memory usage
        initial_memory_mb = process.memory_info().rss / BYTES_TO_MB

        # Tracking for continuous memory monitoring
        peak_memory_mb = initial_memory_mb
        peak_memory_lock = threading.Lock()
        monitoring_active = threading.Event()
        monitoring_active.set()

        def monitor_memory() -> None:
            """Continuously monitor memory usage in background thread."""
            nonlocal peak_memory_mb
            while monitoring_active.is_set():
                current_memory_mb = process.memory_info().rss / BYTES_TO_MB
                with peak_memory_lock:
                    peak_memory_mb = max(peak_memory_mb, current_memory_mb)
                time.sleep(MEMORY_SAMPLE_INTERVAL)

        # Start memory monitoring thread
        monitor_thread = threading.Thread(target=monitor_memory, daemon=True)
        monitor_thread.start()

        def process_file() -> BibtexAssessmentResult:
            """Process the BibTeX file."""
            assessor = BibtexBatchAssessor()
            return asyncio.run(assessor.assess_bibtex_file(bibtex_file))

        try:
            # Run the benchmark and get the result
            result = benchmark(process_file)
        finally:
            # Stop memory monitoring
            monitoring_active.clear()
            monitor_thread.join(timeout=MONITOR_THREAD_TIMEOUT)

        with peak_memory_lock:
            memory_increase_mb = peak_memory_mb - initial_memory_mb

        # Verify functionality
        assert result.total_entries == MEMORY_TEST_ENTRY_COUNT
        assert result.entries_with_journals == MEMORY_TEST_ENTRY_COUNT

        # Memory usage should be reasonable
        assert (
            memory_increase_mb < performance_baseline["batch_processing_max_memory_mb"]
        ), f"Memory increase {memory_increase_mb:.2f}MB exceeds baseline"
