# SPDX-License-Identifier: MIT
"""DOAJ (Directory of Open Access Journals) data source (optional user-provided CSV)."""

import asyncio
import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ...cache import DataSourceManager
from ...enums import AssessmentType
from ...logging_config import get_detail_logger, get_status_logger
from ...normalizer import input_normalizer
from ...validation import validate_issn
from ..core import DataSource


detail_logger = get_detail_logger()
status_logger = get_status_logger()


# DOAJ has published the journal CSV under both word orderings over time:
# the current export is named "doaj_journalcsv_<date>_<time>_utf8.csv", older
# ones "journalcsv__doaj_<date>_<time>_utf8.csv". These names are documented
# for diagnostics only; detection is content-based (see _is_doaj_csv).
_KNOWN_NAMING_SCHEMES = (
    "doaj_journalcsv_*.csv",
    "journalcsv__doaj_*.csv",
)

DOAJ_CSV_HEADERS = frozenset(
    [
        "Journal title",
        "Journal URL",
        "Journal ISSN (print version)",
        "Journal EISSN (online version)",
        "Publisher",
        "Subjects",
    ]
)


class DOAJSource(DataSource):
    """Data source for DOAJ journal list (optional user-provided CSV file).

    The user can download the CSV from https://doaj.org/csv and place it in
    .aletheia-probe/doaj/ in the current working directory. Any CSV file
    in that directory with a valid DOAJ header is detected by content,
    regardless of filename. Known upstream naming schemes
    (:data:`_KNOWN_NAMING_SCHEMES`) are logged for diagnostics only.
    """

    def __init__(self, data_dir: Path | None = None) -> None:
        """Initialize DOAJ source.

        Args:
            data_dir: Directory to search for DOAJ CSV files.
                     Defaults to .aletheia-probe/doaj/ in current directory
        """
        if data_dir is None:
            data_dir = Path.cwd() / ".aletheia-probe" / "doaj"
        self.data_dir = data_dir
        self.file_path: Path | None = None

    def get_name(self) -> str:
        """Return the source identifier used for cache sync."""
        return "doaj"

    def get_list_type(self) -> AssessmentType:
        """Return assessment classification provided by DOAJ data."""
        return AssessmentType.LEGITIMATE

    def should_update(self) -> bool:
        """Check if we should update (monthly or when file is modified)."""
        if not self._find_doaj_file():
            self.skip_reason = "file_not_found"
            return False

        data_source_manager = DataSourceManager()
        last_update = data_source_manager.get_source_last_updated(self.get_name())
        if last_update is None:
            return True

        # If a newer local file was placed or modified after last sync, update immediately
        assert self.file_path is not None
        file_mtime = datetime.fromtimestamp(
            self.file_path.stat().st_mtime, tz=timezone.utc
        ).replace(tzinfo=None)
        if file_mtime > last_update:
            return True

        # Otherwise update monthly
        if (datetime.now() - last_update).days < 30:
            self.skip_reason = "already_up_to_date"
            return False

        return True

    def _is_doaj_csv(self, csv_path: Path) -> bool:
        """Check whether a CSV file has a valid DOAJ header.

        Args:
            csv_path: Path to the candidate CSV file.

        Returns:
            True if the header row contains all required DOAJ column headers.
        """
        try:
            with open(csv_path, newline="", encoding="utf-8-sig") as fh:
                reader = csv.reader(fh)
                first_row = next(reader, None)
                if first_row:
                    headers = {col.strip() for col in first_row}
                    return DOAJ_CSV_HEADERS.issubset(headers)
        except (OSError, csv.Error):
            pass
        return False

    def _find_doaj_file(self) -> bool:
        """Find the most recent DOAJ CSV file in the data directory.

        Detection is content-based: any CSV file whose header validates
        as a DOAJ export is accepted, regardless of filename.

        Returns:
            True if file found, False otherwise
        """
        if not self.data_dir.exists():
            self.data_dir.mkdir(parents=True, exist_ok=True)

        csv_files = sorted(p for p in self.data_dir.glob("*.csv") if p.is_file())

        if not csv_files:
            status_logger.info(
                f"    {self.get_name()}: No DOAJ journal list found in {self.data_dir}"
            )
            detail_logger.info(
                f"No DOAJ journal list found in {self.data_dir}. "
                "To use DOAJ data locally, download the CSV from "
                '"https://doaj.org/csv" and place it in this directory.'
            )
            return False

        valid_files = [p for p in csv_files if self._is_doaj_csv(p)]

        if not valid_files:
            status_logger.info(
                f"    {self.get_name()}: No valid DOAJ journal list found in {self.data_dir}"
            )
            names = ", ".join(p.name for p in csv_files)
            detail_logger.info(
                f"Found {len(csv_files)} CSV file(s) in {self.data_dir}, "
                f"but none have valid DOAJ headers: {names}."
            )
            return False

        if len(valid_files) > 1:
            valid_files.sort(key=lambda p: p.stat().st_mtime)
            names = ", ".join(p.name for p in valid_files)
            detail_logger.info(
                f"Multiple DOAJ CSVs found in {self.data_dir}: {names}. "
                f"Using newest by modification time: {valid_files[-1].name}."
            )

        # Use the most recent file by mtime
        self.file_path = max(valid_files, key=lambda p: p.stat().st_mtime)
        detail_logger.info(f"DOAJSource found journal list: {self.file_path.name}")
        return True

    def _validate_and_normalize_issn(
        self, issn: str | None, journal_title: str
    ) -> str | None:
        """Validate and normalize ISSN format."""
        if not issn:
            return None

        issn = issn.strip()
        if not issn:
            return None

        # Ensure hyphen format (NNNN-NNNN)
        if len(issn) == 8 and "-" not in issn:
            issn = f"{issn[:4]}-{issn[4:]}"

        if not validate_issn(issn):
            detail_logger.warning(
                f"Invalid ISSN '{issn}' for journal '{journal_title}' - skipping ISSN"
            )
            return None

        return issn

    def _parse_row(self, row: dict[str, str]) -> dict[str, Any] | None:
        """Parse a single CSV row into a journal entry dict."""
        title = row.get("Journal title", "").strip()
        if not title or len(title) < 2:
            return None

        issn_raw = row.get("Journal ISSN (print version)", "").strip() or None
        eissn_raw = row.get("Journal EISSN (online version)", "").strip() or None
        publisher = row.get("Publisher", "").strip() or None
        journal_url = row.get("Journal URL", "").strip() or None
        subjects = row.get("Subjects", "").strip() or None

        issn = self._validate_and_normalize_issn(issn_raw, title)
        eissn = self._validate_and_normalize_issn(eissn_raw, title)

        try:
            normalized_input = input_normalizer.normalize(title)
            normalized_name = (
                normalized_input.normalized_venue.name
                if normalized_input.normalized_venue
                else ""
            )
        except Exception as e:
            detail_logger.debug(f"Failed to normalize DOAJ journal '{title}': {e}")
            return None

        metadata: dict[str, Any] = {}
        if journal_url:
            metadata["journal_url"] = journal_url
        if subjects:
            metadata["subjects"] = subjects

        return {
            "journal_name": title,
            "normalized_name": normalized_name,
            "issn": issn,
            "eissn": eissn,
            "publisher": publisher,
            "metadata": metadata,
        }

    async def fetch_data(self) -> list[dict[str, Any]]:
        """Fetch and parse DOAJ journal data from CSV file."""
        if not self._find_doaj_file():
            return []

        if not self.file_path:
            return []

        status_logger.info(
            f"    {self.get_name()}: Loading journal list from {self.file_path.name}"
        )

        try:
            journals = await asyncio.to_thread(self._parse_csv)
            status_logger.info(
                f"    {self.get_name()}: Processed {len(journals)} journals"
            )
            return journals
        except Exception as e:
            status_logger.error(
                f"    {self.get_name()}: Error loading journal list - {e}"
            )
            return []

    def _parse_csv(self) -> list[dict[str, Any]]:
        """Parse the DOAJ CSV file synchronously (called via asyncio.to_thread)."""
        assert self.file_path is not None
        journals = []
        with open(self.file_path, newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                entry = self._parse_row(row)
                if entry:
                    journals.append(entry)
        return journals
