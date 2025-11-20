"""Algerian Ministry of Higher Education predatory journal list data source."""

import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from aiohttp import ClientSession, ClientTimeout

from ...cache import get_cache_manager
from ...config import get_config_manager
from ...logging_config import get_detail_logger, get_status_logger
from ..core import DataSource
from .algerian_helpers import PDFTextExtractor, RARDownloader, RARExtractor


detail_logger = get_detail_logger()
status_logger = get_status_logger()


class AlgerianMinistrySource(DataSource):
    """Data source for Algerian Ministry of Higher Education predatory journal lists."""

    def __init__(self) -> None:
        # Load URLs from configuration
        config = get_config_manager().load_config()
        url_config = config.data_source_urls

        # Construct the full base URL from config
        self.base_url = (
            f"{url_config.algerian_ministry_base_url}"
            "Liste%20des%20Revues%20Pr%C3%A9datrices,%20Editeurs%20pr%C3%A9dateurs"
        )
        self.current_year = datetime.now().year
        self.timeout = ClientTimeout(
            total=300
        )  # 5 minutes timeout for large RAR files (18MB+)

        # Initialize helper classes
        self.downloader = RARDownloader()
        self.extractor = RARExtractor()
        self.pdf_parser = PDFTextExtractor()

    def get_name(self) -> str:
        return "algerian_ministry"

    def get_list_type(self) -> str:
        return "predatory"

    def should_update(self) -> bool:
        """Check if we should update (monthly checks for new year data)."""
        last_update = get_cache_manager().get_source_last_updated(self.get_name())
        if last_update is None:
            return True

        # Update monthly (more frequent than Bealls due to active maintenance)
        return (datetime.now() - last_update).days >= 30

    async def fetch_data(self) -> list[dict[str, Any]]:
        """Fetch and process Algerian predatory journal data from RAR archives."""
        all_journals = []
        status_logger.info(f"    {self.get_name()}: Starting data fetch")

        # Try 2024 first (known to exist), then current year if different, then previous year
        years_to_try = []
        if self.current_year != 2024:
            years_to_try = [2024, self.current_year, self.current_year - 1]
        else:
            years_to_try = [2024, 2023]

        detail_logger.info(
            f"Algerian Ministry: Will try years in order: {years_to_try}"
        )

        for year in years_to_try:
            try:
                status_logger.info(
                    f"    {self.get_name()}: Attempting to fetch data for year {year}"
                )
                detail_logger.info(
                    f"Algerian Ministry: Starting download for year {year}"
                )
                journals = await self._fetch_year_data(year)
                if journals:
                    all_journals.extend(journals)
                    detail_logger.info(
                        f"Successfully processed {len(journals)} journals from {year}"
                    )
                    status_logger.info(
                        f"    {self.get_name()}: Retrieved {len(journals)} journals from {year}"
                    )
                    break  # Stop after first successful year
            except Exception as e:
                status_logger.warning(
                    f"    {self.get_name()}: Failed to fetch data for {year}: {e}"
                )
                detail_logger.exception(
                    f"Algerian Ministry: Detailed error for {year}: {e}"
                )

        if not all_journals:
            detail_logger.error("Failed to fetch Algerian data for any year")
            status_logger.error(
                f"    {self.get_name()}: Failed to fetch data for any year"
            )

        return self._deduplicate_journals(all_journals)

    async def _fetch_year_data(self, year: int) -> list[dict[str, Any]]:
        """Fetch and process data for a specific year.

        Args:
            year: Year to fetch data for

        Returns:
            List of journal entries
        """
        url = f"{self.base_url}/{year}.rar"
        detail_logger.info(f"Algerian Ministry: Downloading RAR file from {url}")

        with tempfile.TemporaryDirectory() as temp_dir:
            # Download RAR file
            detail_logger.info("Algerian Ministry: Starting RAR download...")
            rar_path = await self._download_rar(url, temp_dir)
            if not rar_path:
                detail_logger.warning("Algerian Ministry: RAR download failed")
                status_logger.warning(f"    {self.get_name()}: RAR download failed")
                return []

            detail_logger.info(
                "Algerian Ministry: RAR downloaded, starting extraction..."
            )

            # Extract RAR contents
            extract_dir = self._extract_rar(rar_path, temp_dir)
            if not extract_dir:
                detail_logger.warning("Algerian Ministry: RAR extraction failed")
                status_logger.warning(f"    {self.get_name()}: RAR extraction failed")
                return []

            detail_logger.info(
                "Algerian Ministry: RAR extracted, processing PDF files..."
            )

            # Find and process PDF files
            return self._process_pdf_files(extract_dir, year)

    async def _download_rar(self, url: str, temp_dir: str) -> str | None:
        """Download RAR file to temporary directory.

        Args:
            url: URL of the RAR file
            temp_dir: Temporary directory path

        Returns:
            Path to downloaded RAR file, or None if failed
        """
        async with ClientSession(timeout=self.timeout) as session:
            result: str | None = await self.downloader.download_rar(
                session, url, temp_dir
            )
            return result

    def _extract_rar(self, rar_path: str, temp_dir: str) -> str | None:
        """Extract RAR file using command line tool.

        Args:
            rar_path: Path to RAR file
            temp_dir: Temporary directory

        Returns:
            Path to extraction directory, or None if failed
        """
        return self.extractor.extract_rar(rar_path, temp_dir)

    def _process_pdf_files(self, extract_dir: str, year: int) -> list[dict[str, Any]]:
        """Process PDF files to extract journal and publisher lists from the target year only.

        Args:
            extract_dir: Directory containing extracted files
            year: Year of the data

        Returns:
            List of journal entries
        """
        all_entries = []
        extract_path = Path(extract_dir)

        # Navigate to the actual year directory (may be nested)
        # The structure is often: extracted/2024/2024/2024/ for the current year
        possible_year_dirs = [
            extract_path / str(year) / str(year) / str(year),  # nested structure
            extract_path / str(year) / str(year),  # double nested
            extract_path / str(year),  # simple structure
        ]

        year_dir = None
        for candidate in possible_year_dirs:
            if candidate.exists():
                year_dir = candidate
                break

        if not year_dir:
            detail_logger.warning(f"No directory found for year {year}")
            status_logger.warning(
                f"    {self.get_name()}: No directory found for year {year}"
            )
            return []

        detail_logger.info(f"Processing files from: {year_dir}")

        # Find PDF files containing both journals and publishers from the target year only
        target_patterns = [
            "Liste des revues*.pdf",  # Journal lists
            "Actualisation*.pdf",  # Updated journal lists
            "Liste des éditeurs*.pdf",  # Publisher lists
        ]

        for pattern in target_patterns:
            for pdf_file in year_dir.glob(pattern):
                try:
                    detail_logger.info(f"Processing PDF: {pdf_file.name}")

                    # Determine entry type based on filename
                    entry_type = (
                        "journal"
                        if (
                            "revues" in pdf_file.name.lower()
                            or "actualisation" in pdf_file.name.lower()
                        )
                        else "publisher"
                    )

                    entries = self.pdf_parser.parse_pdf_file(pdf_file, year, entry_type)
                    all_entries.extend(entries)
                    detail_logger.info(
                        f"Extracted {len(entries)} {entry_type}s from {pdf_file.name}"
                    )
                except Exception as e:
                    detail_logger.error(f"Error processing PDF {pdf_file}: {e}")
                    status_logger.error(
                        f"    {self.get_name()}: Error processing PDF {pdf_file.name} - {e}"
                    )

        return all_entries

    def _deduplicate_journals(
        self, journals: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Remove duplicate journals based on normalized name.

        Args:
            journals: List of journal entries

        Returns:
            Deduplicated list
        """
        seen_names = set()
        unique_journals = []

        for journal in journals:
            normalized_name = journal.get("normalized_name")
            if normalized_name and normalized_name not in seen_names:
                seen_names.add(normalized_name)
                unique_journals.append(journal)

        return unique_journals
