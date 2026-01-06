# SPDX-License-Identifier: MIT
"""Unit tests for PDF parser."""

from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

from aletheia_probe.updater.sources.algerian_helpers.pdf_parser import PDFTextExtractor


class TestPDFTextExtractor:
    """Test suite for PDFTextExtractor class."""

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
    def test_parse_pdf_file_single_entry(
        self, mock_file: MagicMock, mock_pdf_reader: MagicMock, tmp_path: Path
    ) -> None:
        """Test parsing PDF with single entry."""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()

        mock_page = MagicMock()
        mock_page.extract_text.return_value = "1 Test Journal https://example.com"
        mock_pdf_reader.return_value.pages = [mock_page]

        extractor = PDFTextExtractor()
        entries = extractor.parse_pdf_file(pdf_path, 2024)

        assert len(entries) == 1
        assert entries[0]["journal_name"] == "Test Journal"

    @patch("aletheia_probe.updater.sources.algerian_helpers.pdf_parser.pypdf.PdfReader")
    @patch("builtins.open", new_callable=mock_open)
    def test_parse_pdf_file_multiple_entries(
        self, mock_file: MagicMock, mock_pdf_reader: MagicMock, tmp_path: Path
    ) -> None:
        """Test parsing PDF with multiple entries."""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()

        mock_page = MagicMock()
        mock_page.extract_text.return_value = "1 First Journal\n2 Second Journal"
        mock_pdf_reader.return_value.pages = [mock_page]

        extractor = PDFTextExtractor()
        entries = extractor.parse_pdf_file(pdf_path, 2024)

        assert len(entries) == 2

    @patch("aletheia_probe.updater.sources.algerian_helpers.pdf_parser.pypdf.PdfReader")
    @patch("builtins.open", new_callable=mock_open)
    def test_parse_pdf_file_empty_content(
        self, mock_file: MagicMock, mock_pdf_reader: MagicMock, tmp_path: Path
    ) -> None:
        """Test parsing PDF with empty content."""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()

        mock_page = MagicMock()
        mock_page.extract_text.return_value = ""
        mock_pdf_reader.return_value.pages = [mock_page]

        extractor = PDFTextExtractor()
        entries = extractor.parse_pdf_file(pdf_path, 2024)

        assert len(entries) == 0
