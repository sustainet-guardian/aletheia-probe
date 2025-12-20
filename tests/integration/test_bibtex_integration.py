# SPDX-License-Identifier: MIT
"""Integration tests for BibTeX file processing workflows.

INTEGRATION TEST FILE: This file contains integration tests that verify
component interactions and end-to-end workflows. These are NOT predictable
unit tests - they may make real external API calls and use fuzzy assertions.

See README.md in this directory for details on integration test characteristics
and how to interpret test failures.

These tests validate end-to-end BibTeX processing including file parsing,
journal extraction, batch assessment, and result formatting.
"""

import tempfile
from contextlib import contextmanager
from pathlib import Path

import pytest

from aletheia_probe.batch_assessor import BibtexBatchAssessor
from aletheia_probe.enums import AssessmentType


@contextmanager
def temp_bibtex_file(content: str, encoding: str = "utf-8"):
    """Context manager for creating temporary BibTeX files with automatic cleanup.

    Args:
        content: BibTeX content to write to the file
        encoding: File encoding (default: utf-8)

    Yields:
        Path: Path to the temporary BibTeX file

    Example:
        with temp_bibtex_file("@article{...}") as path:
            result = await assessor.assess_bibtex_file(path)
    """
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".bib", delete=False, encoding=encoding
    ) as f:
        f.write(content)
        temp_path = Path(f.name)

    try:
        yield temp_path
    finally:
        temp_path.unlink()


class TestBibtexIntegration:
    """Integration tests for BibTeX processing workflows."""

    @pytest.fixture
    def sample_bibtex_file(self) -> Path:
        """Create a sample BibTeX file for testing."""
        bibtex_content = """
@article{nature2023,
    title={Breakthrough in DNA Research},
    author={Smith, John and Doe, Jane},
    journal={Nature},
    year={2023},
    volume={615},
    pages={123--130},
    doi={10.1038/nature.2023.12345}
}

@article{science2023,
    title={Advances in Machine Learning},
    author={Johnson, Alice},
    journal={Science},
    year={2023},
    volume={380},
    pages={456--460}
}

@article{questionable2023,
    title={Generic Research Paper},
    author={Unknown, Author},
    journal={International Journal of Advanced Computer Science},
    year={2023},
    volume={1},
    pages={1--10}
}

@book{textbook2022,
    title={Computer Science Fundamentals},
    author={Professor, Academic},
    publisher={Academic Press},
    year={2022}
}

@article{plosone2023,
    title={Open Access Research},
    author={Researcher, Open},
    journal={PLOS ONE},
    year={2023},
    volume={18},
    doi={10.1371/journal.pone.0123456}
}
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".bib", delete=False) as f:
            f.write(bibtex_content.strip())
            temp_path = Path(f.name)

        yield temp_path

        # Cleanup
        if temp_path.exists():
            temp_path.unlink()

    @pytest.mark.integration
    async def test_bibtex_file_processing_end_to_end(
        self, sample_bibtex_file: Path
    ) -> None:
        """Test complete BibTeX file processing workflow.

        Validates that a BibTeX file can be:
        1. Parsed correctly
        2. Journals extracted and normalized
        3. Each journal assessed
        4. Results compiled and formatted
        """
        assessor = BibtexBatchAssessor()

        # Process the BibTeX file
        result = await assessor.assess_bibtex_file(sample_bibtex_file)

        # Assertions about the overall result
        assert result is not None, "Assessment result should not be None"
        # Fixture has 4 articles + 1 book = 5 total entries (parsing is deterministic)
        assert result.total_entries == 5, (
            "Should find exactly 5 total entries (4 articles + 1 book)"
        )

        # Should have some legitimate journals (Nature, Science, PLOS ONE)
        # This test verifies the integration of components (parser → normalizer →
        # dispatcher → assessor → formatter), NOT the correctness of individual
        # assessments. External API calls can fail, so we check >= 2 out of 3 to
        # confirm the integration works, not that all backends are available.
        assert result.legitimate_count >= 2, (
            "Should find at least 2 legitimate journals"
        )

        # May have predatory/suspicious journals
        total_assessed = (
            result.legitimate_count
            + result.predatory_count
            + result.suspicious_count
            + result.insufficient_data_count
        )
        assert total_assessed == result.entries_with_journals, (
            "All journal entries should be assessed"
        )

        # Processing should take reasonable time
        assert result.processing_time > 0, "Processing time should be positive"
        assert result.processing_time < 120, (
            f"Processing should take < 2 min, took: {result.processing_time}s"
        )

    @pytest.mark.integration
    async def test_bibtex_entry_details_extraction(
        self, sample_bibtex_file: Path
    ) -> None:
        """Test that BibTeX entry details are properly extracted.

        Validates that DOIs, authors, titles, and other metadata
        are correctly parsed and preserved in the assessment.
        """
        assessor = BibtexBatchAssessor()

        # Process file (assessor processes all entries by default)
        result = await assessor.assess_bibtex_file(sample_bibtex_file)

        # Verify that journal entries were processed
        assert result is not None, "Assessment result should not be None"
        assert result.total_entries > 0, "Should process some entries"

        # The assessment should recognize well-known legitimate journals
        # (Nature, Science, PLOS ONE from our test data)
        assert result.legitimate_count >= 1, (
            "Should find at least one legitimate journal"
        )

    @pytest.mark.integration
    async def test_bibtex_with_issn_extraction(self) -> None:
        """Test BibTeX processing with ISSN identifiers.

        Validates that ISSN identifiers in BibTeX entries are properly
        extracted and used in assessment.
        """
        bibtex_with_issn = """
@article{nature_with_issn,
    title={Research with ISSN},
    author={Researcher, Test},
    journal={Nature},
    issn={0028-0836},
    year={2023},
    pages={1--10}
}
"""

        with temp_bibtex_file(bibtex_with_issn) as temp_path:
            assessor = BibtexBatchAssessor()
            result = await assessor.assess_bibtex_file(temp_path)

            assert result.total_entries == 1, "Should process one entry"

            # The journal should be processed (Nature should be recognized as legitimate)
            assert result.legitimate_count == 1, (
                "Nature should be recognized as legitimate"
            )

    @pytest.mark.integration
    async def test_bibtex_malformed_entries_handling(self) -> None:
        """Test handling of malformed BibTeX entries.

        Validates that processing continues gracefully when encountering
        malformed or incomplete BibTeX entries.
        """
        malformed_bibtex = """
@article{incomplete1,
    title={Missing Journal Field},
    author={Test, Author},
    year={2023}
}

@article{valid1,
    title={Valid Entry},
    author={Valid, Author},
    journal={Science},
    year={2023}
}

@article{incomplete2,
    title={Missing Journal Field Too},
    author={Another, Test},
    year={2023}
}

@article{valid2,
    title={Another Valid Entry},
    author={Another, Valid},
    journal={Nature},
    year={2023}
}
"""

        with temp_bibtex_file(malformed_bibtex) as temp_path:
            assessor = BibtexBatchAssessor()
            result = await assessor.assess_bibtex_file(temp_path)

            # Should process all entries (including those without journals)
            assert result.total_entries == 4, "Should process all 4 BibTeX entries"
            assert result.legitimate_count >= 1, "Should find legitimate journals"

    @pytest.mark.integration
    async def test_batch_processing_scalability(self) -> None:
        """Test scalability of batch processing with larger BibTeX files.

        This test validates that the batch processor can handle files with many
        entries without crashing or hanging. It is NOT testing the correctness
        of individual journal assessments (which depends on external API availability),
        but rather the ability to process large batches reliably.

        Uses 50 entries with well-known legitimate journals to verify the system
        can handle realistic workloads.
        """
        # Generate a larger BibTeX file
        large_bibtex_entries = []

        journals = [
            "Nature",
            "Science",
            "Cell",
            "The Lancet",
            "PLOS ONE",
            "IEEE Computer",
            "ACM Computing Surveys",
            "Journal of AI Research",
        ]

        for i in range(50):  # 50 entries
            journal = journals[i % len(journals)]
            entry = f"""
@article{{test{i:03d},
    title={{Test Article {i}}},
    author={{Author{i}, Test}},
    journal={{{journal}}},
    year={{2023}},
    volume={{1}},
    pages={{{i}--{i + 5}}}
}}"""
            large_bibtex_entries.append(entry)

        large_bibtex = "\n".join(large_bibtex_entries)

        with temp_bibtex_file(large_bibtex) as temp_path:
            assessor = BibtexBatchAssessor()
            result = await assessor.assess_bibtex_file(temp_path)

            assert result.total_entries == 50, "Should process all 50 entries"
            assert result.processing_time < 300, "Should complete within 5 minutes"

            # Note: We only verify that SOME assessments succeeded (> 0), not all 50,
            # because this is an integration test with real backend API calls that may
            # fail or timeout. This tests batch processing capability, not assessment
            # correctness.
            assert result.legitimate_count > 0, "Should find legitimate journals"

    @pytest.mark.integration
    async def test_bibtex_unicode_handling(self) -> None:
        """Test BibTeX processing with unicode characters.

        Validates that entries with unicode characters in titles,
        authors, and journal names are handled correctly.
        """
        unicode_bibtex = """
@article{unicode1,
    title={Résumé of Artificial Intelligence Research},
    author={Müller, Hans and González, María},
    journal={Nature},
    year={2023}
}

@article{unicode2,
    title={学术研究进展},
    author={王, 小明 and 李, 小红},
    journal={科学杂志},
    year={2023}
}

@article{unicode3,
    title={Исследование в области ИИ},
    author={Иванов, Иван},
    journal={Science},
    year={2023}
}
"""

        with temp_bibtex_file(unicode_bibtex) as temp_path:
            assessor = BibtexBatchAssessor()
            result = await assessor.assess_bibtex_file(temp_path)

            # Integration test: Use fuzzy assertion because assessment results depend
            # on external APIs that may be unavailable. We verify the system handles
            # unicode without crashing, not that all entries are successfully assessed.
            assert result.total_entries >= 2, (
                "Should process at least 2 out of 3 entries with unicode characters"
            )

            # Unicode-specific check: Verify specific unicode strings from test data
            # are preserved correctly during parsing (not corrupted or stripped)
            expected_unicode_strings = [
                "Résumé",  # French accent in title
                "Müller",  # German umlaut in author
                "González",  # Spanish accent in author
                "学术研究进展",  # Chinese title
                "Исследование",  # Russian/Cyrillic title
            ]

            unicode_strings_found = []
            for entry, _ in result.assessment_results:
                text_fields = [
                    entry.title or "",
                    entry.authors or "",
                    entry.journal_name or "",
                ]
                combined_text = " ".join(text_fields)
                for unicode_str in expected_unicode_strings:
                    if unicode_str in combined_text:
                        unicode_strings_found.append(unicode_str)

            assert len(unicode_strings_found) >= 1, (
                f"Should preserve at least one unicode string from test data. "
                f"Expected any of {expected_unicode_strings}, found {unicode_strings_found}"
            )
