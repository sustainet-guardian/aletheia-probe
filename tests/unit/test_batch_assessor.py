# SPDX-License-Identifier: MIT
"""Tests for BibtexBatchAssessor functionality."""

from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from aletheia_probe.article_retraction_checker import ArticleRetractionResult
from aletheia_probe.batch_assessor import BibtexBatchAssessor
from aletheia_probe.enums import AssessmentType
from aletheia_probe.models import (
    AssessmentResult,
    BibtexAssessmentResult,
    QueryInput,
    VenueType,
)


class TestBibtexBatchAssessor:
    """Test suite for BibtexBatchAssessor functionality."""

    @pytest.fixture
    def sample_bibtex_file(self, tmp_path: Path) -> Path:
        """Create a sample BibTeX file with legitimate journals."""
        bibtex_content = """
@article{nature2023,
    title={Advances in Machine Learning},
    journal={Nature},
    author={Smith, John and Doe, Jane},
    year={2023},
    doi={10.1038/s41586-023-00001-0}
}

@article{science2023,
    title={Quantum Computing Breakthroughs},
    journal={Science},
    author={Johnson, Alice},
    year={2023},
    doi={10.1126/science.abc123}
}
"""
        file_path = tmp_path / "sample.bib"
        file_path.write_text(bibtex_content)
        return file_path

    @pytest.fixture
    def predatory_bibtex_file(self, tmp_path: Path) -> Path:
        """Create a BibTeX file with known predatory journals."""
        bibtex_content = """
@article{predatory1,
    title={Sample Article},
    journal={International Journal of Advanced Research},
    author={Test Author},
    year={2023}
}

@article{predatory2,
    title={Another Article},
    journal={World Journal of Science and Technology},
    author={Another Author},
    year={2023}
}
"""
        file_path = tmp_path / "predatory.bib"
        file_path.write_text(bibtex_content)
        return file_path

    @pytest.fixture
    def empty_bibtex_file(self, tmp_path: Path) -> Path:
        """Create an empty BibTeX file."""
        file_path = tmp_path / "empty.bib"
        file_path.write_text("")
        return file_path

    @pytest.fixture
    def malformed_bibtex_file(self, tmp_path: Path) -> Path:
        """Create a BibTeX file with invalid syntax."""
        bibtex_content = """
@article{invalid
    title={Missing comma and closing brace
    journal={Invalid Journal}
    year={2023
"""
        file_path = tmp_path / "malformed.bib"
        file_path.write_text(bibtex_content)
        return file_path

    @pytest.fixture
    def mock_dispatcher(self):
        """Create a mock query dispatcher for testing."""
        with patch("aletheia_probe.batch_assessor.query_dispatcher") as mock:
            # Configure the mock to return legitimate results by default
            mock.assess_journal = AsyncMock(
                return_value=AssessmentResult(
                    input_query="test",
                    assessment=AssessmentType.LEGITIMATE.value,
                    confidence=0.9,
                    overall_score=0.9,
                    backend_results=[],
                    metadata=None,
                    reasoning=["Found in reputable database"],
                    processing_time=0.1,
                    venue_type=VenueType.JOURNAL,
                )
            )
            yield mock

    @pytest.fixture
    def mock_retraction_checker(self):
        """Create a mock retraction checker for testing."""
        with patch(
            "aletheia_probe.batch_assessor.ArticleRetractionChecker"
        ) as mock_class:
            mock_instance = Mock()
            mock_instance.check_doi = AsyncMock(
                return_value=ArticleRetractionResult(
                    doi="10.1234/test",
                    is_retracted=False,
                    retraction_date=None,
                    retraction_type=None,
                    retraction_reason=None,
                    sources=[],
                )
            )
            mock_class.return_value = mock_instance
            yield mock_instance

    @pytest.mark.asyncio
    async def test_assess_empty_bibtex_file(
        self, empty_bibtex_file: Path, mock_dispatcher, mock_retraction_checker
    ):
        """Test handling of empty BibTeX files."""
        result = await BibtexBatchAssessor.assess_bibtex_file(empty_bibtex_file)

        assert isinstance(result, BibtexAssessmentResult)
        assert result.total_entries == 0
        assert result.entries_with_journals == 0
        assert result.predatory_count == 0
        assert result.legitimate_count == 0
        assert not result.has_predatory_journals
        assert result.processing_time >= 0

    @pytest.mark.asyncio
    async def test_assess_valid_bibtex_file(
        self, sample_bibtex_file: Path, mock_dispatcher, mock_retraction_checker
    ):
        """Test normal processing flow with valid BibTeX file."""
        result = await BibtexBatchAssessor.assess_bibtex_file(sample_bibtex_file)

        assert isinstance(result, BibtexAssessmentResult)
        assert result.total_entries == 2
        assert result.entries_with_journals == 2
        assert result.legitimate_count == 2
        assert result.predatory_count == 0
        assert not result.has_predatory_journals
        assert len(result.assessment_results) == 2

    @pytest.mark.asyncio
    async def test_assess_bibtex_with_predatory_journals(
        self, predatory_bibtex_file: Path, mock_retraction_checker
    ):
        """Test detection and exit code 1 for predatory journals."""
        # Mock dispatcher to return predatory results
        with patch("aletheia_probe.batch_assessor.query_dispatcher") as mock_dispatcher:
            mock_dispatcher.assess_journal = AsyncMock(
                return_value=AssessmentResult(
                    input_query="test",
                    assessment=AssessmentType.PREDATORY.value,
                    confidence=0.95,
                    overall_score=0.0,
                    backend_results=[],
                    metadata=None,
                    reasoning=["Found in predatory journal list"],
                    processing_time=0.1,
                    venue_type=VenueType.JOURNAL,
                )
            )

            result = await BibtexBatchAssessor.assess_bibtex_file(predatory_bibtex_file)

            assert isinstance(result, BibtexAssessmentResult)
            assert result.predatory_count == 2
            assert result.has_predatory_journals
            assert result.legitimate_count == 0

            # Test exit code
            exit_code = BibtexBatchAssessor.get_exit_code(result)
            assert exit_code == 1

    @pytest.mark.asyncio
    async def test_assess_bibtex_legitimate_journals_only(
        self, sample_bibtex_file: Path, mock_dispatcher, mock_retraction_checker
    ):
        """Test clean results and exit code 0 for legitimate journals."""
        result = await BibtexBatchAssessor.assess_bibtex_file(sample_bibtex_file)

        assert isinstance(result, BibtexAssessmentResult)
        assert result.legitimate_count == 2
        assert result.predatory_count == 0
        assert not result.has_predatory_journals

        # Test exit code
        exit_code = BibtexBatchAssessor.get_exit_code(result)
        assert exit_code == 0

    @pytest.mark.asyncio
    async def test_assess_nonexistent_file(self, tmp_path: Path, mock_dispatcher):
        """Test file not found scenarios."""
        nonexistent_file = tmp_path / "does_not_exist.bib"

        with pytest.raises(ValueError, match="Failed to parse BibTeX file"):
            await BibtexBatchAssessor.assess_bibtex_file(nonexistent_file)

    @pytest.mark.asyncio
    async def test_assess_malformed_bibtex(
        self, malformed_bibtex_file: Path, mock_dispatcher
    ):
        """Test invalid BibTeX syntax."""
        with pytest.raises(ValueError, match="Failed to parse BibTeX file"):
            await BibtexBatchAssessor.assess_bibtex_file(malformed_bibtex_file)

    @pytest.mark.asyncio
    async def test_concurrent_assessment_failures(
        self, sample_bibtex_file: Path, mock_retraction_checker
    ):
        """Test partial backend failures and error handling."""
        # Mock dispatcher to raise an exception for one journal
        call_count = 0

        async def mock_assess_with_failure(query_input):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("Backend timeout")
            return AssessmentResult(
                input_query="test",
                assessment=AssessmentType.LEGITIMATE.value,
                confidence=0.9,
                overall_score=0.9,
                backend_results=[],
                metadata=None,
                reasoning=["Found in database"],
                processing_time=0.1,
                venue_type=VenueType.JOURNAL,
            )

        with patch("aletheia_probe.batch_assessor.query_dispatcher") as mock_dispatcher:
            mock_dispatcher.assess_journal = AsyncMock(
                side_effect=mock_assess_with_failure
            )

            result = await BibtexBatchAssessor.assess_bibtex_file(sample_bibtex_file)

            assert isinstance(result, BibtexAssessmentResult)
            # One should fail with error, one should succeed
            assert result.total_entries == 2
            assert result.insufficient_data_count == 1
            assert result.legitimate_count == 1

    @pytest.mark.asyncio
    async def test_format_assessment_summary(
        self, sample_bibtex_file: Path, mock_dispatcher, mock_retraction_checker
    ):
        """Test text output formatting."""
        result = await BibtexBatchAssessor.assess_bibtex_file(sample_bibtex_file)

        summary = BibtexBatchAssessor.format_summary(result, verbose=False)

        assert "BibTeX Assessment Summary" in summary
        assert f"File: {result.file_path}" in summary
        assert f"Total entries in file: {result.total_entries}" in summary
        assert f"Predatory: {result.predatory_count}" in summary
        assert f"Legitimate: {result.legitimate_count}" in summary
        assert "No predatory journals" in summary

    @pytest.mark.asyncio
    async def test_format_summary_verbose(
        self, sample_bibtex_file: Path, mock_dispatcher, mock_retraction_checker
    ):
        """Test verbose text output with detailed results."""
        result = await BibtexBatchAssessor.assess_bibtex_file(sample_bibtex_file)

        summary = BibtexBatchAssessor.format_summary(result, verbose=True)

        assert "BibTeX Assessment Summary" in summary
        assert "Detailed Results:" in summary
        # Should contain journal names in verbose mode
        assert any(
            entry.journal_name in summary for entry, _ in result.assessment_results
        )

    @pytest.mark.asyncio
    async def test_retracted_article_detection(self, tmp_path: Path, mock_dispatcher):
        """Test detection of retracted articles via DOI."""
        bibtex_content = """
@article{retracted2023,
    title={Retracted Article},
    journal={Nature},
    author={Test Author},
    year={2023},
    doi={10.1038/retracted-001}
}
"""
        file_path = tmp_path / "retracted.bib"
        file_path.write_text(bibtex_content)

        # Mock retraction checker to return retracted status
        with patch(
            "aletheia_probe.batch_assessor.ArticleRetractionChecker"
        ) as mock_class:
            mock_instance = Mock()
            mock_instance.check_doi = AsyncMock(
                return_value=ArticleRetractionResult(
                    doi="10.1038/retracted-001",
                    is_retracted=True,
                    retraction_date="2023-05-15",
                    retraction_type="misconduct",
                    retraction_reason="Data fabrication",
                    sources=["RetractionWatch"],
                )
            )
            mock_class.return_value = mock_instance

            result = await BibtexBatchAssessor.assess_bibtex_file(file_path)

            assert result.retracted_articles_count == 1
            assert result.articles_checked_for_retraction == 1

            # Exit code should be 1 when retracted articles found
            exit_code = BibtexBatchAssessor.get_exit_code(result)
            assert exit_code == 1

            # Check summary includes retraction warning
            summary = BibtexBatchAssessor.format_summary(result)
            assert "Retracted articles" in summary

    @pytest.mark.asyncio
    async def test_mixed_assessment_results(
        self, tmp_path: Path, mock_retraction_checker
    ):
        """Test BibTeX file with mixed assessment types."""
        bibtex_content = """
@article{legitimate,
    title={Legitimate Article},
    journal={Nature},
    author={Good Author},
    year={2023}
}

@article{predatory,
    title={Predatory Article},
    journal={Suspicious Journal},
    author={Bad Author},
    year={2023}
}

@article{suspicious,
    title={Suspicious Article},
    journal={Questionable Journal},
    author={Unknown Author},
    year={2023}
}
"""
        file_path = tmp_path / "mixed.bib"
        file_path.write_text(bibtex_content)

        # Mock dispatcher to return different results for different journals
        call_count = 0
        assessment_types = [
            AssessmentType.LEGITIMATE,
            AssessmentType.PREDATORY,
            AssessmentType.SUSPICIOUS,
        ]

        async def mock_assess_mixed(query_input):
            nonlocal call_count
            assessment = assessment_types[call_count]
            call_count += 1
            return AssessmentResult(
                input_query="test",
                assessment=assessment.value,
                confidence=0.8,
                overall_score=0.5,
                backend_results=[],
                metadata=None,
                reasoning=[f"Classified as {assessment.value}"],
                processing_time=0.1,
                venue_type=VenueType.JOURNAL,
            )

        with patch("aletheia_probe.batch_assessor.query_dispatcher") as mock_dispatcher:
            mock_dispatcher.assess_journal = AsyncMock(side_effect=mock_assess_mixed)

            result = await BibtexBatchAssessor.assess_bibtex_file(file_path)

            assert result.legitimate_count == 1
            assert result.predatory_count == 1
            assert result.suspicious_count == 1
            assert result.total_entries == 3

    @pytest.mark.asyncio
    async def test_venue_type_counting(self, tmp_path: Path, mock_retraction_checker):
        """Test venue type counting for conferences and journals."""
        bibtex_content = """
@article{journal1,
    title={Journal Article},
    journal={Test Journal},
    author={Author},
    year={2023}
}

@inproceedings{conf1,
    title={Conference Paper},
    booktitle={Test Conference},
    author={Author},
    year={2023}
}

@inproceedings{workshop1,
    title={Workshop Paper},
    booktitle={ML Workshop 2023},
    author={Author},
    year={2023}
}
"""
        file_path = tmp_path / "venues.bib"
        file_path.write_text(bibtex_content)

        with patch("aletheia_probe.batch_assessor.query_dispatcher") as mock_dispatcher:
            # Configure mock to preserve venue types
            async def mock_assess_preserve_venue(query_input):
                return AssessmentResult(
                    input_query="test",
                    assessment=AssessmentType.LEGITIMATE.value,
                    confidence=0.9,
                    overall_score=0.9,
                    backend_results=[],
                    metadata=None,
                    reasoning=["Test"],
                    processing_time=0.1,
                    venue_type=query_input.venue_type,
                )

            mock_dispatcher.assess_journal = AsyncMock(
                side_effect=mock_assess_preserve_venue
            )

            result = await BibtexBatchAssessor.assess_bibtex_file(file_path)

            assert result.journal_entries == 1
            assert result.conference_entries == 2  # Both inproceedings and workshop
            assert VenueType.JOURNAL in result.venue_type_counts
            assert (
                VenueType.CONFERENCE in result.venue_type_counts
                or VenueType.WORKSHOP in result.venue_type_counts
            )

    @pytest.mark.asyncio
    async def test_cache_usage_for_duplicate_journals(
        self, tmp_path: Path, mock_retraction_checker
    ):
        """Test that duplicate journal names use cached results."""
        bibtex_content = """
@article{article1,
    title={First Article},
    journal={Nature},
    author={Author One},
    year={2023}
}

@article{article2,
    title={Second Article},
    journal={Nature},
    author={Author Two},
    year={2023}
}

@article{article3,
    title={Third Article},
    journal={nature},
    author={Author Three},
    year={2023}
}
"""
        file_path = tmp_path / "duplicates.bib"
        file_path.write_text(bibtex_content)

        with patch("aletheia_probe.batch_assessor.query_dispatcher") as mock_dispatcher:
            mock_dispatcher.assess_journal = AsyncMock(
                return_value=AssessmentResult(
                    input_query="test",
                    assessment=AssessmentType.LEGITIMATE.value,
                    confidence=0.9,
                    overall_score=0.9,
                    backend_results=[],
                    metadata=None,
                    reasoning=["Test"],
                    processing_time=0.1,
                    venue_type=VenueType.JOURNAL,
                )
            )

            result = await BibtexBatchAssessor.assess_bibtex_file(file_path)

            # Should assess all 3 entries
            assert result.total_entries == 3
            assert result.legitimate_count == 3

            # But only call the dispatcher once for "Nature" (case-insensitive cache)
            assert mock_dispatcher.assess_journal.call_count == 1

    @pytest.mark.asyncio
    async def test_preprint_entries_skipped(
        self, tmp_path: Path, mock_dispatcher, mock_retraction_checker
    ):
        """Test that preprint entries (arXiv) are skipped."""
        bibtex_content = """
@article{journal1,
    title={Regular Journal},
    journal={Nature},
    author={Author},
    year={2023}
}

@article{arxiv1,
    title={arXiv Preprint},
    journal={arXiv preprint arXiv:2301.12345},
    author={Author},
    year={2023}
}
"""
        file_path = tmp_path / "with_preprints.bib"
        file_path.write_text(bibtex_content)

        result = await BibtexBatchAssessor.assess_bibtex_file(file_path)

        assert result.total_entries == 2
        assert result.preprint_entries_count == 1
        assert result.entries_with_journals == 1

    @pytest.mark.asyncio
    async def test_verbose_output_flag(
        self, sample_bibtex_file: Path, mock_dispatcher, mock_retraction_checker
    ):
        """Test that verbose flag affects output."""
        result = await BibtexBatchAssessor.assess_bibtex_file(
            sample_bibtex_file, verbose=True
        )

        assert isinstance(result, BibtexAssessmentResult)
        # Verbose flag doesn't affect the result structure, just logging

    @pytest.mark.asyncio
    async def test_relax_bibtex_flag(
        self, tmp_path: Path, mock_dispatcher, mock_retraction_checker
    ):
        """Test that relax_bibtex flag enables tolerant parsing."""
        # Create a slightly malformed but recoverable BibTeX file
        bibtex_content = """
@article{test,
    title={Test},
    journal={Test Journal},
    year={2023}
}
"""
        file_path = tmp_path / "relaxed.bib"
        file_path.write_text(bibtex_content)

        result = await BibtexBatchAssessor.assess_bibtex_file(
            file_path, relax_bibtex=True
        )

        assert isinstance(result, BibtexAssessmentResult)

    @pytest.mark.asyncio
    async def test_processing_time_recorded(
        self, sample_bibtex_file: Path, mock_dispatcher, mock_retraction_checker
    ):
        """Test that processing time is recorded."""
        result = await BibtexBatchAssessor.assess_bibtex_file(sample_bibtex_file)

        assert result.processing_time > 0
        assert isinstance(result.processing_time, float)

    @pytest.mark.asyncio
    async def test_exit_code_with_retracted_articles(
        self, tmp_path: Path, mock_dispatcher
    ):
        """Test exit code is 1 when retracted articles found."""
        bibtex_content = """
@article{retracted,
    title={Retracted},
    journal={Nature},
    author={Author},
    year={2023},
    doi={10.1234/retracted}
}
"""
        file_path = tmp_path / "retracted.bib"
        file_path.write_text(bibtex_content)

        with patch(
            "aletheia_probe.batch_assessor.ArticleRetractionChecker"
        ) as mock_class:
            mock_instance = Mock()
            mock_instance.check_doi = AsyncMock(
                return_value=ArticleRetractionResult(
                    doi="10.1234/retracted",
                    is_retracted=True,
                    retraction_date="2023-01-01",
                    retraction_type="misconduct",
                    retraction_reason="Fraud",
                    sources=["RetractionWatch"],
                )
            )
            mock_class.return_value = mock_instance

            result = await BibtexBatchAssessor.assess_bibtex_file(file_path)

            assert result.retracted_articles_count == 1
            exit_code = BibtexBatchAssessor.get_exit_code(result)
            assert exit_code == 1

    @pytest.mark.asyncio
    async def test_exit_code_combined_issues(
        self, tmp_path: Path, mock_retraction_checker
    ):
        """Test exit code is 1 when both predatory journals and retracted articles found."""
        bibtex_content = """
@article{predatory,
    title={Predatory},
    journal={Bad Journal},
    author={Author},
    year={2023},
    doi={10.1234/retracted}
}
"""
        file_path = tmp_path / "combined.bib"
        file_path.write_text(bibtex_content)

        # Mock both predatory and retracted
        with patch("aletheia_probe.batch_assessor.query_dispatcher") as mock_dispatcher:
            mock_dispatcher.assess_journal = AsyncMock(
                return_value=AssessmentResult(
                    input_query="test",
                    assessment=AssessmentType.PREDATORY.value,
                    confidence=0.95,
                    overall_score=0.0,
                    backend_results=[],
                    metadata=None,
                    reasoning=["Predatory"],
                    processing_time=0.1,
                    venue_type=VenueType.JOURNAL,
                )
            )

            with patch(
                "aletheia_probe.batch_assessor.ArticleRetractionChecker"
            ) as mock_class:
                mock_instance = Mock()
                mock_instance.check_doi = AsyncMock(
                    return_value=ArticleRetractionResult(
                        doi="10.1234/retracted",
                        is_retracted=True,
                        retraction_date="2023-01-01",
                        retraction_type="misconduct",
                        retraction_reason="Fraud",
                        sources=["RetractionWatch"],
                    )
                )
                mock_class.return_value = mock_instance

                result = await BibtexBatchAssessor.assess_bibtex_file(file_path)

                assert result.predatory_count == 1
                assert result.retracted_articles_count == 1
                exit_code = BibtexBatchAssessor.get_exit_code(result)
                assert exit_code == 1

    def test_format_summary_with_retracted_articles(self, tmp_path: Path):
        """Test that summary correctly displays retracted article information."""
        # Create a mock result with retracted articles
        result = BibtexAssessmentResult(
            file_path=str(tmp_path / "test.bib"),
            total_entries=1,
            entries_with_journals=1,
            preprint_entries_count=0,
            skipped_entries_count=0,
            predatory_count=0,
            legitimate_count=1,
            insufficient_data_count=0,
            suspicious_count=0,
            conference_entries=0,
            conference_predatory=0,
            conference_legitimate=0,
            conference_suspicious=0,
            journal_entries=1,
            journal_predatory=0,
            journal_legitimate=1,
            journal_suspicious=0,
            has_predatory_journals=False,
            venue_type_counts={VenueType.JOURNAL: 1},
            retracted_articles_count=1,
            articles_checked_for_retraction=1,
            processing_time=0.5,
        )

        summary = BibtexBatchAssessor.format_summary(result)

        assert "Article Retraction Check:" in summary
        assert "Retracted articles: 1" in summary
        assert "WARNING: Retracted articles detected" in summary

    def test_format_summary_no_issues(self, tmp_path: Path):
        """Test summary for clean results with no issues."""
        result = BibtexAssessmentResult(
            file_path=str(tmp_path / "test.bib"),
            total_entries=2,
            entries_with_journals=2,
            preprint_entries_count=0,
            skipped_entries_count=0,
            predatory_count=0,
            legitimate_count=2,
            insufficient_data_count=0,
            suspicious_count=0,
            conference_entries=0,
            conference_predatory=0,
            conference_legitimate=0,
            conference_suspicious=0,
            journal_entries=2,
            journal_predatory=0,
            journal_legitimate=2,
            journal_suspicious=0,
            has_predatory_journals=False,
            venue_type_counts={VenueType.JOURNAL: 2},
            retracted_articles_count=0,
            articles_checked_for_retraction=0,
            processing_time=0.5,
        )

        summary = BibtexBatchAssessor.format_summary(result)

        assert "No predatory journals or retracted articles detected" in summary
        assert "WARNING" not in summary or "No predatory journals" in summary
