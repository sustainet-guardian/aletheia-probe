"""Generic Kscien data source for multiple publication types."""

import asyncio
import re
from datetime import datetime
from typing import Any, Literal

from aiohttp import ClientSession, ClientTimeout

from ...cache import get_cache_manager
from ...logging_config import get_detail_logger, get_status_logger
from ...normalizer import input_normalizer
from ..core import DataSource

detail_logger = get_detail_logger()
status_logger = get_status_logger()

PublicationType = Literal[
    "predatory-conferences",
    "standalone-journals",
    "hijacked-journals",
    "publishers",
    "misleading-metrics",
]


class KscienGenericSource(DataSource):
    """Generic data source for Kscien Organisation lists.

    Supports multiple publication types from Kscien (counts updated dynamically):
    - predatory-conferences - predatory conferences
    - standalone-journals - predatory individual journals
    - hijacked-journals - legitimate journals that were hijacked
    - publishers - predatory publishers
    - misleading-metrics - questionable metrics services
    """

    def __init__(
        self, publication_type: PublicationType, list_type: str = "predatory"
    ) -> None:
        """Initialize the Kscien generic data source.

        Args:
            publication_type: Type of publications to fetch
            list_type: Assessment type ("predatory" or "hijacked")
        """
        self.publication_type = publication_type
        self.list_type = list_type

        # Configure base URL for the specific publication type
        self.base_url = f"https://kscien.org/predatory-publishing/?_publishing_list={publication_type}"

        self.timeout = ClientTimeout(total=60)
        self.max_pages = 45  # Safety limit for pagination

    def get_name(self) -> str:
        """Return the data source identifier."""
        return f"kscien_{self.publication_type.replace('-', '_')}"

    def get_list_type(self) -> str:
        """Return the list type (predatory, hijacked, etc.)."""
        return self.list_type

    def should_update(self) -> bool:
        """Check if we should update (weekly for static lists)."""
        if not self.base_url:
            detail_logger.debug(
                f"Kscien {self.publication_type} source has no configured URL, skipping update"
            )
            return False

        last_update = get_cache_manager().get_source_last_updated(self.get_name())
        if last_update is None:
            detail_logger.info(
                f"No previous update found for kscien {self.publication_type}, will update"
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
        """Fetch data from Kscien for the specified publication type.

        Returns:
            List of publication entries with normalized names
        """
        all_publications = []

        detail_logger.info(f"Starting Kscien {self.publication_type} data fetch")
        status_logger.info(f"    {self.get_name()}: Starting data fetch")

        async with ClientSession(timeout=self.timeout) as session:
            publications = await self._fetch_kscien_publications(session, self.base_url)
            all_publications.extend(publications)
            status_logger.info(
                f"    {self.get_name()}: Retrieved {len(publications)} raw entries"
            )

        # Remove duplicates based on normalized name
        unique_publications = self._deduplicate_publications(all_publications)
        detail_logger.info(
            f"Total unique {self.publication_type} after deduplication: {len(unique_publications)}"
        )
        status_logger.info(
            f"    {self.get_name()}: Processed {len(unique_publications)} unique entries"
        )

        return unique_publications

    async def _fetch_kscien_publications(
        self, session: ClientSession, base_url: str
    ) -> list[dict[str, Any]]:
        """Fetch publications from Kscien.org with pagination support."""
        all_publications = []
        page = 1
        expected_count = None

        while page <= self.max_pages:
            try:
                # Construct URL for specific page
                if page == 1:
                    url = base_url
                else:
                    # Kscien pagination requires BOTH _publishing_list and _pagination parameters
                    url = f"https://kscien.org/predatory-publishing/?_publishing_list={self.publication_type}&_pagination={page}"

                detail_logger.debug(
                    f"Fetching Kscien {self.publication_type} page {page}: {url}"
                )

                async with session.get(url) as response:
                    if response.status != 200:
                        detail_logger.warning(f"HTTP {response.status} from {url}")
                        status_logger.warning(
                            f"    {self.get_name()}: HTTP {response.status} from page {page}"
                        )
                        break

                    html_content = await response.text()

                    # Extract expected count from first page
                    if page == 1:
                        expected_count = self._extract_expected_count(html_content)
                        if expected_count:
                            detail_logger.info(
                                f"Expecting {expected_count} total {self.publication_type} entries"
                            )

                    page_publications = self._parse_kscien_page(html_content, page)

                    if not page_publications:
                        detail_logger.info(
                            f"No {self.publication_type} found on page {page}, stopping pagination"
                        )
                        break

                    all_publications.extend(page_publications)
                    detail_logger.debug(
                        f"Found {len(page_publications)} {self.publication_type} on page {page}"
                    )

                    # Check if there's a next page
                    if not self._has_next_page(html_content, page):
                        detail_logger.info(f"Reached last page at page {page}")
                        break

                page += 1

                # Small delay to be respectful to the server
                await asyncio.sleep(0.5)

            except Exception as e:
                detail_logger.error(
                    f"Error fetching Kscien {self.publication_type} page {page}: {e}"
                )
                status_logger.error(
                    f"    {self.get_name()}: Error fetching page {page} - {e}"
                )
                break

        actual_count = len(all_publications)
        if expected_count:
            if actual_count == expected_count:
                detail_logger.info(
                    f"✅ Successfully fetched {actual_count}/{expected_count} {self.publication_type} from Kscien across {page - 1} pages"
                )
            else:
                detail_logger.warning(
                    f"⚠️ Count mismatch: fetched {actual_count} but expected {expected_count} {self.publication_type} (across {page - 1} pages)"
                )
                status_logger.warning(
                    f"    {self.get_name()}: Count mismatch - got {actual_count}, expected {expected_count}"
                )
        else:
            detail_logger.info(
                f"Fetched {actual_count} {self.publication_type} from Kscien across {page - 1} pages"
            )

        return all_publications

    def _extract_expected_count(self, html: str) -> int | None:
        """Extract the expected total count for this publication type from the page."""
        try:
            # First try to find the specific count in the filter sections
            # Pattern: "Predatory Conferences (499)" or similar
            type_display_names = {
                "predatory-conferences": r"Predatory\s+Conferences?\s*\(\s*(\d+)\s*\)",
                "standalone-journals": r"Standalone\s+Journals?\s*\(\s*(\d+)\s*\)",
                "hijacked-journals": r"Hijacked\s+Journals?\s*\(\s*(\d+)\s*\)",
                "publishers": r"Publishers?\s*\(\s*(\d+)\s*\)",
                "misleading-metrics": r"Misleading\s+Metrics?\s*\(\s*(\d+)\s*\)",
            }

            pattern = type_display_names.get(self.publication_type)
            if pattern:
                count_match = re.search(pattern, html, re.IGNORECASE)
                if count_match:
                    count = int(count_match.group(1))
                    detail_logger.debug(
                        f"Found {self.publication_type} count in filter: {count}"
                    )
                    return count

            # If specific count not found, try pagination info as fallback
            # Note: This may give total count across all types, not just this type
            pagination_match = re.search(
                r"(\d+)\s*-\s*\d+\s*of\s*(\d+)\s*Publishings?", html, re.IGNORECASE
            )
            if pagination_match:
                total_count = int(pagination_match.group(2))
                detail_logger.debug(
                    f"Found pagination count (may be total across all types): {total_count}"
                )
                # Only use if it's reasonable for the specific type (not the 3539 total)
                if total_count < 2000:  # Reasonable threshold for individual types
                    return total_count
                else:
                    detail_logger.debug(
                        f"Pagination count {total_count} seems like total across all types, ignoring"
                    )

        except Exception as e:
            detail_logger.debug(f"Error extracting expected count: {e}")

        return None

    def _parse_kscien_page(self, html: str, page_num: int) -> list[dict[str, Any]]:
        """Parse publication names from a Kscien.org page using regex."""
        publications = []

        try:
            # Pattern to match h4 headings followed by "Visit Website" links
            pattern = r'<h4[^>]*>(.*?)</h4>\s*<p[^>]*>.*?<a[^>]*href=["\']([^"\']*)["\'][^>]*>.*?Visit\s+Website.*?</a>'
            matches = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)

            for publication_name_raw, website_url in matches:
                try:
                    # Clean the publication name
                    publication_name = re.sub(
                        r"<[^>]+>", "", publication_name_raw
                    ).strip()
                    if not publication_name:
                        continue

                    # Clean the URL
                    website_url = website_url.strip()

                    # Create publication entry
                    publication_entry = {
                        "journal_name": publication_name,  # Core updater expects this field name
                        "normalized_name": None,  # Will be set during deduplication
                        "source": f"kscien_{self.publication_type}",
                        "source_url": "https://kscien.org/predatory-publishing/",
                        "page": page_num,
                        "metadata": {
                            "website_url": website_url,
                            "publication_type": self.publication_type,
                            "list_type": self.list_type,
                            "authority_level": 8,  # High authority like Beall's
                            "last_verified": datetime.now().isoformat(),
                        },
                    }

                    publications.append(publication_entry)
                    detail_logger.debug(
                        f"Parsed {self.publication_type}: {publication_name}"
                    )

                except Exception as e:
                    detail_logger.warning(
                        f"Error parsing individual {self.publication_type} on page {page_num}: {e}"
                    )
                    status_logger.debug(
                        f"    {self.get_name()}: Parse error on page {page_num} - {e}"
                    )
                    continue

            # Alternative pattern for publications without "Visit Website" links
            if not publications:
                simple_pattern = r"<h4[^>]*>(.*?)</h4>"
                simple_matches = re.findall(
                    simple_pattern, html, re.DOTALL | re.IGNORECASE
                )

                for publication_name_raw in simple_matches:
                    try:
                        publication_name = re.sub(
                            r"<[^>]+>", "", publication_name_raw
                        ).strip()
                        if (
                            not publication_name or len(publication_name) < 5
                        ):  # Skip very short names
                            continue

                        publication_entry = {
                            "journal_name": publication_name,
                            "normalized_name": None,
                            "source": f"kscien_{self.publication_type}",
                            "source_url": "https://kscien.org/predatory-publishing/",
                            "page": page_num,
                            "metadata": {
                                "website_url": None,
                                "publication_type": self.publication_type,
                                "list_type": self.list_type,
                                "authority_level": 8,
                                "last_verified": datetime.now().isoformat(),
                            },
                        }

                        publications.append(publication_entry)
                        detail_logger.debug(
                            f"Parsed {self.publication_type} (simple): {publication_name}"
                        )

                    except Exception as e:
                        detail_logger.warning(
                            f"Error parsing simple {self.publication_type} on page {page_num}: {e}"
                        )
                        status_logger.debug(
                            f"    {self.get_name()}: Simple parse error on page {page_num} - {e}"
                        )
                        continue

        except Exception as e:
            detail_logger.error(
                f"Error parsing Kscien {self.publication_type} page {page_num}: {e}"
            )
            status_logger.error(
                f"    {self.get_name()}: Error parsing page {page_num} - {e}"
            )

        return publications

    def _has_next_page(self, html: str, current_page: int) -> bool:
        """Check if there's a next page in Kscien pagination using regex."""
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
                rf'<a[^>]*href=["\'][^"\']*_pagination={next_page}[^"\']*["\'][^>]*>'
            )
            if re.search(next_page_pattern, html, re.IGNORECASE):
                detail_logger.debug(f"Found link to page {next_page}")
                return True

        except Exception as e:
            detail_logger.debug(f"Error checking pagination: {e}")

        return False

    def _deduplicate_publications(
        self, publications: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Remove duplicate publications based on normalized names."""
        seen = set()
        unique_publications = []

        for pub in publications:
            # Normalize the publication name for deduplication
            normalized = input_normalizer.normalize(pub.get("journal_name", ""))
            normalized_name = normalized.normalized_name
            if normalized_name is None:
                continue
            normalized_key = normalized_name.lower()

            if normalized_key not in seen:
                seen.add(normalized_key)
                # Ensure we have the normalized name in the entry
                pub["normalized_name"] = normalized_name
                unique_publications.append(pub)

        return unique_publications
