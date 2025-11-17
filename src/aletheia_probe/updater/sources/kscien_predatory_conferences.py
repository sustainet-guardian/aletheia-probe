"""Kscien predatory conference data source."""

import asyncio
import re
from datetime import datetime
from typing import Any

from aiohttp import ClientSession, ClientTimeout

from ...cache import get_cache_manager
from ...logging_config import get_detail_logger, get_status_logger
from ...normalizer import input_normalizer
from ..core import DataSource

detail_logger = get_detail_logger()
status_logger = get_status_logger()


class KscienPredatoryConferencesSource(DataSource):
    """Data source for Kscien predatory conference lists.

    Fetches predatory conference data from Kscien Organisation.
    """

    def __init__(self) -> None:
        """Initialize the predatory conferences data source."""
        # Configure data sources
        self.sources: dict[str, str] = {
            "kscien": "https://kscien.org/predatory-publishing/?_publishing_list=predatory-conferences",
            # Note: Beall's original conference list is archived but not easily machine-readable
            # Original source was scholarlyoa.com (offline since 2017)
            # Data now fragmented across Wayback Machine archives
            # TODO: Consider adding other reliable predatory conference sources
        }
        self.timeout = ClientTimeout(total=60)  # Increased timeout for web scraping
        self.max_pages = (
            100  # Safety limit for pagination (Kscien has ~40 pages as of Nov 2025)
        )

    def get_name(self) -> str:
        """Return the data source identifier."""
        return "kscien_predatory_conferences"

    def get_list_type(self) -> str:
        """Return the list type (predatory)."""
        return "predatory"

    def should_update(self) -> bool:
        """Check if we should update (weekly for predatory lists).

        Returns True if sources are configured and data is stale or missing.
        """
        if not self.sources:
            status_logger.debug(
                "Predatory conferences source has no configured sources, skipping update"
            )
            return False

        last_update = get_cache_manager().get_source_last_updated(self.get_name())
        if last_update is None:
            detail_logger.info(
                "No previous update found for predatory conferences, will update"
            )
            return True

        # Update weekly
        days_since_update = (datetime.now() - last_update).days
        should_update = days_since_update >= 7
        detail_logger.debug(
            f"Last update was {days_since_update} days ago, should_update: {should_update}"
        )
        return should_update

    async def fetch_data(self) -> list[dict[str, Any]]:
        """Fetch predatory conference data from configured sources.

        Returns:
            List of conference entries with normalized names
        """
        all_conferences = []

        detail_logger.info(
            "Starting predatory conferences data fetch from configured sources"
        )

        if self.sources:
            async with ClientSession(timeout=self.timeout) as session:
                for source_name, url in self.sources.items():
                    try:
                        detail_logger.info(f"Fetching data from {source_name}: {url}")
                        conferences = await self._fetch_from_source(
                            session, url, source_name
                        )
                        all_conferences.extend(conferences)
                        detail_logger.info(
                            f"Successfully fetched {len(conferences)} entries from {source_name}"
                        )
                    except Exception as e:
                        detail_logger.error(f"Failed to fetch from {source_name}: {e}")
                        detail_logger.exception("Full error details:")
        else:
            detail_logger.warning(
                "No data sources configured for predatory conferences"
            )

        # Remove duplicates based on normalized name
        unique_conferences = self._deduplicate_conferences(all_conferences)
        status_logger.info(
            f"Total unique conferences after deduplication: {len(unique_conferences)}"
        )

        return unique_conferences

    async def _fetch_from_source(
        self, session: ClientSession, url: str, source_name: str
    ) -> list[dict[str, Any]]:
        """Fetch conference data from a specific source.

        Args:
            session: HTTP session
            url: Source URL
            source_name: Name of the source

        Returns:
            List of conference entries
        """
        conferences = []

        try:
            if source_name == "kscien":
                conferences = await self._fetch_kscien_conferences(session, url)
            else:
                # Generic fallback for other sources
                async with session.get(url) as response:
                    if response.status == 200:
                        html_content = await response.text()
                        conferences = self._parse_conference_list(html_content, url)
                    else:
                        status_logger.warning(f"HTTP {response.status} from {url}")

        except asyncio.TimeoutError:
            status_logger.error(f"Timeout fetching from {url}")
        except Exception as e:
            status_logger.error(f"Error fetching from {url}: {e}")

        return conferences

    async def _fetch_kscien_conferences(
        self, session: ClientSession, base_url: str
    ) -> list[dict[str, Any]]:
        """Fetch conferences from Kscien.org with pagination support.

        Args:
            session: HTTP session
            base_url: Base URL for Kscien predatory conferences

        Returns:
            List of conference entries from all pages
        """
        all_conferences = []
        page = 1

        while page <= self.max_pages:
            try:
                # Construct URL for specific page using Kscien's pagination pattern
                if page == 1:
                    url = base_url  # Uses the original URL with _publishing_list filter
                else:
                    # Kscien pagination requires BOTH _publishing_list and _pagination parameters
                    # Pattern: /?_publishing_list=predatory-conferences&_pagination=2
                    url = f"https://kscien.org/predatory-publishing/?_publishing_list=predatory-conferences&_pagination={page}"

                detail_logger.debug(f"Fetching Kscien page {page}: {url}")

                async with session.get(url) as response:
                    if response.status != 200:
                        status_logger.warning(f"HTTP {response.status} from {url}")
                        break

                    html_content = await response.text()
                    page_conferences = self._parse_kscien_page(html_content, page)

                    if not page_conferences:
                        detail_logger.info(
                            f"No conferences found on page {page}, stopping pagination"
                        )
                        break

                    all_conferences.extend(page_conferences)
                    detail_logger.debug(
                        f"Found {len(page_conferences)} conferences on page {page}"
                    )

                    # Check if there's a next page
                    if not self._has_next_page(html_content, page):
                        detail_logger.info(f"Reached last page at page {page}")
                        break

                page += 1

                # Small delay to be respectful to the server
                await asyncio.sleep(0.5)

            except Exception as e:
                status_logger.error(f"Error fetching Kscien page {page}: {e}")
                break

        detail_logger.info(
            f"Fetched {len(all_conferences)} total conferences from Kscien across {page - 1} pages"
        )
        return all_conferences

    def _parse_kscien_page(self, html: str, page_num: int) -> list[dict[str, Any]]:
        """Parse conference names from a Kscien.org page using regex.

        Args:
            html: HTML content from Kscien page
            page_num: Page number for logging

        Returns:
            List of parsed conference entries
        """
        conferences = []

        try:
            # Pattern to match h4 headings followed by "Visit Website" links
            # Example structure: <h4>Conference Name</h4><p><a href="URL">Visit Website</a></p>
            pattern = r'<h4[^>]*>(.*?)</h4>\s*<p[^>]*>.*?<a[^>]*href=["\']([^"\']*)["\'][^>]*>.*?Visit\s+Website.*?</a>'
            matches = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)

            for conference_name_raw, website_url in matches:
                try:
                    # Clean the conference name
                    conference_name = re.sub(
                        r"<[^>]+>", "", conference_name_raw
                    ).strip()
                    if not conference_name:
                        continue

                    # Clean the URL
                    website_url = website_url.strip()

                    # Create conference entry
                    conference_entry = {
                        "journal_name": conference_name,  # Core updater expects this field name
                        "normalized_name": None,  # Will be set during deduplication
                        "source": "kscien",
                        "source_url": "https://kscien.org/predatory-publishing/",
                        "page": page_num,
                        "metadata": {
                            "website_url": website_url,
                            "list_type": "predatory",
                            "authority_level": 8,  # High authority like Beall's
                            "last_verified": datetime.now().isoformat(),
                        },
                    }

                    conferences.append(conference_entry)
                    detail_logger.debug(f"Parsed conference: {conference_name}")

                except Exception as e:
                    status_logger.warning(
                        f"Error parsing individual conference on page {page_num}: {e}"
                    )
                    continue

            # Alternative pattern for conferences without "Visit Website" links
            # Some entries might just be h4 headings
            if not conferences:
                simple_pattern = r"<h4[^>]*>(.*?)</h4>"
                simple_matches = re.findall(
                    simple_pattern, html, re.DOTALL | re.IGNORECASE
                )

                for conference_name_raw in simple_matches:
                    try:
                        conference_name = re.sub(
                            r"<[^>]+>", "", conference_name_raw
                        ).strip()
                        if (
                            not conference_name or len(conference_name) < 5
                        ):  # Skip very short names
                            continue

                        conference_entry = {
                            "journal_name": conference_name,  # Core updater expects this field name
                            "normalized_name": None,
                            "source": "kscien",
                            "source_url": "https://kscien.org/predatory-publishing/",
                            "page": page_num,
                            "metadata": {
                                "website_url": None,
                                "list_type": "predatory",
                                "authority_level": 8,
                                "last_verified": datetime.now().isoformat(),
                            },
                        }

                        conferences.append(conference_entry)
                        detail_logger.debug(
                            f"Parsed conference (simple): {conference_name}"
                        )

                    except Exception as e:
                        status_logger.warning(
                            f"Error parsing simple conference on page {page_num}: {e}"
                        )
                        continue

        except Exception as e:
            status_logger.error(f"Error parsing Kscien page {page_num}: {e}")

        return conferences

    def _has_next_page(self, html: str, current_page: int) -> bool:
        """Check if there's a next page in Kscien pagination using regex.

        Args:
            html: HTML content from current page
            current_page: Current page number

        Returns:
            True if there's a next page, False otherwise
        """
        try:
            # Look for pagination indicators
            # Kscien shows pagination like "1 - 90 of 3539 Publishings"
            pagination_match = re.search(
                r"(\d+)\s*-\s*(\d+)\s*of\s*(\d+)\s*Publishings?", html, re.IGNORECASE
            )
            if pagination_match:
                end_item = int(pagination_match.group(2))
                total_items = int(pagination_match.group(3))
                has_more = end_item < total_items
                detail_logger.debug(
                    f"Pagination info: showing items up to {end_item} of {total_items}, "
                    f"has_more: {has_more}"
                )
                return has_more

            # Also check for numbered pagination links to next page
            next_page = current_page + 1
            next_page_pattern = (
                rf'<a[^>]*href=["\'][^"\']*page={next_page}[^"\']*["\'][^>]*>'
            )
            if re.search(next_page_pattern, html, re.IGNORECASE):
                detail_logger.debug(f"Found link to page {next_page}")
                return True

            # Check for "Next" or ">" links
            next_link_pattern = (
                r'<a[^>]*href=["\'][^"\']*["\'][^>]*>.*?(?:Next|>).*?</a>'
            )
            if re.search(next_link_pattern, html, re.IGNORECASE | re.DOTALL):
                detail_logger.debug("Found 'Next' link")
                return True

        except Exception as e:
            detail_logger.debug(f"Error checking pagination: {e}")

        return False

    def _parse_conference_list(
        self, html: str, source_url: str
    ) -> list[dict[str, Any]]:
        """Parse conference names from HTML content (generic fallback).

        This is a fallback implementation for non-Kscien sources.

        Args:
            html: HTML content
            source_url: Source URL for metadata

        Returns:
            List of parsed conference entries
        """
        conferences: list[dict[str, Any]] = []

        # Generic parsing - look for common patterns
        # This can be extended for other sources in the future
        detail_logger.warning(
            f"Using generic parsing for {source_url} - results may be limited"
        )

        return conferences

    def _deduplicate_conferences(
        self, conferences: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Remove duplicate conferences based on normalized names.

        Args:
            conferences: List of conference entries

        Returns:
            Deduplicated list of conferences
        """
        seen = set()
        unique_conferences = []

        for conf in conferences:
            # Normalize the conference name for deduplication
            normalized = input_normalizer.normalize(conf.get("journal_name", ""))
            normalized_name = normalized.normalized_name
            if normalized_name is None:
                continue
            normalized_key = normalized_name.lower()

            if normalized_key not in seen:
                seen.add(normalized_key)
                # Ensure we have the normalized name in the entry
                conf["normalized_name"] = normalized_name
                unique_conferences.append(conf)

        return unique_conferences
