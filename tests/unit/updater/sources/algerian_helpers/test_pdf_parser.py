# SPDX-License-Identifier: MIT
"""Unit tests for PDF parser."""

from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

from aletheia_probe.updater.sources.algerian_helpers.pdf_parser import PDFTextExtractor


class TestPDFTextExtractor:
    """Test suite for PDFTextExtractor class."""

    def test_extract_entry_from_text_with_url(self) -> None:
        """Test extracting entry with URL."""
        extractor = PDFTextExtractor()
        entry_text = "1 Test Journal https://example.com"

        result = extractor._extract_entry_from_text(
            entry_text, "test.pdf", 2024, "journal"
        )

        assert result is not None
        assert result["journal_name"] == "Test Journal"
        assert result["metadata"]["urls"] == ["https://example.com"]
        assert result["metadata"]["year"] == 2024

    def test_extract_entry_from_text_without_url(self) -> None:
        """Test extracting entry without URL."""
        extractor = PDFTextExtractor()
        entry_text = "1 Test Journal"

        result = extractor._extract_entry_from_text(
            entry_text, "test.pdf", 2024, "journal"
        )

        assert result is not None
        assert result["journal_name"] == "Test Journal"
        assert result["metadata"]["urls"] == []

    def test_extract_entry_from_text_empty_after_cleanup(self) -> None:
        """Test extracting entry that becomes empty after cleanup."""
        extractor = PDFTextExtractor()
        entry_text = "1 "

        result = extractor._extract_entry_from_text(
            entry_text, "test.pdf", 2024, "journal"
        )

        assert result is None

    def test_parse_entry_text_single_entry(self) -> None:
        """Test parsing text with single entry."""
        extractor = PDFTextExtractor()
        text = "1 Test Journal https://example.com"

        entries = extractor._parse_entry_text(text, "test.pdf", 2024, "journal")

        assert len(entries) == 1
        assert entries[0]["journal_name"] == "Test Journal"

    def test_parse_entry_text_multiple_entries(self) -> None:
        """Test parsing text with multiple entries."""
        extractor = PDFTextExtractor()
        text = """1 First Journal https://first.com
2 Second Journal https://second.com"""

        entries = extractor._parse_entry_text(text, "test.pdf", 2024, "journal")

        assert len(entries) == 2
        assert entries[0]["journal_name"] == "First Journal"
        assert entries[1]["journal_name"] == "Second Journal"

    def test_parse_entry_text_skips_headers(self) -> None:
        """Test that header lines are skipped."""
        extractor = PDFTextExtractor()
        text = """N°
Les Revues
1 Test Journal https://example.com"""

        entries = extractor._parse_entry_text(text, "test.pdf", 2024, "journal")

        assert len(entries) == 1
        assert entries[0]["journal_name"] == "Test Journal"

    def test_parse_entry_text_empty_text(self) -> None:
        """Test parsing empty text."""
        extractor = PDFTextExtractor()
        text = ""

        entries = extractor._parse_entry_text(text, "test.pdf", 2024, "journal")

        assert len(entries) == 0

    def test_parse_pdf_file_invalid_path(self) -> None:
        """Test parsing with invalid path raises FileNotFoundError."""
        extractor = PDFTextExtractor()

        with pytest.raises(FileNotFoundError, match="PDF file not found"):
            extractor.parse_pdf_file(Path("/nonexistent/path.pdf"), 2024)

    def test_parse_pdf_file_not_exists(self, tmp_path: Path) -> None:
        """Test parsing non-existent file raises FileNotFoundError."""
        extractor = PDFTextExtractor()
        pdf_path = tmp_path / "nonexistent.pdf"

        with pytest.raises(FileNotFoundError, match="PDF file not found"):
            extractor.parse_pdf_file(pdf_path, 2024)

    def test_parse_pdf_file_directory_not_file(self, tmp_path: Path) -> None:
        """Test parsing directory instead of file raises ValueError."""
        extractor = PDFTextExtractor()

        with pytest.raises(ValueError, match="PDF path must be a file"):
            extractor.parse_pdf_file(tmp_path, 2024)

    def test_parse_pdf_file_invalid_extension(self, tmp_path: Path) -> None:
        """Test parsing file with wrong extension raises ValueError."""
        extractor = PDFTextExtractor()
        txt_file = tmp_path / "test.txt"
        txt_file.touch()

        with pytest.raises(ValueError, match="Invalid file extension"):
            extractor.parse_pdf_file(txt_file, 2024)

    @patch("aletheia_probe.updater.sources.algerian_helpers.pdf_parser.pypdf.PdfReader")
    @patch("builtins.open", new_callable=mock_open)
    def test_parse_pdf_file_success(
        self, mock_file: MagicMock, mock_pdf_reader: MagicMock, tmp_path: Path
    ) -> None:
        """Test successful PDF parsing."""
        # Create a test PDF file
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()

        # Mock PDF page with text
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "1 Test Journal https://example.com"
        mock_pdf_reader.return_value.pages = [mock_page]

        extractor = PDFTextExtractor()
        entries = extractor.parse_pdf_file(pdf_path, 2024)

        assert len(entries) == 1
        assert entries[0]["journal_name"] == "Test Journal"

    @patch("aletheia_probe.updater.sources.algerian_helpers.pdf_parser.pypdf.PdfReader")
    @patch("builtins.open", new_callable=mock_open)
    def test_parse_pdf_file_empty_pages(
        self, mock_file: MagicMock, mock_pdf_reader: MagicMock, tmp_path: Path
    ) -> None:
        """Test parsing PDF with empty pages."""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()

        # Mock PDF page with no text
        mock_page = MagicMock()
        mock_page.extract_text.return_value = ""
        mock_pdf_reader.return_value.pages = [mock_page]

        extractor = PDFTextExtractor()
        entries = extractor.parse_pdf_file(pdf_path, 2024)

        assert len(entries) == 0
