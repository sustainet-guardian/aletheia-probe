# SPDX-License-Identifier: MIT
"""Article-level retraction checking using multiple data sources."""

import asyncio
import re
from typing import Any

import aiohttp

from .cache import RetractionCache
from .logging_config import get_detail_logger, get_status_logger


status_logger = get_status_logger()
detail_logger = get_detail_logger()

# DOI format pattern - matches standard DOI structure (10.xxxx/...)
DOI_PATTERN = re.compile(r"^10\.\d{4,}/[^\s]+$")


class ArticleRetractionResult:
    """Result of checking an article for retraction status."""

    def __init__(
        self,
        doi: str,
        is_retracted: bool = False,
        retraction_type: str | None = None,
        retraction_date: str | None = None,
        retraction_doi: str | None = None,
        retraction_reason: str | None = None,
        sources: list[str] | None = None,
        checked_sources: list[str] | None = None,
    ):
        self.doi = doi
        self.is_retracted = is_retracted
        self.retraction_type = retraction_type
        self.retraction_date = retraction_date
        self.retraction_doi = retraction_doi
        self.retraction_reason = retraction_reason
        self.sources = sources or []
        self.checked_sources = checked_sources or []

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "doi": self.doi,
            "is_retracted": self.is_retracted,
            "retraction_type": self.retraction_type,
            "retraction_date": self.retraction_date,
            "retraction_doi": self.retraction_doi,
            "retraction_reason": self.retraction_reason,
            "sources": self.sources,
            "checked_sources": self.checked_sources,
        }


class ArticleRetractionChecker:
    """Checks individual articles (by DOI) for retraction status using multiple sources."""

    def __init__(
        self,
        retraction_cache: RetractionCache | None = None,
        email: str = "noreply@aletheia-probe.org",
        api_timeout_seconds: int = 30,
        cache_ttl_hours: int = 720,
    ):
        """
        Initialize the article retraction checker.

        Args:
            retraction_cache: Optional cache instance for storing results
            email: Email for Crossref polite pool access
            api_timeout_seconds: Timeout for API requests in seconds (default: 30)
            cache_ttl_hours: Cache time-to-live in hours (default: 720 = 30 days)
        """
        self.email = email
        self.crossref_base_url = "https://api.crossref.org"
        self.headers = {
            "User-Agent": f"AletheiaProbe/1.0 (mailto:{email})",
        }
        self.retraction_cache = (
            retraction_cache if retraction_cache else RetractionCache()
        )
        self.api_timeout_seconds = api_timeout_seconds
        self.cache_ttl_hours = cache_ttl_hours

    async def check_doi(self, doi: str) -> ArticleRetractionResult:
        """
        Check if a DOI is retracted using multiple data sources.

        This method:
        1. Validates DOI format
        2. Checks cache first
        3. Checks local Retraction Watch data (if available)
        4. Queries Crossref API for retraction status
        5. Caches the result

        Args:
            doi: The DOI to check

        Returns:
            ArticleRetractionResult with retraction information
        """
        if not doi:
            return ArticleRetractionResult(doi="", is_retracted=False)

        normalized_doi = doi.lower().strip()

        # Validate DOI format
        if not DOI_PATTERN.match(normalized_doi):
            detail_logger.warning(
                f"Invalid DOI format: {normalized_doi}. Expected format: 10.xxxx/suffix"
            )
            return ArticleRetractionResult(doi=normalized_doi, is_retracted=False)

        detail_logger.debug(f"Checking retraction status for DOI: {normalized_doi}")

        # Check cache first
        cached = self.retraction_cache.get_article_retraction(normalized_doi)
        if cached:
            detail_logger.debug(f"Cache hit for DOI {normalized_doi}")
            return ArticleRetractionResult(
                doi=normalized_doi,
                is_retracted=bool(cached.get("is_retracted", False)),
                retraction_type=cached.get("retraction_type"),
                retraction_date=cached.get("retraction_date"),
                retraction_doi=cached.get("retraction_doi"),
                retraction_reason=cached.get("retraction_reason"),
                sources=[cached.get("source", "cache")],
            )

        # Check multiple sources
        checked_sources = []
        result = ArticleRetractionResult(doi=normalized_doi)

        # Check local Retraction Watch database first (faster)
        rw_result = await self._check_retraction_watch_local(normalized_doi)
        checked_sources.append("retraction_watch_local")
        if rw_result.is_retracted:
            result = rw_result
            result.checked_sources = checked_sources
            self._cache_result(result, "retraction_watch")
            return result

        # Check Crossref API
        try:
            crossref_result = await self._check_crossref_api(normalized_doi)
            checked_sources.append("crossref")
            if crossref_result.is_retracted:
                result = crossref_result
                result.checked_sources = checked_sources
                self._cache_result(result, "crossref")
                return result
        except (aiohttp.ClientError, ValueError, KeyError, AttributeError) as e:
            detail_logger.warning(
                f"Crossref API check failed for {normalized_doi}: {e}"
            )

        # No retraction found - cache negative result
        result.checked_sources = checked_sources
        self._cache_result(result, "multiple")
        return result

    async def _check_retraction_watch_local(self, doi: str) -> ArticleRetractionResult:
        """
        Check local Retraction Watch database for DOI.

        Queries the article_retractions cache table which should be populated
        from the Retraction Watch CSV data during sync operations.

        Args:
            doi: The DOI to check

        Returns:
            ArticleRetractionResult
        """
        # Check if we have this DOI in the article_retractions table
        # (populated from Retraction Watch CSV during sync)
        cached = self.retraction_cache.get_article_retraction(doi)

        if cached and cached.get("source") == "retraction_watch":
            detail_logger.debug(
                f"Found retraction in local Retraction Watch data: {doi}"
            )
            return ArticleRetractionResult(
                doi=doi,
                is_retracted=bool(cached.get("is_retracted", False)),
                retraction_type=cached.get("retraction_type"),
                retraction_date=cached.get("retraction_date"),
                retraction_doi=cached.get("retraction_doi"),
                retraction_reason=cached.get("retraction_reason"),
                sources=["retraction_watch"],
            )

        return ArticleRetractionResult(doi=doi, is_retracted=False)

    async def _check_crossref_api(self, doi: str) -> ArticleRetractionResult:
        """
        Check Crossref API for retraction status.

        Uses the Crossref REST API to check if a DOI has been retracted.
        Looks for the 'update-to' or 'updated-by' fields in the response.

        Args:
            doi: The DOI to check

        Returns:
            ArticleRetractionResult
        """
        url = f"{self.crossref_base_url}/works/{doi}"

        async with aiohttp.ClientSession(
            headers=self.headers,
            timeout=aiohttp.ClientTimeout(total=self.api_timeout_seconds),
        ) as session:
            try:
                async with session.get(url) as response:
                    if response.status == 404:
                        detail_logger.debug(f"DOI not found in Crossref: {doi}")
                        return ArticleRetractionResult(doi=doi, is_retracted=False)

                    if response.status != 200:
                        detail_logger.warning(
                            f"Crossref API returned status {response.status} for {doi}"
                        )
                        return ArticleRetractionResult(doi=doi, is_retracted=False)

                    data = await response.json()
                    message = data.get("message", {})

                    # Check for retraction information in 'update-to' or 'updated-by' fields
                    # 'updated-by' indicates this work has been updated (potentially retracted)
                    updated_by = message.get("updated-by")
                    if (
                        updated_by
                        and isinstance(updated_by, list)
                        and len(updated_by) > 0
                    ):
                        # Check if any update is a retraction
                        for update in updated_by:
                            update_type = update.get("type", "").lower()
                            if "retract" in update_type or update_type == "retraction":
                                return self._parse_crossref_retraction(
                                    doi, update, message
                                )

                    # Also check 'update-to' field (for retraction notices)
                    # This is less common but possible
                    update_to = message.get("update-to")
                    if update_to and isinstance(update_to, list):
                        for update in update_to:
                            update_type = update.get("type", "").lower()
                            if "retract" in update_type:
                                return self._parse_crossref_retraction(
                                    doi, update, message, is_notice=True
                                )

                    return ArticleRetractionResult(doi=doi, is_retracted=False)

            except asyncio.TimeoutError:
                detail_logger.warning(f"Crossref API timeout for {doi}")
                return ArticleRetractionResult(doi=doi, is_retracted=False)
            except (aiohttp.ClientError, ValueError, KeyError, AttributeError) as e:
                detail_logger.warning(f"Error checking Crossref for {doi}: {e}")
                return ArticleRetractionResult(doi=doi, is_retracted=False)

    def _parse_crossref_retraction(
        self,
        doi: str,
        update_info: dict[str, Any],
        full_message: dict[str, Any],
        is_notice: bool = False,
    ) -> ArticleRetractionResult:
        """
        Parse retraction information from Crossref update data.

        Extracts retraction details such as type, date, DOI, and reason from the
        Crossref API response structures.

        Args:
            doi: The DOI of the article being checked.
            update_info: Dictionary containing the specific update information
                (from 'updated-by' or 'update-to').
            full_message: The complete 'message' dictionary from the Crossref API response.
            is_notice: Whether the update info comes from a retraction notice ('update-to')
                rather than an update to the work itself. Defaults to False.

        Returns:
            ArticleRetractionResult containing the parsed retraction details.
        """
        retraction_type = update_info.get("type", "retraction")
        retraction_date = None
        retraction_doi = update_info.get("DOI")

        # Try to extract date from update info or full message
        if "updated" in update_info:
            updated = update_info["updated"]
            if isinstance(updated, dict) and "date-parts" in updated:
                date_parts = updated["date-parts"][0]
                if len(date_parts) >= 3:
                    retraction_date = (
                        f"{date_parts[0]}-{date_parts[1]:02d}-{date_parts[2]:02d}"
                    )

        # Extract reason from label if available
        retraction_reason = update_info.get("label")

        return ArticleRetractionResult(
            doi=doi,
            is_retracted=True,
            retraction_type=retraction_type,
            retraction_date=retraction_date,
            retraction_doi=retraction_doi,
            retraction_reason=retraction_reason,
            sources=["crossref"],
        )

    def _cache_result(self, result: ArticleRetractionResult, source: str) -> None:
        """
        Cache the retraction check result.

        Stores the retraction result in the cache with a predefined time-to-live (TTL).

        Args:
            result: The ArticleRetractionResult object containing the check findings.
            source: The identifier of the source used for the check (e.g., 'crossref',
                'retraction_watch').
        """
        self.retraction_cache.cache_article_retraction(
            doi=result.doi,
            is_retracted=result.is_retracted,
            source=source,
            retraction_type=result.retraction_type,
            retraction_date=result.retraction_date,
            retraction_doi=result.retraction_doi,
            retraction_reason=result.retraction_reason,
            ttl_hours=self.cache_ttl_hours,
        )


async def check_article_retraction(doi: str) -> ArticleRetractionResult:
    """
    Convenience function to check if an article is retracted.

    Args:
        doi: The DOI to check

    Returns:
        ArticleRetractionResult with retraction information
    """
    checker = ArticleRetractionChecker()
    return await checker.check_doi(doi)
