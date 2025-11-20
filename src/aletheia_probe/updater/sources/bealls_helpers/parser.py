"""HTML parsing utilities for Beall's List."""

import re
from typing import Any

from aletheia_probe.normalizer import input_normalizer
from ....logging_config import get_detail_logger, get_status_logger

from .cleaner import JournalNameCleaner
from .validator import JournalEntryValidator

detail_logger = get_detail_logger()
status_logger = get_status_logger()


class BeallsHTMLParser:
    """Parses HTML content from Beall's List websites."""

    def __init__(self) -> None:
        self.cleaner = JournalNameCleaner()
        self.validator = JournalEntryValidator()

    def parse_beallslist_html(
        self, html_content: str, source_url: str
    ) -> list[dict[str, Any]]:
        """Parse HTML content from beallslist.net archives.

        Args:
            html_content: Raw HTML content
            source_url: URL of the source page

        Returns:
            List of parsed journal/publisher entries
        """
        journals = []

        # The structure is straightforward: <ul><li><a>Publisher Name</a> (optional info)</li></ul>
        # Extract all list items with links
        li_pattern = r'<li[^>]*>.*?<a[^>]*href="[^"]*"[^>]*>(.*?)</a>(.*?)</li>'
        matches = re.findall(li_pattern, html_content, re.DOTALL | re.IGNORECASE)

        for link_text, additional_info in matches:
            # Clean the publisher/journal name from the link text
            publisher_name = re.sub(r"<[^>]+>", "", link_text).strip()

            # Clean additional info (like "(ASJ)")
            additional_info = re.sub(r"<[^>]+>", "", additional_info).strip()

            # Extract publisher code from parentheses if present
            publisher_code = None
            if additional_info:
                # Look for pattern like "(ASJ)" or "(some code)"
                code_match = re.search(r"\(([^)]+)\)", additional_info)
                if code_match:
                    publisher_code = code_match.group(1).strip()

            if not publisher_name or len(publisher_name) < 2:
                continue

            # Clean and validate the entry
            clean_name = self.cleaner.clean_malformed_text(publisher_name)

            # For the main publishers page, we're getting publisher names, not journal names
            # But these represent organizations that publish predatory journals
            # We'll treat them as "publisher entries" and note this in metadata

            if self.validator.is_valid_publisher_entry(clean_name):
                try:
                    normalized_input = input_normalizer.normalize(clean_name)
                    journals.append(
                        {
                            "journal_name": clean_name,
                            "normalized_name": normalized_input.normalized_name,
                            "publisher": publisher_code,
                            "metadata": {
                                "source_url": source_url,
                                "entry_type": (
                                    "publisher"
                                    if "standalone" not in source_url
                                    else "journal"
                                ),
                                "raw_entry": f"{publisher_name} {additional_info}".strip(),
                            },
                        }
                    )
                except Exception as e:
                    detail_logger.debug(f"Failed to normalize publisher '{clean_name}': {e}")

        return journals

    def parse_table_content(
        self, table_html: str, source_url: str
    ) -> list[dict[str, Any]]:
        """Parse journal information from HTML table content.

        Args:
            table_html: HTML table content
            source_url: URL of the source page

        Returns:
            List of parsed journal entries
        """
        journals = []

        # Extract table rows
        row_pattern = r"<tr[^>]*>(.*?)</tr>"
        rows = re.findall(row_pattern, table_html, re.DOTALL | re.IGNORECASE)

        for row in rows:
            # Extract cell content
            cell_pattern = r"<t[dh][^>]*>(.*?)</t[dh]>"
            cells = re.findall(cell_pattern, row, re.DOTALL | re.IGNORECASE)

            if len(cells) >= 1:
                # First cell typically contains journal name
                journal_cell = re.sub(r"<[^>]+>", "", cells[0]).strip()
                publisher_cell = (
                    re.sub(r"<[^>]+>", "", cells[1]).strip() if len(cells) > 1 else None
                )

                journal_name, publisher = self._extract_journal_info(journal_cell)
                if not publisher and publisher_cell:
                    publisher = publisher_cell

                if journal_name:
                    try:
                        normalized_input = input_normalizer.normalize(journal_name)
                        journals.append(
                            {
                                "journal_name": journal_name,
                                "normalized_name": normalized_input.normalized_name,
                                "publisher": publisher,
                                "metadata": {
                                    "source_url": source_url,
                                    "table_data": True,
                                },
                            }
                        )
                    except Exception as e:
                        detail_logger.debug(
                            f"Failed to normalize table journal '{journal_name}': {e}"
                        )

        return journals

    def _extract_journal_info(self, text: str) -> tuple[str | None, str | None]:
        """Extract journal name and publisher from text entry.

        Args:
            text: Text containing journal and possibly publisher information

        Returns:
            Tuple of (journal_name, publisher) or (None, None) if invalid
        """
        text = text.strip()

        if not text or len(text) < 3:
            return None, None

        # Clean up malformed text first
        text = self.cleaner.clean_malformed_text(text)

        # Apply data quality filter
        if not self.validator.is_valid_journal_entry(text):
            return None, None

        # Common patterns to extract journal name and publisher
        # Pattern: "Journal Name (Publisher)"
        publisher_pattern = r"^(.*?)\s*\(([^)]+)\)\s*$"
        match = re.match(publisher_pattern, text)
        if match:
            journal_name = match.group(1).strip()
            publisher = match.group(2).strip()
            if self.validator.is_valid_journal_entry(journal_name):
                return journal_name, publisher

        # Pattern: "Journal Name, Publisher"
        comma_pattern = r"^(.*?),\s*([^,]+)$"
        match = re.match(comma_pattern, text)
        if match and len(match.group(2)) < 50:  # Publisher name shouldn't be too long
            journal_name = match.group(1).strip()
            publisher = match.group(2).strip()
            if self.validator.is_valid_journal_entry(journal_name):
                return journal_name, publisher

        # Pattern: "Journal Name - Publisher"
        dash_pattern = r"^(.*?)\s*-\s*([^-]+)$"
        match = re.match(dash_pattern, text)
        if match and len(match.group(2)) < 50:
            journal_name = match.group(1).strip()
            publisher = match.group(2).strip()
            if self.validator.is_valid_journal_entry(journal_name):
                return journal_name, publisher

        # Default: entire text is journal name
        return text, None
