# SPDX-License-Identifier: MIT
"""Pytest configuration and fixtures for performance tests."""

from pathlib import Path

import pytest


@pytest.fixture
def generated_bibtex_file(tmp_path: Path):
    """
    Generate BibTeX files of varying sizes for performance testing.

    Args:
        tmp_path: Temporary directory provided by pytest

    Returns:
        Callable that generates a BibTeX file with specified number of entries
    """

    def _generate(entry_count: int) -> Path:
        """
        Generate a BibTeX file with specified number of entries.

        Args:
            entry_count: Number of BibTeX entries to generate

        Returns:
            Path to the generated BibTeX file
        """
        bibtex_entries = []
        for i in range(entry_count):
            # Generate realistic BibTeX entries with varying journals
            journal_names = [
                "Nature",
                "Science",
                "Journal of Advanced Research",
                "International Journal of Technology",
                "Academic Press",
            ]
            journal = journal_names[i % len(journal_names)]

            entry = f"""@article{{entry{i},
    title={{Article Title {i}}},
    journal={{{journal}}},
    author={{Author{i}, First and CoAuthor{i}, Second}},
    year={{{2020 + (i % 4)}}},
    volume={{{i % 100}}},
    pages={{{i * 10}-{i * 10 + 9}}},
    doi={{10.1000/test.{i:06d}}}
}}
"""
            bibtex_entries.append(entry)

        file_path = tmp_path / f"generated_{entry_count}.bib"
        file_path.write_text("\n".join(bibtex_entries))
        return file_path

    return _generate


@pytest.fixture
def performance_baseline():
    """
    Define performance baseline targets for regression detection.

    These are initial conservative targets for MVP. Should be adjusted
    based on actual measurements and system capabilities.

    Returns:
        dict: Performance targets in seconds or MB
    """
    return {
        # Batch Processing Targets (seconds)
        "batch_entries_max_time": {
            10: 30.0,
            50: 120.0,
            100: 240.0,
            200: 480.0,
            500: 1200.0,
        },
        # Cache Operation Targets
        "cache_search_max_time": 1.0,  # seconds
        "cache_insert_max_time": 0.1,  # seconds
        # Memory Usage Targets
        "batch_processing_max_memory_mb": 500.0,  # MB
    }
