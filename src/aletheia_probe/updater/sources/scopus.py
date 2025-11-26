# SPDX-License-Identifier: MIT
"""Scopus journal list data source (optional user-provided Excel file)."""

import asyncio
import glob
from datetime import datetime
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from ...cache import get_cache_manager
from ...enums import AssessmentType
from ...logging_config import get_detail_logger, get_status_logger
from ...normalizer import input_normalizer
from ...validation import validate_issn
from ..core import DataSource


detail_logger = get_detail_logger()
status_logger = get_status_logger()


class ScopusSource(DataSource):
    """Data source for Scopus journal list (optional user-provided Excel file)."""

    def __init__(self, data_dir: Path | None = None) -> None:
        """Initialize Scopus source.

        Args:
            data_dir: Directory to search for Scopus files.
                     Defaults to .aletheia-probe/scopus/ in current directory
        """
        if data_dir is None:
            data_dir = Path.cwd() / ".aletheia-probe" / "scopus"
        self.data_dir = data_dir
        self.file_path: Path | None = None

    def get_name(self) -> str:
        return "scopus"

    def get_list_type(self) -> AssessmentType:
        return AssessmentType.LEGITIMATE

    def should_update(self) -> bool:
        """Check if we should update (monthly for static file)."""
        # First check if file exists - message will be shown to user via click.echo
        if not self._find_scopus_file():
            return False

        last_update = get_cache_manager().get_source_last_updated(self.get_name())
        if last_update is None:
            return True

        # Update monthly
        return (datetime.now() - last_update).days >= 30

    def _find_scopus_file(self) -> bool:
        """Find the most recent Scopus Excel file in the data directory.

        Returns:
            True if file found, False otherwise
        """
        if not self.data_dir.exists():
            self.data_dir.mkdir(parents=True, exist_ok=True)

        # Look for ext_list_*.xlsx files
        pattern = str(self.data_dir / "ext_list_*.xlsx")
        matching_files = glob.glob(pattern)

        if not matching_files:
            detail_logger.debug(
                f"No Scopus journal list found in {self.data_dir}. "
                "To use Scopus data, download the latest list from "
                '"https://www.researchgate.net/publication/384898389_Last_Update_of_Scopus_Indexed_Journal\'s_List_-_October_2024" '
                "and place it in this directory."
            )
            return False

        # Use the most recent file
        self.file_path = Path(
            max(matching_files, key=lambda p: Path(p).stat().st_mtime)
        )
        status_logger.info(
            f"    {self.get_name()}: Found journal list: {self.file_path.name}"
        )
        return True

    async def fetch_data(self) -> list[dict[str, Any]]:
        """Fetch and parse Scopus journal data from Excel file."""
        if not self._find_scopus_file():
            status_logger.info(f"    {self.get_name()}: File not found, skipping")
            return []

        if not self.file_path:
            return []

        status_logger.info(
            f"    {self.get_name()}: Loading journal list from {self.file_path.name}"
        )

        try:
            # Load workbook in thread pool to avoid blocking event loop
            workbook = await asyncio.to_thread(
                load_workbook, filename=self.file_path, read_only=True, data_only=True
            )

            # Find the sheet (usually "Scopus Sources Oct. 2024" or similar)
            sheet = None
            for sheet_name in workbook.sheetnames:
                if "scopus" in sheet_name.lower() or "source" in sheet_name.lower():
                    sheet = workbook[sheet_name]
                    break

            if sheet is None:
                # Fallback to first sheet
                sheet = workbook.active

            if sheet is None:
                status_logger.error(
                    f"    {self.get_name()}: No valid sheet found in Excel file"
                )
                return []

            detail_logger.info(f"Reading sheet: {sheet.title}")

            # Read header row to find column indices
            rows_iter = iter(sheet.rows)
            header_row = next(rows_iter)
            headers = [cell.value for cell in header_row]

            # Find column indices
            col_indices = {}
            for i, header in enumerate(headers):
                if header:
                    header_lower = str(header).lower()
                    if "source title" in header_lower or header_lower == "title":
                        col_indices["title"] = i
                    elif header_lower == "issn":
                        col_indices["issn"] = i
                    elif header_lower == "eissn" or header_lower == "e-issn":
                        col_indices["eissn"] = i
                    elif "publisher" in header_lower:
                        col_indices["publisher"] = i
                    elif "active or inactive" in header_lower:
                        col_indices["status"] = i
                    elif "discontinued" in header_lower and "quality" in header_lower:
                        col_indices["quality_flag"] = i
                    elif "source type" in header_lower:
                        col_indices["source_type"] = i
                    elif "coverage" in header_lower:
                        col_indices["coverage"] = i
                    elif "open access" in header_lower:
                        col_indices["open_access"] = i

            # Validate required columns exist
            if "title" not in col_indices:
                status_logger.error(
                    f"    {self.get_name()}: Could not find 'Source Title' column in file"
                )
                return []

            detail_logger.info(f"Found columns: {list(col_indices.keys())}")

            journals = []
            active_count = 0
            inactive_count = 0
            quality_flagged_count = 0

            # Process data rows
            for row in rows_iter:
                # Extract values
                title = (
                    row[col_indices["title"]].value if "title" in col_indices else None
                )
                issn = row[col_indices["issn"]].value if "issn" in col_indices else None
                eissn = (
                    row[col_indices["eissn"]].value if "eissn" in col_indices else None
                )
                publisher = (
                    row[col_indices["publisher"]].value
                    if "publisher" in col_indices
                    else None
                )
                status = (
                    row[col_indices["status"]].value
                    if "status" in col_indices
                    else None
                )
                quality_flag = (
                    row[col_indices["quality_flag"]].value
                    if "quality_flag" in col_indices
                    else None
                )
                source_type = (
                    row[col_indices["source_type"]].value
                    if "source_type" in col_indices
                    else None
                )
                coverage = (
                    row[col_indices["coverage"]].value
                    if "coverage" in col_indices
                    else None
                )
                open_access = (
                    row[col_indices["open_access"]].value
                    if "open_access" in col_indices
                    else None
                )

                # Skip rows without title
                if not title:
                    continue

                title = str(title).strip()
                if not title or len(title) < 2:
                    continue

                # Track statistics
                status_str = str(status).strip() if status else ""
                is_active = status_str.lower() == "active"
                is_quality_flagged = quality_flag and str(quality_flag).strip()

                if is_active:
                    active_count += 1
                else:
                    inactive_count += 1

                if is_quality_flagged:
                    quality_flagged_count += 1

                # Only include active journals (skip inactive ones)
                if not is_active:
                    continue

                # Normalize and validate ISSN format
                if issn:
                    issn = str(issn).strip()
                    # Ensure hyphen format (NNNN-NNNN)
                    if len(issn) == 8 and "-" not in issn:
                        issn = f"{issn[:4]}-{issn[4:]}"
                    # Validate ISSN checksum
                    if not validate_issn(issn):
                        detail_logger.warning(
                            f"Invalid ISSN '{issn}' for journal '{title}' - skipping ISSN"
                        )
                        issn = None

                if eissn:
                    eissn = str(eissn).strip()
                    if len(eissn) == 8 and "-" not in eissn:
                        eissn = f"{eissn[:4]}-{eissn[4:]}"
                    # Validate e-ISSN checksum
                    if not validate_issn(eissn):
                        detail_logger.warning(
                            f"Invalid e-ISSN '{eissn}' for journal '{title}' - skipping e-ISSN"
                        )
                        eissn = None

                # Normalize journal name
                try:
                    normalized_input = input_normalizer.normalize(title)

                    metadata: dict[str, Any] = {
                        "source_type": (
                            str(source_type).strip() if source_type else "Journal"
                        ),
                        "coverage": str(coverage).strip() if coverage else None,
                        "open_access": (
                            str(open_access).strip() if open_access else None
                        ),
                    }

                    # Add quality flag if present
                    if is_quality_flagged:
                        metadata["quality_flagged"] = True
                        metadata["quality_flag_reason"] = (
                            str(quality_flag).strip() if quality_flag else None
                        )

                    journals.append(
                        {
                            "journal_name": title,
                            "normalized_name": normalized_input.normalized_name,
                            "issn": issn,
                            "eissn": eissn,
                            "publisher": str(publisher).strip() if publisher else None,
                            "metadata": metadata,
                        }
                    )

                except Exception as e:
                    detail_logger.debug(f"Failed to process journal '{title}': {e}")

            workbook.close()

            status_logger.info(
                f"    {self.get_name()}: Processed {len(journals)} active journals "
                f"({inactive_count} inactive excluded, {quality_flagged_count} quality-flagged found)"
            )

            return journals

        except Exception as e:
            status_logger.error(
                f"    {self.get_name()}: Error loading journal list - {e}"
            )
            return []
