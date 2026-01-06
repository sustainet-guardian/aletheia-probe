# SPDX-License-Identifier: MIT
"""Predatory Journals database data source."""

import asyncio
import csv
import io
import re
from datetime import datetime
from typing import Any

from aiohttp import ClientSession, ClientTimeout

from ...cache import DataSourceManager
from ...config import get_config_manager
from ...enums import AssessmentType
from ...logging_config import get_detail_logger, get_status_logger
from ...normalizer import input_normalizer
from ..core import DataSource
from ..utils import deduplicate_journals


detail_logger = get_detail_logger()
status_logger = get_status_logger()


class PredatoryJournalsSource(DataSource):
    """Data source for predatoryjournals.org lists.

    Fetches both the predatory journals list and the predatory publishers list
    from predatoryjournals.org Google Sheets exports.
    """

    def __init__(self) -> None:
        """Initialize the PredatoryJournalsSource.

        Sets up URLs for both journals and publishers Google Sheets exports.
        """
        # Load URLs from configuration
        config = get_config_manager().load_config()
        # Google Sheets CSV export URLs
        # Format: https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={GID}
        self.sources = {
            "journals": {
                "name": "Predatory Journals List 2025",
                "url": None,  # Will be set after discovering the sheet
                "fallback_url": config.data_source_urls.predatory_journals_fallback_url,
            },
            "publishers": {
                "name": "Predatory Publishers List 2025",
                "url": None,  # Will be set after discovering the sheet
                "fallback_url": config.data_source_urls.predatory_publishers_fallback_url,
            },
        }
        self.timeout = ClientTimeout(total=60)

    def get_name(self) -> str:
        """Return the source name.

        Returns:
            Source identifier string
        """
        return "predatoryjournals"

    def get_list_type(self) -> AssessmentType:
        """Return the list type.

        Returns:
            List type identifier (AssessmentType.PREDATORY)
        """
        return AssessmentType.PREDATORY

    def should_update(self) -> bool:
        """Check if we should update (monthly for community-maintained lists).

        Returns:
            True if update is needed, False otherwise
        """
        data_source_manager = DataSourceManager()
        last_update = data_source_manager.get_source_last_updated(self.get_name())
        if last_update is None:
            return True

        # Update monthly
        return (datetime.now() - last_update).days >= 30

    async def fetch_data(self) -> list[dict[str, Any]]:
        """Fetch predatory journals and publishers data.

        Returns:
            List of dictionaries with journal/publisher information
        """
        all_entries = []
        status_logger.info(f"    {self.get_name()}: Starting data fetch")

        async with ClientSession(timeout=self.timeout) as session:
            # Fetch journals list
            try:
                journals_url = str(self.sources["journals"]["fallback_url"])
                journals = await self._fetch_google_sheet(
                    session, "journals", journals_url
                )
                all_entries.extend(journals)
                status_logger.info(
                    f"    {self.get_name()}: Retrieved {len(journals)} journal entries"
                )
            except Exception as e:
                status_logger.error(
                    f"    {self.get_name()}: Failed to fetch journals - {e}"
                )

            # Fetch publishers list
            try:
                publishers_url = str(self.sources["publishers"]["fallback_url"])
                publishers = await self._fetch_google_sheet(
                    session, "publishers", publishers_url
                )
                all_entries.extend(publishers)
                status_logger.info(
                    f"    {self.get_name()}: Retrieved {len(publishers)} publisher entries"
                )
            except Exception as e:
                status_logger.error(
                    f"    {self.get_name()}: Failed to fetch publishers - {e}"
                )

        # Remove duplicates based on normalized name
        unique_entries = deduplicate_journals(all_entries)
        status_logger.info(
            f"    {self.get_name()}: Processed {len(unique_entries)} unique entries"
        )

        return unique_entries

    async def _fetch_google_sheet(
        self, session: ClientSession, sheet_type: str, page_url: str
    ) -> list[dict[str, Any]]:
        """Fetch and parse Google Sheet data.

        Args:
            session: HTTP session
            sheet_type: Type of sheet ('journals' or 'publishers')
            page_url: URL of the page containing the Google Sheet

        Returns:
            List of parsed entries
        """
        entries = []

        try:
            # First, try to discover the Google Sheet URL from the page
            csv_url = await self._discover_sheet_url(session, page_url)

            if csv_url:
                # Fetch the CSV data
                async with session.get(csv_url) as response:
                    if response.status == 200:
                        csv_content = await response.text()
                        entries = self._parse_csv(csv_content, sheet_type)
                    else:
                        status_logger.warning(
                            f"    {self.get_name()}: HTTP {response.status} from CSV URL"
                        )
            else:
                status_logger.warning(
                    f"    {self.get_name()}: Could not discover sheet URL from page"
                )

        except asyncio.TimeoutError:
            status_logger.error(
                f"    {self.get_name()}: Timeout fetching {sheet_type} sheet"
            )
        except Exception as e:
            status_logger.error(
                f"    {self.get_name()}: Error fetching {sheet_type} sheet - {e}"
            )

        return entries

    async def _discover_sheet_url(
        self, session: ClientSession, page_url: str
    ) -> str | None:
        """Discover the Google Sheets CSV export URL from the page.

        Args:
            session: HTTP session
            page_url: URL of the page containing the embedded sheet

        Returns:
            CSV export URL if found, None otherwise
        """
        try:
            async with session.get(page_url) as response:
                if response.status == 200:
                    html = await response.text()

                    # Look for Google Sheets URLs in the HTML
                    # Pattern for embedded Google Sheets
                    sheet_pattern = (
                        r"https://docs\.google\.com/spreadsheets/d/([a-zA-Z0-9-_]+)"
                    )
                    matches = re.findall(sheet_pattern, html)

                    if matches:
                        sheet_id = matches[0]
                        # Convert to CSV export URL
                        csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
                        detail_logger.info(f"Discovered Google Sheet: {csv_url}")
                        return csv_url

        except Exception as e:
            status_logger.error(
                f"    {self.get_name()}: Error discovering sheet URL - {e}"
            )

        return None

    def _parse_csv(self, csv_content: str, sheet_type: str) -> list[dict[str, Any]]:
        """Parse CSV content into journal/publisher entries.

        Args:
            csv_content: CSV data as string
            sheet_type: Type of sheet ('journals' or 'publishers')

        Returns:
            List of parsed entries
        """
        entries = []

        try:
            csv_reader = csv.DictReader(io.StringIO(csv_content))

            for row in csv_reader:
                # Skip empty rows
                if not any(row.values()):
                    continue

                entry = self._parse_row(row, sheet_type)
                if entry:
                    entries.append(entry)

        except Exception as e:
            status_logger.error(
                f"    {self.get_name()}: Error parsing CSV for {sheet_type} - {e}"
            )

        return entries

    def _extract_name_from_row(self, row: dict[str, Any]) -> str | None:
        """Extract journal/publisher name from CSV row.

        Args:
            row: CSV row as dictionary

        Returns:
            Extracted name or None if no valid name found
        """
        # Try to extract journal/publisher name from common column names
        name = None
        for possible_name_col in [
            "Journal Name",
            "Journal",
            "Name",
            "Title",
            "Publisher Name",
            "Publisher",
            "journal_name",
            "publisher_name",
            "name",
            "title",
        ]:
            if possible_name_col in row and row[possible_name_col]:
                name = row[possible_name_col].strip()
                break

        if not name:
            # If no recognized column, use the first non-numeric, substantive value
            # Skip numeric-only values (row numbers) and very short values
            for _col_name, value in row.items():
                if value and isinstance(value, str):
                    stripped = value.strip()
                    # Skip if it's just a number (row index)
                    if stripped.isdigit():
                        continue
                    # Skip very short values (likely not journal names)
                    if len(stripped) < 3:
                        continue
                    # Skip common column headers that aren't journal names
                    if stripped.lower() in [
                        "journal",
                        "publisher",
                        "issn",
                        "eissn",
                        "name",
                    ]:
                        continue
                    name = stripped
                    break

        return name

    def _extract_issn_from_row(self, row: dict[str, Any]) -> str | None:
        """Extract ISSN from CSV row.

        Args:
            row: CSV row as dictionary

        Returns:
            Extracted ISSN or None if not found
        """
        for possible_issn_col in ["ISSN", "issn", "Print ISSN", "print_issn"]:
            if possible_issn_col in row and row[possible_issn_col]:
                return str(row[possible_issn_col]).strip()
        return None

    def _extract_eissn_from_row(self, row: dict[str, Any]) -> str | None:
        """Extract eISSN from CSV row.

        Args:
            row: CSV row as dictionary

        Returns:
            Extracted eISSN or None if not found
        """
        for possible_eissn_col in [
            "eISSN",
            "eissn",
            "Online ISSN",
            "online_issn",
            "E-ISSN",
        ]:
            if possible_eissn_col in row and row[possible_eissn_col]:
                return str(row[possible_eissn_col]).strip()
        return None

    def _extract_publisher_from_row(
        self, row: dict[str, Any], sheet_type: str
    ) -> str | None:
        """Extract publisher from CSV row for journal entries.

        Args:
            row: CSV row as dictionary
            sheet_type: Type of sheet ('journals' or 'publishers')

        Returns:
            Extracted publisher or None if not found or not applicable
        """
        if sheet_type != "journals":
            return None

        for possible_pub_col in [
            "Publisher",
            "publisher",
            "Publisher Name",
            "publisher_name",
        ]:
            if possible_pub_col in row and row[possible_pub_col]:
                return str(row[possible_pub_col]).strip()
        return None

    def _parse_row(self, row: dict[str, Any], sheet_type: str) -> dict[str, Any] | None:
        """Parse a single CSV row into an entry.

        Args:
            row: CSV row as dictionary
            sheet_type: Type of sheet ('journals' or 'publishers')

        Returns:
            Parsed entry dictionary or None if invalid
        """
        # Extract name from row
        name = self._extract_name_from_row(row)
        if not name:
            return None

        # Extract ISSNs and publisher
        issn = self._extract_issn_from_row(row)
        eissn = self._extract_eissn_from_row(row)
        publisher = self._extract_publisher_from_row(row, sheet_type)

        # Create entry
        try:
            normalized_input = input_normalizer.normalize(name)
            entry = {
                "journal_name": name,
                "normalized_name": normalized_input.normalized_name,
                "metadata": {
                    "source": "predatoryjournals.org",
                    "list_type": sheet_type,
                    "raw_data": dict(row),
                },
            }
        except Exception as e:
            detail_logger.debug(f"Failed to normalize entry '{name}': {e}")
            return None

        if issn:
            entry["issn"] = issn
        if eissn:
            entry["eissn"] = eissn
        if publisher:
            entry["publisher"] = publisher

        return entry
