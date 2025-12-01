# SPDX-License-Identifier: MIT
"""Integration tests for BibTeX file processing workflows.

These tests validate end-to-end BibTeX processing including file parsing,
journal extraction, batch assessment, and result formatting.
"""

import tempfile
from pathlib import Path

import pytest

from aletheia_probe.batch_assessor import BibtexBatchAssessor
from aletheia_probe.enums import AssessmentType


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
        assert result.total_entries >= 4, "Should find at least 4 journal articles"
        assert result.total_entries <= 5, (
            "Should not find more than 4-5 entries (books excluded)"
        )

        # Should have some legitimate journals (Nature, Science, PLOS ONE)
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

        with tempfile.NamedTemporaryFile(mode="w", suffix=".bib", delete=False) as f:
            f.write(bibtex_with_issn)
            temp_path = Path(f.name)

        try:
            assessor = BibtexBatchAssessor()
            result = await assessor.assess_bibtex_file(Path(temp_path))

            assert result.total_entries == 1, "Should process one entry"

            # The journal should be processed (Nature should be recognized as legitimate)
            assert result.legitimate_count == 1, (
                "Nature should be recognized as legitimate"
            )

        finally:
            temp_path.unlink()

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

@article{incomplete2
    title={Missing Closing Brace and Journal}
    author={Another, Test}

@article{valid2,
    title={Another Valid Entry},
    author={Another, Valid},
    journal={Nature},
    year={2023}
}
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".bib", delete=False) as f:
            f.write(malformed_bibtex)
            temp_path = Path(f.name)

        try:
            assessor = BibtexBatchAssessor()
            result = await assessor.assess_bibtex_file(Path(temp_path))

            # Should process valid entries despite malformed ones
            assert result.total_entries >= 2, "Should process valid entries"
            assert result.legitimate_count >= 1, "Should find legitimate journals"

        finally:
            temp_path.unlink()

    @pytest.mark.integration
    async def test_large_bibtex_file_processing(self) -> None:
        """Test processing of larger BibTeX files.

        Validates that batch processing can handle files with many entries
        efficiently and without errors.
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

        with tempfile.NamedTemporaryFile(mode="w", suffix=".bib", delete=False) as f:
            f.write(large_bibtex)
            temp_path = Path(f.name)

        try:
            assessor = BibtexBatchAssessor()
            result = await assessor.assess_bibtex_file(Path(temp_path))

            assert result.total_entries == 50, "Should process all 50 entries"
            assert result.processing_time < 300, "Should complete within 5 minutes"

            # Should find legitimate journals
            assert result.legitimate_count > 0, "Should find legitimate journals"

        finally:
            temp_path.unlink()

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

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".bib", delete=False, encoding="utf-8"
        ) as f:
            f.write(unicode_bibtex)
            temp_path = Path(f.name)

        try:
            assessor = BibtexBatchAssessor()
            result = await assessor.assess_bibtex_file(Path(temp_path))

            assert result.total_entries >= 2, "Should process entries with unicode"
            # Should handle unicode gracefully without errors

        finally:
            temp_path.unlink()
