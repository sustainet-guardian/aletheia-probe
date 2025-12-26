# SPDX-License-Identifier: MIT
"""Retraction Watch database data source from GitLab."""

import asyncio
import csv
import json
import sqlite3
import subprocess
import tempfile
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ...cache import DataSourceManager, RetractionCache
from ...config import get_config_manager
from ...enums import AssessmentType
from ...logging_config import get_detail_logger, get_status_logger
from ...normalizer import input_normalizer
from ..core import DataSource, get_update_source_registry


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
                status_logger.error("Failed to clone Retraction Watch repository")
                return []

            # Find and parse the CSV file
            csv_path = repo_path / self.csv_filename
            if not csv_path.exists():
                status_logger.error(f"CSV file not found: {csv_path}")
                return []

            # Parse and aggregate the data
            journals = await self._parse_and_aggregate_csv(csv_path)
            status_logger.info(
                f"Successfully aggregated data for {len(journals)} journals"
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

        current_year = datetime.now().year
        records_processed = 0
        articles_cached = 0
        article_batch = []  # Batch for article retractions
        batch_size = 1000  # Commit every 1000 articles

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
                        f"    Processing retraction records: {records_processed:,} processed, {articles_cached:,} articles cached"
                    )

                journal = row.get("Journal", "").strip()
                publisher = row.get("Publisher", "").strip()
                retraction_date_str = row.get("RetractionDate", "")
                retraction_nature = row.get("RetractionNature", "").strip()
                reason = row.get("Reason", "").strip()
                original_paper_doi = row.get("OriginalPaperDOI", "").strip()
                retraction_doi = row.get("RetractionDOI", "").strip()

                # Collect article retraction for batch insert
                if original_paper_doi:
                    article_batch.append(
                        {
                            "doi": original_paper_doi,
                            "retraction_date_str": retraction_date_str,
                            "retraction_nature": retraction_nature,
                            "reason": reason,
                            "retraction_doi": retraction_doi,
                        }
                    )
                    articles_cached += 1

                    # Batch insert every batch_size articles
                    if len(article_batch) >= batch_size:
                        await self._batch_cache_article_retractions(article_batch)
                        article_batch = []

                if not journal:
                    continue

                # Normalize journal name
                try:
                    normalized_input = input_normalizer.normalize(journal)
                    normalized_journal = normalized_input.normalized_name
                    if not normalized_journal:
                        detail_logger.debug(
                            f"Failed to normalize journal '{journal}': normalized name is empty"
                        )
                        continue
                except Exception as e:
                    detail_logger.debug(f"Failed to normalize journal '{journal}': {e}")
                    continue

                # Parse retraction date
                retraction_date = self._parse_date(retraction_date_str)

                # Update journal stats
                stats = journal_stats[normalized_journal]
                stats["total_retractions"] += 1
                stats["original_names"].add(journal)

                if retraction_date:
                    stats["retraction_dates"].append(retraction_date)

                    # Update first/last dates
                    if (
                        stats["first_date"] is None
                        or retraction_date < stats["first_date"]
                    ):
                        stats["first_date"] = retraction_date
                    if (
                        stats["last_date"] is None
                        or retraction_date > stats["last_date"]
                    ):
                        stats["last_date"] = retraction_date

                    # Count recent retractions
                    years_ago = current_year - retraction_date.year
                    if years_ago <= 2:
                        stats["recent_retractions"] += 1
                    if years_ago <= 1:
                        stats["very_recent_retractions"] += 1

                # Retraction type
                if retraction_nature:
                    stats["retraction_types"][retraction_nature] += 1

                # Reasons
                if reason:
                    stats["reasons"].append(reason)

                # Publisher
                if publisher:
                    stats["publishers"].add(publisher)

            # Insert any remaining articles in the batch
            if article_batch:
                await self._batch_cache_article_retractions(article_batch)

            status_logger.info(
                f"    Completed CSV parsing: {records_processed:,} total records, {articles_cached:,} articles cached by DOI"
            )
            detail_logger.info(f"Processed {records_processed} retraction records")

        except Exception as e:
            status_logger.error(f"Error parsing CSV: {e}")
            return []

        # Convert aggregated stats to journal list format
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

        status_logger.info(
            f"    Aggregating journal statistics: {len(journals):,} journals found"
        )
        detail_logger.info(f"Aggregated {len(journals)} journals from retraction data")

        # Convert to final format without OpenAlex enrichment
        # (OpenAlex data will be fetched on-demand during queries)
        final_journals = []
        for journal_data in journals:
            stats: dict[str, Any] = journal_data["stats"]  # type: ignore

            # Calculate risk level without publication data (will be recalculated on-demand)
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

        status_logger.info(
            f"    Retraction data processing complete: {len(final_journals):,} journals, {articles_cached:,} article DOIs cached"
        )
        detail_logger.info(
            "Retraction data aggregation complete (OpenAlex data will be fetched on-demand)"
        )

        return final_journals

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
        from ...risk_calculator import calculate_retraction_risk_level

        return calculate_retraction_risk_level(
            total, recent, total_publications, recent_publications
        )

    async def _batch_cache_article_retractions(
        self, article_batch: list[dict[str, str]]
    ) -> None:
        """
        Cache multiple article retractions in a single transaction (batch insert).

        This is much faster than individual inserts as it commits all records at once.

        Args:
            article_batch: List of article retraction records to cache
        """
        if not article_batch:
            return

        retraction_cache = RetractionCache()
        expires_at = datetime.now() + timedelta(hours=24 * 365)  # 1 year

        # Prepare batch data
        records = []
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

            records.append(
                (
                    doi.lower().strip(),
                    True,  # is_retracted
                    retraction_nature or "Retraction",
                    retraction_date_formatted,
                    retraction_doi if retraction_doi else None,
                    reason if reason else None,
                    "retraction_watch",
                    expires_at.isoformat(),
                )
            )

        # Batch insert
        if records:
            with sqlite3.connect(retraction_cache.db_path) as conn:
                cursor = conn.cursor()
                cursor.executemany(
                    """
                    INSERT OR REPLACE INTO article_retractions
                    (doi, is_retracted, retraction_type, retraction_date, retraction_doi,
                     retraction_reason, source, checked_at, expires_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
                    """,
                    records,
                )
                conn.commit()


# Register the update source factory
get_update_source_registry().register_factory(
    "retraction_watch", lambda: RetractionWatchSource(), default_config={}
)
