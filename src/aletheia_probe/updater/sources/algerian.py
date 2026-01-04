# SPDX-License-Identifier: MIT
"""Algerian Ministry of Higher Education predatory journal list data source."""

import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from aiohttp import ClientSession, ClientTimeout

from ...cache import DataSourceManager
from ...config import get_config_manager
from ...enums import AssessmentType
from ...logging_config import get_detail_logger, get_status_logger
from ..core import DataSource
from ..utils import deduplicate_journals
from .algerian_helpers import ArchiveDownloader, ArchiveExtractor, PDFTextExtractor


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
        self.downloader = ArchiveDownloader()
        self.extractor = ArchiveExtractor()
        self.pdf_parser = PDFTextExtractor()

    def get_name(self) -> str:
        return "algerian_ministry"

    def get_list_type(self) -> AssessmentType:
        return AssessmentType.PREDATORY

    def should_update(self) -> bool:
        """Check if we should update (monthly checks for new year data)."""
        data_source_manager = DataSourceManager()
        last_update = data_source_manager.get_source_last_updated(self.get_name())
        if last_update is None:
            return True

        # Update monthly (more frequent than Bealls due to active maintenance)
        return (datetime.now() - last_update).days >= 30

    async def fetch_data(self) -> list[dict[str, Any]]:
        """Fetch and process Algerian predatory journal data from archives (RAR/ZIP)."""
        all_journals = []
        status_logger.info(f"    {self.get_name()}: Starting data fetch")

        # Try current year first, then previous years
        # Note: 2022+ are in ZIP format, older years are in RAR format
        years_to_try = []
        if self.current_year >= 2024:
            years_to_try = [2024, 2023, 2022]
        else:
            years_to_try = [self.current_year, self.current_year - 1]

        detail_logger.info(
            f"Algerian Ministry: Will try years in order: {years_to_try}"
        )

        for year in years_to_try:
            # Determine format: ZIP for 2022+, RAR for earlier years
            file_format = "zip" if year >= 2022 else "rar"

            try:
                status_logger.info(
                    f"    {self.get_name()}: Attempting to fetch data for year {year} ({file_format.upper()} format)"
                )
                detail_logger.info(
                    f"Algerian Ministry: Starting download for year {year} ({file_format.upper()} format)"
                )
                journals = await self._fetch_year_data(year, file_format)
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

        return deduplicate_journals(all_journals)

    async def _fetch_year_data(
        self, year: int, file_format: str = "rar"
    ) -> list[dict[str, Any]]:
        """Fetch and process data for a specific year.

        Args:
            year: Year to fetch data for
            file_format: Archive format ("rar" or "zip")

        Returns:
            List of journal entries
        """
        url = f"{self.base_url}/{year}.{file_format}"
        detail_logger.info(
            f"Algerian Ministry: Downloading {file_format.upper()} file from {url}"
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            # Download archive file
            detail_logger.info(
                f"Algerian Ministry: Starting {file_format.upper()} download..."
            )
            archive_path = await self._download_archive(url, temp_dir, file_format)
            if not archive_path:
                detail_logger.warning(
                    f"Algerian Ministry: {file_format.upper()} download failed"
                )
                status_logger.warning(
                    f"    {self.get_name()}: {file_format.upper()} download failed"
                )
                return []

            detail_logger.info(
                f"Algerian Ministry: {file_format.upper()} downloaded, starting extraction..."
            )

            # Extract archive contents
            extract_dir = await self._extract_archive(
                archive_path, temp_dir, file_format
            )
            if not extract_dir:
                detail_logger.warning(
                    f"Algerian Ministry: {file_format.upper()} extraction failed"
                )
                status_logger.warning(
                    f"    {self.get_name()}: {file_format.upper()} extraction failed"
                )
                return []

            detail_logger.info(
                f"Algerian Ministry: {file_format.upper()} extracted, processing PDF files..."
            )

            # Find and process PDF files
            return self._process_pdf_files(extract_dir, year)

    async def _download_archive(
        self, url: str, temp_dir: str, file_format: str
    ) -> str | None:
        """Download archive file to temporary directory.

        Args:
            url: URL of the archive file
            temp_dir: Temporary directory path
            file_format: Archive format ("rar" or "zip")

        Returns:
            Path to downloaded archive file, or None if failed
        """
        async with ClientSession(timeout=self.timeout) as session:
            result: str | None = await self.downloader.download_archive(
                session, url, temp_dir, f".{file_format}"
            )
            return result

    async def _extract_archive(
        self, archive_path: str, temp_dir: str, file_format: str
    ) -> str | None:
        """Extract archive file using appropriate extractor.

        Args:
            archive_path: Path to archive file
            temp_dir: Temporary directory
            file_format: Archive format ("rar" or "zip")

        Returns:
            Path to extraction directory, or None if failed
        """
        if file_format == "zip":
            return await self.extractor.extract_zip(archive_path, temp_dir)
        else:
            return await self.extractor.extract_rar(archive_path, temp_dir)

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
