# SPDX-License-Identifier: MIT
"""Tests for batch acronym processor module."""

import tempfile
from pathlib import Path

import pytest

from aletheia_probe.batch_acronym_processor import (
    FileProcessingResult,
    discover_bibtex_files,
    extract_acronyms_local,
    merge_file_results,
    normalize_venue_name_local,
    process_files_parallel,
    process_single_file,
)
from aletheia_probe.cache import AcronymCache
from aletheia_probe.models import BibtexEntry, VenueType


class TestNormalizeVenueNameLocal:
    """Tests for normalize_venue_name_local function."""

    def test_basic_normalization(self):
        """Test basic venue name normalization."""
        result = normalize_venue_name_local("ICML 2023")
        assert "icml" in result.lower()

    def test_proceedings_prefix_removal(self):
        """Test that 'Proceedings of' prefix is handled."""
        result = normalize_venue_name_local(
            "Proceedings of the International Conference on Machine Learning"
        )
        # Should normalize and remove proceedings prefix
        assert "proceedings of" not in result.lower()

    def test_whitespace_normalization(self):
        """Test that extra whitespace is normalized."""
        result = normalize_venue_name_local("  Some   Conference  ")
        assert "  " not in result  # No double spaces
        assert not result.startswith(" ")  # No leading space
        assert not result.endswith(" ")  # No trailing space


class TestExtractAcronymsLocal:
    """Tests for extract_acronyms_local function."""

    def test_empty_entries(self):
        """Test with empty entries list."""
        result = extract_acronyms_local([], Path("test.bib"))
        assert result.entry_count == 0
        assert len(result.mappings) == 0
        assert len(result.in_file_conflicts) == 0

    def test_entry_without_journal_name(self):
        """Test entries without journal names are skipped."""
        entries = [
            BibtexEntry(
                key="test1",
                journal_name="",
                entry_type="article",
                venue_type=VenueType.JOURNAL,
            )
        ]
        result = extract_acronyms_local(entries, Path("test.bib"))
        assert len(result.mappings) == 0

    def test_basic_acronym_extraction(self):
        """Test basic acronym extraction from venue name."""
        entries = [
            BibtexEntry(
                key="test1",
                journal_name="International Conference on Machine Learning (ICML)",
                entry_type="inproceedings",
                venue_type=VenueType.CONFERENCE,
            )
        ]
        result = extract_acronyms_local(entries, Path("test.bib"))
        # Should find ICML acronym
        acronyms = [m[0] for m in result.mappings]
        assert "ICML" in acronyms


class TestDiscoverBibtexFiles:
    """Tests for discover_bibtex_files function."""

    def test_single_file(self, tmp_path):
        """Test discovery with single file."""
        bib_file = tmp_path / "test.bib"
        bib_file.write_text("@article{test, title={Test}}")

        files = discover_bibtex_files(single_file=str(bib_file))
        assert len(files) == 1
        assert files[0] == bib_file.resolve()

    def test_directory_non_recursive(self, tmp_path):
        """Test discovery in directory without recursion."""
        # Create bib files
        (tmp_path / "a.bib").write_text("@article{a, title={A}}")
        (tmp_path / "b.bib").write_text("@article{b, title={B}}")
        # Create subdirectory with bib file
        subdir = tmp_path / "sub"
        subdir.mkdir()
        (subdir / "c.bib").write_text("@article{c, title={C}}")

        files = discover_bibtex_files(directory=str(tmp_path), recursive=False)
        assert len(files) == 2  # Only top-level files

    def test_directory_recursive(self, tmp_path):
        """Test discovery in directory with recursion."""
        # Create bib files
        (tmp_path / "a.bib").write_text("@article{a, title={A}}")
        # Create subdirectory with bib file
        subdir = tmp_path / "sub"
        subdir.mkdir()
        (subdir / "c.bib").write_text("@article{c, title={C}}")

        files = discover_bibtex_files(directory=str(tmp_path), recursive=True)
        assert len(files) == 2  # Both files found

    def test_deduplication(self, tmp_path):
        """Test that duplicate files are deduplicated."""
        bib_file = tmp_path / "test.bib"
        bib_file.write_text("@article{test, title={Test}}")

        # Pass same file twice
        files = discover_bibtex_files(
            single_file=str(bib_file),
            directory=str(tmp_path),
        )
        assert len(files) == 1

    def test_empty_directory(self, tmp_path):
        """Test with directory containing no bib files."""
        files = discover_bibtex_files(directory=str(tmp_path))
        assert len(files) == 0


class TestProcessSingleFile:
    """Tests for process_single_file function."""

    def test_valid_bibtex_file(self, tmp_path):
        """Test processing a valid BibTeX file."""
        bib_file = tmp_path / "test.bib"
        bib_file.write_text(
            """
@inproceedings{test2023,
    author = {John Doe},
    title = {Test Paper},
    booktitle = {International Conference on Machine Learning (ICML)},
    year = {2023}
}
"""
        )

        result = process_single_file(bib_file)
        assert result.error is None
        assert result.entry_count == 1
        assert result.file_path == bib_file

    def test_invalid_bibtex_file(self, tmp_path):
        """Test processing an invalid BibTeX file."""
        bib_file = tmp_path / "invalid.bib"
        bib_file.write_text("this is not valid bibtex {{{")

        result = process_single_file(bib_file)
        # Should not crash, but may have error or empty results
        assert result.file_path == bib_file

    def test_nonexistent_file(self, tmp_path):
        """Test processing a non-existent file."""
        result = process_single_file(tmp_path / "nonexistent.bib")
        assert result.error is not None


class TestProcessFilesParallel:
    """Tests for process_files_parallel function."""

    def test_empty_file_list(self):
        """Test with empty file list."""
        results = process_files_parallel([])
        assert len(results) == 0

    def test_single_file_no_parallelism(self, tmp_path):
        """Test single file doesn't use parallelism."""
        bib_file = tmp_path / "test.bib"
        bib_file.write_text("@article{test, title={Test}, journal={Nature}}")

        results = process_files_parallel([bib_file])
        assert len(results) == 1

    def test_multiple_files(self, tmp_path):
        """Test processing multiple files."""
        # Create multiple bib files
        for i in range(3):
            bib_file = tmp_path / f"test{i}.bib"
            bib_file.write_text(
                f"@article{{test{i}, title={{Test {i}}}, journal={{Journal {i}}}}}"
            )

        files = list(tmp_path.glob("*.bib"))
        results = process_files_parallel(files, max_workers=2)
        assert len(results) == 3

    def test_progress_callback(self, tmp_path):
        """Test that progress callback is called."""
        bib_file = tmp_path / "test.bib"
        bib_file.write_text("@article{test, title={Test}, journal={Nature}}")

        progress_calls = []

        def callback(completed, total, file_path):
            progress_calls.append((completed, total, file_path))

        process_files_parallel([bib_file], progress_callback=callback)
        assert len(progress_calls) == 1
        assert progress_calls[0][0] == 1  # completed
        assert progress_calls[0][1] == 1  # total


class TestMergeFileResults:
    """Tests for merge_file_results function."""

    def test_empty_results(self, isolated_test_cache):
        """Test merging empty results."""
        acronym_cache = AcronymCache(isolated_test_cache)
        merged = merge_file_results([], acronym_cache)

        assert merged.files_processed == 0
        assert len(merged.new_acronyms) == 0
        assert len(merged.conflicts) == 0

    def test_single_file_result(self, isolated_test_cache):
        """Test merging single file result."""
        acronym_cache = AcronymCache(isolated_test_cache)

        file_result = FileProcessingResult(
            file_path=Path("test.bib"),
            mappings=[
                ("ICML", "Machine Learning Conf", "machine learning conf", "conference")
            ],
            occurrence_counts={("ICML", "conference", "machine learning conf"): 1},
            entry_count=1,
        )

        merged = merge_file_results([file_result], acronym_cache)

        assert merged.files_processed == 1
        assert len(merged.new_acronyms) == 1
        assert merged.new_acronyms[0][0] == "ICML"

    def test_aggregation_across_files(self, isolated_test_cache):
        """Test that counts are aggregated across files."""
        acronym_cache = AcronymCache(isolated_test_cache)

        result1 = FileProcessingResult(
            file_path=Path("test1.bib"),
            mappings=[("ICML", "Machine Learning", "machine learning", "conference")],
            occurrence_counts={("ICML", "conference", "machine learning"): 2},
            entry_count=2,
        )
        result2 = FileProcessingResult(
            file_path=Path("test2.bib"),
            mappings=[("ICML", "Machine Learning", "machine learning", "conference")],
            occurrence_counts={("ICML", "conference", "machine learning"): 3},
            entry_count=3,
        )

        merged = merge_file_results([result1, result2], acronym_cache)

        assert merged.files_processed == 2
        assert merged.total_entries == 5
        # Should have one acronym with combined count
        assert len(merged.new_acronyms) == 1
        assert merged.new_acronyms[0][4] == 5  # Combined count

    def test_error_tracking(self, isolated_test_cache):
        """Test that file errors are tracked."""
        acronym_cache = AcronymCache(isolated_test_cache)

        result = FileProcessingResult(
            file_path=Path("error.bib"),
            error="Failed to parse",
            entry_count=0,
        )

        merged = merge_file_results([result], acronym_cache)

        assert len(merged.files_with_errors) == 1
        assert merged.files_with_errors[0][0] == Path("error.bib")
        assert "Failed to parse" in merged.files_with_errors[0][1]
