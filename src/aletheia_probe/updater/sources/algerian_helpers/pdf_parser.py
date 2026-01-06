# SPDX-License-Identifier: MIT
"""PDF parsing utilities for Algerian Ministry data."""

import re
from pathlib import Path
from typing import Any

import pypdf
import pypdf.errors

from aletheia_probe.normalizer import normalize_case

from ....config import get_config_manager
from ....logging_config import get_detail_logger, get_status_logger


detail_logger = get_detail_logger()
status_logger = get_status_logger()


class PDFTextExtractor:
    """Extracts and parses text from PDF files."""

    def __init__(self) -> None:
        """Initialize the PDFTextExtractor with configuration."""
        config = get_config_manager().load_config()
        self.url_pattern = config.data_source_processing.url_extraction_pattern

    def parse_pdf_file(
        self, pdf_path: Path, year: int, entry_type: str = "journal"
    ) -> list[dict[str, Any]]:
        """Parse PDF file to extract journal or publisher names and URLs.

        Args:
            pdf_path: Path to PDF file
            year: Year of the data
            entry_type: Type of entry ("journal" or "publisher")

        Returns:
            List of parsed entries

        Raises:
            ValueError: If the PDF file path is invalid or insecure
            FileNotFoundError: If the PDF file does not exist
            PermissionError: If the PDF file cannot be read
        """
        entries = []

        # Validate and resolve paths to prevent path traversal attacks
        try:
            pdf_file = pdf_path.resolve()
        except (OSError, RuntimeError) as e:
            detail_logger.error(f"Failed to resolve PDF path {pdf_path}: {e}")
            raise ValueError(f"Invalid PDF file path: {pdf_path}") from e

        # Security validations
        if not pdf_file.exists():
            detail_logger.error(f"PDF file does not exist: {pdf_file}")
            raise FileNotFoundError(f"PDF file not found: {pdf_file}")

        if not pdf_file.is_file():
            detail_logger.error(f"PDF path is not a file: {pdf_file}")
            raise ValueError(f"PDF path must be a file, not a directory: {pdf_file}")

        if pdf_file.suffix.lower() != ".pdf":
            detail_logger.error(f"Invalid file extension: {pdf_file}")
            raise ValueError(
                f"Invalid file extension: expected .pdf, got {pdf_file.suffix}"
            )

        # Process PDF file with specific exception handling
        try:
            with open(pdf_file, "rb") as file:
                pdf_reader = pypdf.PdfReader(file)

                # Extract text from all pages
                text_parts = []
                for page in pdf_reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)

                full_text = "\n".join(text_parts)

                # Parse the extracted text for entries
                entries = self._parse_entry_text(
                    full_text, str(pdf_file), year, entry_type
                )

        except FileNotFoundError:
            # Re-raise to caller (shouldn't happen after validation, but included for completeness)
            raise
        except PermissionError as e:
            detail_logger.error(f"Permission denied reading PDF {pdf_file}: {e}")
            raise
        except (
            pypdf.errors.PdfReadError,
            pypdf.errors.EmptyFileError,
            pypdf.errors.ParseError,
        ) as e:
            detail_logger.error(f"Failed to parse PDF {pdf_file}: {e}")
            # Return empty list for PDF parsing errors to allow processing to continue
            return []
        except OSError as e:
            detail_logger.error(f"I/O error reading PDF {pdf_file}: {e}")
            raise

        return entries

    def _parse_entry_text(
        self, text: str, source_file: str, year: int, entry_type: str = "journal"
    ) -> list[dict[str, Any]]:
        """Parse extracted text to find journal or publisher entries.

        Args:
            text: Extracted text
            source_file: Source file path
            year: Year of the data
            entry_type: Type of entry

        Returns:
            List of parsed entries
        """
        entries = []

        # Split text into lines and process
        lines = text.split("\n")
        current_entry = ""

        for line in lines:
            line = line.strip()

            # Skip empty lines and headers
            if not line or line in [
                "N°",
                "Les Revues",
                "Editeurs",
                "URL",
                "République Algérienne",
            ]:
                continue

            # Look for numbered entries (entries start with numbers)
            if re.match(r"^\d+\s+", line):
                # Process previous entry if exists
                if current_entry:
                    entry = self._extract_entry_from_text(
                        current_entry, source_file, year, entry_type
                    )
                    if entry:
                        entries.append(entry)

                # Start new entry
                current_entry = line
            else:
                # Continue current entry
                current_entry += " " + line

        # Process the last entry
        if current_entry:
            entry = self._extract_entry_from_text(
                current_entry, source_file, year, entry_type
            )
            if entry:
                entries.append(entry)

        return entries

    def _extract_entry_from_text(
        self, entry_text: str, source_file: str, year: int, entry_type: str = "journal"
    ) -> dict[str, Any] | None:
        """Extract structured data from a single entry text.

        Args:
            entry_text: Entry text
            source_file: Source file path
            year: Year of the data
            entry_type: Type of entry

        Returns:
            Structured entry data or None
        """
        # Remove number prefix and clean text
        entry_text = re.sub(r"^\d+\s+", "", entry_text).strip()

        if not entry_text:
            return None

        # Extract URLs (multiple URLs can be present)
        urls = re.findall(self.url_pattern, entry_text)

        # Remove URLs to get clean name
        name_text = re.sub(self.url_pattern, "", entry_text).strip()

        # Clean up extra spaces
        name_text = re.sub(r"\s+", " ", name_text).strip()

        if not name_text:
            return None

        # Normalize the name
        normalized_name = normalize_case(name_text)

        return {
            "journal_name": name_text,
            "normalized_name": normalized_name,
            "issn": None,  # Usually not provided in these lists
            "eissn": None,
            "publisher": None,
            "metadata": {
                "source_file": source_file,
                "year": year,
                "entry_type": entry_type,
                "urls": urls,
                "raw_entry": entry_text,
            },
        }
