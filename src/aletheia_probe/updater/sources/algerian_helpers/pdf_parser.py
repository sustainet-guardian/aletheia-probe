"""PDF parsing utilities for Algerian Ministry data."""

import logging
import re
from pathlib import Path
from typing import Any

import pypdf

from aletheia_probe.normalizer import input_normalizer


logger = logging.getLogger(__name__)


class PDFTextExtractor:
    """Extracts and parses text from PDF files."""

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
        """
        entries = []

        try:
            with open(pdf_path, "rb") as file:
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
                    full_text, str(pdf_path), year, entry_type
                )

        except Exception as e:
            logger.error(f"Error reading PDF {pdf_path}: {e}")

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
        url_pattern = r"https?://[^\s]+"
        urls = re.findall(url_pattern, entry_text)

        # Remove URLs to get clean name
        name_text = re.sub(url_pattern, "", entry_text).strip()

        # Clean up extra spaces
        name_text = re.sub(r"\s+", " ", name_text).strip()

        if not name_text:
            return None

        # Normalize the name
        normalized_name = input_normalizer._normalize_case(name_text)

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
