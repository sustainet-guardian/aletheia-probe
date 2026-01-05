# SPDX-License-Identifier: MIT
"""Retraction Watch database data source from GitLab."""

import asyncio
import csv
import subprocess
import tempfile
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ...cache import DataSourceManager
from ...config import get_config_manager
from ...enums import AssessmentType
from ...logging_config import get_detail_logger, get_status_logger
from ...normalizer import input_normalizer
from ...risk_calculator import calculate_retraction_risk_level
from ..core import DataSource


detail_logger = get_detail_logger()
status_logger = get_status_logger()


class RetractionWatchSource(DataSource):
    """Data source for Retraction Watch database from GitLab."""

    def __init__(self) -> None:
        # Load URLs from configuration
        config = get_config_manager().load_config()
        url_config = config.data_source_urls

        self.repo_url = url_config.retraction_watch_repo_url
        self.csv_filename = url_config.retraction_watch_csv_filename
        self.article_retractions: list[dict[str, Any]] = []

    def get_name(self) -> str:
        return "retraction_watch"

    def get_list_type(self) -> AssessmentType:
        return AssessmentType.QUALITY_INDICATOR

    def should_update(self) -> bool:
        """Check if we should update (weekly for retraction data)."""
        data_source_manager = DataSourceManager()
        last_update = data_source_manager.get_source_last_updated(self.get_name())
        if last_update is None:
            return True

        # Update weekly (data updated daily upstream, but weekly is sufficient)
        return (datetime.now() - last_update).days >= 7

    async def fetch_data(self) -> list[dict[str, Any]]:
        """Fetch and aggregate retraction data from GitLab repository."""
        status_logger.info(f"    {self.get_name()}: Starting data fetch")

        with tempfile.TemporaryDirectory() as temp_dir:
            # Clone the repository
            repo_path = await self._clone_repository(temp_dir)
            if not repo_path:
                status_logger.error(
                    f"    {self.get_name()}: Failed to clone repository"
                )
                return []

            # Find and parse the CSV file
            csv_path = repo_path / self.csv_filename
            if not csv_path.exists():
                status_logger.error(f"    {self.get_name()}: CSV file not found")
                return []

            # Parse and aggregate the data
            journals = await self._parse_and_aggregate_csv(csv_path)
            status_logger.info(
                f"    {self.get_name()}: Aggregated data for {len(journals)} journals"
            )

            return journals

    async def _clone_repository(self, temp_dir: str) -> Path | None:
        """Clone the Retraction Watch Git repository.

        Args:
            temp_dir: Temporary directory for cloning

        Returns:
            Path to cloned repository, or None if cloning failed
        """
        # Validate and sanitize temp directory path
        temp_directory = Path(temp_dir).resolve()

        if not temp_directory.exists():
            detail_logger.error(f"Temp directory does not exist: {temp_directory}")
            return None

        if not temp_directory.is_dir():
            detail_logger.error(f"Not a directory: {temp_directory}")
            return None

        repo_path = temp_directory / "retraction-watch-data"

        # Ensure repo_path is within temp_directory (prevent path traversal)
        try:
            repo_path.resolve().relative_to(temp_directory.resolve())
        except ValueError:
            detail_logger.error(
                f"Repository path is outside temp directory: {repo_path}"
            )
            return None

        try:
            detail_logger.info(f"Cloning repository: {self.repo_url}")

            # Use depth=1 for faster cloning (we only need latest)
            # Use absolute path to prevent command injection
            def _run_git_clone() -> subprocess.CompletedProcess[str]:
                return subprocess.run(
                    ["git", "clone", "--depth", "1", self.repo_url, str(repo_path)],
                    capture_output=True,
                    text=True,
                    timeout=300,  # 5 minute timeout
                )

            result = await asyncio.to_thread(_run_git_clone)

            if result.returncode == 0:
                detail_logger.info(f"Successfully cloned repository to {repo_path}")
                return repo_path
            else:
                detail_logger.error(f"Git clone failed: {result.stderr}")
                return None

        except subprocess.TimeoutExpired:
            detail_logger.error("Git clone timed out after 5 minutes")
            return None
        except Exception as e:
            detail_logger.error(f"Error cloning repository: {e}")
            return None

    async def _parse_and_aggregate_csv(self, csv_path: Path) -> list[dict[str, Any]]:
        """Parse CSV and aggregate retractions by journal."""
        # Reset article retractions list for this sync
        self.article_retractions = []

        journal_stats: defaultdict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "total_retractions": 0,
                "recent_retractions": 0,  # last 2 years
                "very_recent_retractions": 0,  # last 1 year
                "retraction_dates": [],
                "retraction_types": defaultdict(int),
                "reasons": [],
                "publishers": set(),
                "original_names": set(),
                "first_date": None,
                "last_date": None,
            }
        )

        # Process CSV rows and collect statistics
        articles_cached = await self._process_csv_rows(csv_path, journal_stats)

        # Convert aggregated stats to journal list format
        journals = self._build_journals_from_stats(journal_stats)

        status_logger.info(
            f"    {self.get_name()}: Aggregating journal statistics: {len(journals):,} journals found"
        )
        detail_logger.info(f"Aggregated {len(journals)} journals from retraction data")

        # Convert to final format without OpenAlex enrichment
        final_journals = self._convert_to_final_format(journals)

        status_logger.info(
            f"    {self.get_name()}: Retraction data processing complete: {len(final_journals):,} journals, {articles_cached:,} article DOIs collected"
        )
        detail_logger.info(
            "Retraction data aggregation complete (OpenAlex data will be fetched on-demand)"
        )

        # Store article retractions in metadata for AsyncDBWriter to process
        self._attach_article_retractions(final_journals)

        return final_journals

    async def _process_csv_rows(
        self,
        csv_path: Path,
        journal_stats: defaultdict[str, dict[str, Any]],
    ) -> int:
        """Process CSV rows and update journal statistics.

        Args:
            csv_path: Path to CSV file
            journal_stats: Dictionary to populate with journal statistics

        Returns:
            Number of article DOIs cached
        """
        current_year = datetime.now().year
        records_processed = 0
        articles_cached = 0
        article_batch: list[dict[str, str]] = []
        batch_size = 1000

        def _read_csv_sync() -> list[dict[str, Any]]:
            """Read CSV file synchronously."""
            rows = []
            with open(csv_path, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    rows.append(dict(row))
            return rows

        try:
            csv_rows = await asyncio.to_thread(_read_csv_sync)

            for row in csv_rows:
                records_processed += 1

                # Log progress every 5000 records
                if records_processed % 5000 == 0:
                    status_logger.info(
                        f"    {self.get_name()}: Processing retraction records: {records_processed:,} processed, {articles_cached:,} articles cached"
                    )

                # Extract and cache article retraction data
                article_cached = self._process_article_data(
                    row, article_batch, batch_size
                )
                if article_cached:
                    articles_cached += 1
                    if len(article_batch) >= batch_size:
                        self._collect_article_retractions(article_batch)
                        article_batch = []

                # Process journal statistics
                self._update_journal_stats(row, journal_stats, current_year)

            # Collect any remaining articles in the batch
            if article_batch:
                self._collect_article_retractions(article_batch)

            status_logger.info(
                f"    {self.get_name()}: Completed CSV parsing - {records_processed:,} records, {articles_cached:,} articles cached"
            )
            detail_logger.info(f"Processed {records_processed} retraction records")

        except Exception as e:
            status_logger.error(f"    {self.get_name()}: Error parsing CSV - {e}")
            return 0

        return articles_cached

    def _process_article_data(
        self,
        row: dict[str, Any],
        article_batch: list[dict[str, str]],
        batch_size: int,
    ) -> bool:
        """Extract and batch article retraction data from CSV row.

        Args:
            row: CSV row data
            article_batch: List to append article data to
            batch_size: Size of batch (unused, kept for API compatibility)

        Returns:
            True if article was cached, False otherwise
        """
        original_paper_doi = row.get("OriginalPaperDOI", "").strip()
        if not original_paper_doi:
            return False

        article_batch.append(
            {
                "doi": original_paper_doi,
                "retraction_date_str": row.get("RetractionDate", ""),
                "retraction_nature": row.get("RetractionNature", "").strip(),
                "reason": row.get("Reason", "").strip(),
                "retraction_doi": row.get("RetractionDOI", "").strip(),
            }
        )
        return True

    def _update_journal_stats(
        self,
        row: dict[str, Any],
        journal_stats: defaultdict[str, dict[str, Any]],
        current_year: int,
    ) -> None:
        """Update journal statistics from a CSV row.

        Args:
            row: CSV row data
            journal_stats: Dictionary to update with statistics
            current_year: Current year for recency calculations
        """
        journal = row.get("Journal", "").strip()
        if not journal:
            return

        # Normalize journal name
        try:
            normalized_input = input_normalizer.normalize(journal)
            normalized_journal = normalized_input.normalized_name
            if not normalized_journal:
                detail_logger.debug(
                    f"Failed to normalize journal '{journal}': normalized name is empty"
                )
                return
        except Exception as e:
            detail_logger.debug(f"Failed to normalize journal '{journal}': {e}")
            return

        # Parse retraction date
        retraction_date = self._parse_date(row.get("RetractionDate", ""))

        # Update journal stats
        stats = journal_stats[normalized_journal]
        stats["total_retractions"] += 1
        stats["original_names"].add(journal)

        if retraction_date:
            stats["retraction_dates"].append(retraction_date)

            # Update first/last dates
            if stats["first_date"] is None or retraction_date < stats["first_date"]:
                stats["first_date"] = retraction_date
            if stats["last_date"] is None or retraction_date > stats["last_date"]:
                stats["last_date"] = retraction_date

            # Count recent retractions
            years_ago = current_year - retraction_date.year
            if years_ago <= 2:
                stats["recent_retractions"] += 1
            if years_ago <= 1:
                stats["very_recent_retractions"] += 1

        # Retraction type
        retraction_nature = row.get("RetractionNature", "").strip()
        if retraction_nature:
            stats["retraction_types"][retraction_nature] += 1

        # Reasons
        reason = row.get("Reason", "").strip()
        if reason:
            stats["reasons"].append(reason)

        # Publisher
        publisher = row.get("Publisher", "").strip()
        if publisher:
            stats["publishers"].add(publisher)

    def _build_journals_from_stats(
        self,
        journal_stats: defaultdict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Convert aggregated statistics to journal list format.

        Args:
            journal_stats: Aggregated statistics by journal

        Returns:
            List of journal data dictionaries
        """
        journals = []
        for normalized_name, stats in journal_stats.items():
            # Get the most common original name
            original_name = (
                sorted(stats["original_names"])[0]
                if stats["original_names"]
                else normalized_name
            )

            # Get top reasons (most common)
            reason_counts: defaultdict[str, int] = defaultdict(int)
            for reason in stats["reasons"]:
                # Split multiple reasons
                for r in reason.split(";"):
                    r_clean = r.strip()
                    if r_clean:
                        reason_counts[r_clean] += 1

            top_reasons = sorted(
                reason_counts.items(), key=lambda x: x[1], reverse=True
            )[:5]

            # Store basic journal data (will enrich with OpenAlex later)
            journals.append(
                {
                    "journal_name": original_name,
                    "normalized_name": normalized_name,
                    "issn": None,  # Not available in retraction watch dataset
                    "eissn": None,
                    "publisher": (
                        list(stats["publishers"])[0] if stats["publishers"] else None
                    ),
                    "stats": stats,  # Temporary - will be converted to metadata
                    "reason_counts": reason_counts,
                    "top_reasons": top_reasons,
                }
            )

        return journals

    def _convert_to_final_format(
        self,
        journals: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Convert journal data to final format with metadata.

        Args:
            journals: List of journal data with stats

        Returns:
            List of journals in final format
        """
        final_journals = []
        for journal_data in journals:
            stats: dict[str, Any] = journal_data["stats"]

            # Calculate risk level without publication data
            risk_level = self._calculate_risk_level(
                stats["total_retractions"], stats["recent_retractions"]
            )

            metadata = {
                "total_retractions": stats["total_retractions"],
                "recent_retractions": stats["recent_retractions"],
                "very_recent_retractions": stats["very_recent_retractions"],
                "risk_level": risk_level,
                "first_retraction_date": (
                    stats["first_date"].isoformat() if stats["first_date"] else None
                ),
                "last_retraction_date": (
                    stats["last_date"].isoformat() if stats["last_date"] else None
                ),
                "retraction_types": dict(stats["retraction_types"]),
                "top_reasons": journal_data["top_reasons"],
                "publishers": list(stats["publishers"])[:10],
                "all_names": list(stats["original_names"])[:5],
            }

            final_journals.append(
                {
                    "journal_name": journal_data["journal_name"],
                    "normalized_name": journal_data["normalized_name"],
                    "issn": journal_data["issn"],
                    "eissn": journal_data["eissn"],
                    "publisher": journal_data["publisher"],
                    "metadata": metadata,
                }
            )

        return final_journals

    def _attach_article_retractions(self, final_journals: list[dict[str, Any]]) -> None:
        """Attach article retractions to first journal's metadata.

        Args:
            final_journals: List of journals in final format
        """
        if not final_journals or not self.article_retractions:
            return

        first_journal = final_journals[0]
        # Ensure metadata exists and is a dict
        if "metadata" not in first_journal or not isinstance(
            first_journal["metadata"], dict
        ):
            first_journal["metadata"] = {}
        # Add article retractions to metadata
        first_journal["metadata"]["_article_retractions"] = self.article_retractions

    def _parse_date(self, date_str: str) -> datetime | None:
        """Parse date string from Retraction Watch CSV."""
        if not date_str or date_str == "0":
            return None
        try:
            return datetime.strptime(date_str, "%m/%d/%Y %H:%M")
        except (ValueError, TypeError):
            return None

    def _calculate_risk_level(
        self,
        total: int,
        recent: int,
        total_publications: int | None = None,
        recent_publications: int | None = None,
    ) -> str:
        """
        Calculate risk level based on retraction rates (or counts if no publication data).

        This method uses the centralized risk calculator.

        Args:
            total: Total number of retractions
            recent: Number of retractions in last 2 years
            total_publications: Total number of publications (if available)
            recent_publications: Number of publications in recent years (if available)

        Returns:
            Risk level: "none", "note", "low", "moderate", "high", or "critical"
        """

        return calculate_retraction_risk_level(
            total, recent, total_publications, recent_publications
        )

    def _collect_article_retractions(self, article_batch: list[dict[str, str]]) -> None:
        """
        Collect article retraction data for later database insertion.

        This method prepares article retraction records without writing to the database,
        allowing AsyncDBWriter to handle all database writes sequentially.

        Args:
            article_batch: List of article retraction records to collect
        """
        if not article_batch:
            return

        expires_at = datetime.now() + timedelta(hours=24 * 365)  # 1 year

        # Prepare batch data
        for article in article_batch:
            doi = article.get("doi", "").strip()
            if not doi:
                continue

            # Parse retraction date
            retraction_date = self._parse_date(article.get("retraction_date_str", ""))
            retraction_date_formatted = (
                retraction_date.strftime("%Y-%m-%d") if retraction_date else None
            )

            retraction_nature = article.get("retraction_nature", "")
            reason = article.get("reason", "")
            retraction_doi = article.get("retraction_doi", "")

            self.article_retractions.append(
                {
                    "doi": doi.lower().strip(),
                    "is_retracted": True,
                    "retraction_type": retraction_nature or "Retraction",
                    "retraction_date": retraction_date_formatted,
                    "retraction_doi": retraction_doi if retraction_doi else None,
                    "retraction_reason": reason if reason else None,
                    "source": "retraction_watch",
                    "expires_at": expires_at.isoformat(),
                }
            )
