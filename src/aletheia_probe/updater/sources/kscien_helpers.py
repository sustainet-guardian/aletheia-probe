# SPDX-License-Identifier: MIT
"""Shared utility functions for fetching and parsing data from Kscien.org."""

import asyncio
import re
from collections.abc import Callable
from datetime import datetime
from enum import Enum
from typing import Any

from aiohttp import ClientSession

from ...enums import AssessmentType
from ...logging_config import get_detail_logger, get_status_logger
from ...normalizer import input_normalizer


# Maximum reasonable count for an individual Kscien publication type.
# Used to distinguish between type-specific counts and the global total.
KSCIEN_TYPE_COUNT_THRESHOLD = 2000


detail_logger = get_detail_logger()
status_logger = get_status_logger()


class PublicationType(str, Enum):
    """Kscien publication types."""

    PREDATORY_CONFERENCES = "predatory-conferences"
    STANDALONE_JOURNALS = "standalone-journals"
    HIJACKED_JOURNALS = "hijacked-journals"
    PUBLISHERS = "publishers"
    MISLEADING_METRICS = "misleading-metrics"


async def fetch_kscien_data(
    session: ClientSession,
    publication_type: PublicationType,
    base_url: str,
    max_pages: int,
    get_name: Callable[[], str],
) -> list[dict[str, Any]]:
    """Fetch publications from Kscien.org with pagination support.

    Args:
        session: The aiohttp ClientSession to use for requests.
        publication_type: The type of publication to fetch.
        base_url: The base URL to start fetching from.
        max_pages: The maximum number of pages to fetch.
        get_name: A callback function to get the name of the caller for logging.

    Returns:
        A list of dictionaries, where each dictionary represents a fetched publication
        containing details such as journal name, source, and metadata.
    """
    all_publications = []
    page = 1
    expected_count = None

    while page <= max_pages:
        try:
            # Construct URL for specific page
            if page == 1:
                url = base_url
            else:
                # Kscien pagination requires BOTH _publishing_list and _pagination parameters
                url = f"https://kscien.org/predatory-publishing/?_publishing_list={publication_type}&_pagination={page}"

            detail_logger.debug(
                f"Fetching Kscien {publication_type} page {page}: {url}"
            )

            async with session.get(url) as response:
                if response.status != 200:
                    detail_logger.warning(f"HTTP {response.status} from {url}")
                    status_logger.warning(
                        f"    {get_name()}: HTTP {response.status} from page {page}"
                    )
                    break

                html_content = await response.text()

                # Extract expected count from first page
                if page == 1:
                    expected_count = _extract_expected_count(
                        html_content, publication_type
                    )
                    if expected_count:
                        detail_logger.info(
                            f"Expecting {expected_count} total {publication_type} entries"
                        )

                page_publications = _parse_kscien_page(
                    html_content, page, publication_type
                )

                if not page_publications:
                    detail_logger.info(
                        f"No {publication_type} found on page {page}, stopping pagination"
                    )
                    break

                all_publications.extend(page_publications)
                detail_logger.debug(
                    f"Found {len(page_publications)} {publication_type} on page {page}"
                )

                # Check if there's a next page
                if not _has_next_page(
                    html_content, page, expected_count, len(all_publications)
                ):
                    detail_logger.info(f"Reached last page at page {page}")
                    break

            page += 1

            # Small delay to be respectful to the server
            await asyncio.sleep(0.5)

        except Exception as e:
            detail_logger.error(
                f"Error fetching Kscien {publication_type} page {page}: {e}"
            )
            status_logger.error(f"    {get_name()}: Error fetching page {page} - {e}")
            break

    actual_count = len(all_publications)
    if expected_count:
        if actual_count == expected_count:
            detail_logger.info(
                f"✅ Successfully fetched {actual_count}/{expected_count} {publication_type} from Kscien across {page - 1} pages"
            )
        else:
            detail_logger.warning(
                f"⚠️ Count mismatch: fetched {actual_count} but expected {expected_count} {publication_type} (across {page - 1} pages)"
            )
            status_logger.warning(
                f"    {get_name()}: Count mismatch - got {actual_count}, expected {expected_count}"
            )
    else:
        detail_logger.info(
            f"Fetched {actual_count} {publication_type} from Kscien across {page - 1} pages"
        )

    return all_publications


def _extract_expected_count(html: str, publication_type: PublicationType) -> int | None:
    """Extract the expected total count for this publication type from the page.

    Args:
        html: The HTML content of the page.
        publication_type: The type of publication being processed.

    Returns:
        The expected count as an integer if found, or None if not found.
    """
    try:
        # First try to find the specific count in the filter sections
        # Pattern: "Predatory Conferences (499)" or similar
        type_display_names = {
            PublicationType.PREDATORY_CONFERENCES: r"Predatory\s+Conferences?\s*\(\s*(\d+)\s*\)",
            PublicationType.STANDALONE_JOURNALS: r"Standalone\s+Journals?\s*\(\s*(\d+)\s*\)",
            PublicationType.HIJACKED_JOURNALS: r"Hijacked\s+Journals?\s*\(\s*(\d+)\s*\)",
            PublicationType.PUBLISHERS: r"Publishers?\s*\(\s*(\d+)\s*\)",
            PublicationType.MISLEADING_METRICS: r"Misleading\s+Metrics?\s*\(\s*(\d+)\s*\)",
        }

        pattern = type_display_names.get(publication_type)
        if pattern:
            count_match = re.search(pattern, html, re.IGNORECASE)
            if count_match:
                count = int(count_match.group(1))
                detail_logger.debug(
                    f"Found {publication_type} count in filter: {count}"
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
            # Only use if it's reasonable for the specific type
            if total_count < KSCIEN_TYPE_COUNT_THRESHOLD:
                return total_count
            else:
                detail_logger.debug(
                    f"Pagination count {total_count} seems like total across all types, ignoring"
                )

    except Exception as e:
        detail_logger.debug(f"Error extracting expected count: {e}")

    return None


def _parse_kscien_page(
    html: str,
    page_num: int,
    publication_type: PublicationType,
) -> list[dict[str, Any]]:
    """Parse publication names from a Kscien.org page using regex.

    Args:
        html: The HTML content of the page to parse.
        page_num: The current page number being parsed.
        publication_type: The type of publication being parsed.

    Returns:
        A list of dictionaries, where each dictionary represents a parsed publication entry
        containing metadata and source information.
    """
    publications = []

    try:
        # Pattern to match h4 headings followed by "Visit Website" links
        pattern = r'<h4[^>]*>(.*?)</h4>\s*<p[^>]*>.*?<a[^>]*href=["\']([^"\']*)["\'][^>]*>.*?Visit\s+Website.*?</a>'
        matches = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)

        for publication_name_raw, website_url in matches:
            try:
                # Clean the publication name
                publication_name = re.sub(r"<[^>]+>", "", publication_name_raw).strip()
                if not publication_name:
                    continue

                # Clean the URL
                website_url = website_url.strip()

                # Create publication entry
                publication_entry = {
                    "journal_name": publication_name,  # Core updater expects this field name
                    "normalized_name": None,  # Will be set during deduplication
                    "source": f"kscien_{publication_type}",
                    "source_url": "https://kscien.org/predatory-publishing/",
                    "page": page_num,
                    "metadata": {
                        "website_url": website_url,
                        "publication_type": publication_type,
                        "list_type": AssessmentType.PREDATORY.value,
                        "authority_level": 8,  # High authority like Beall's
                        "last_verified": datetime.now().isoformat(),
                    },
                }

                publications.append(publication_entry)
                detail_logger.debug(f"Parsed {publication_type}: {publication_name}")

            except Exception as e:
                detail_logger.warning(
                    f"Error parsing individual {publication_type} on page {page_num}: {e}"
                )
                status_logger.debug(
                    f"    kscien_{publication_type}: Parse error on page {page_num} - {e}"
                )
                continue

        # Alternative pattern for publications without "Visit Website" links
        if not publications:
            # UI elements to exclude - these are common page elements, not publications
            ui_elements = {
                "lorem ipsum dolor sit amet consectetur adipiscing elit",
                "contact",
                "publishing search",
                "publishing list",
                "reset",
                "publishing resault count",
                "publishing result count",
                "publishing sort list",
                "visit website",
                "read more",
                "learn more",
                "search",
                "filter",
                "sort by",
                "show all",
                "hide all",
                "next",
                "previous",
                "page",
            }

            simple_pattern = r"<h4[^>]*>(.*?)</h4>"
            simple_matches = re.findall(simple_pattern, html, re.DOTALL | re.IGNORECASE)

            for publication_name_raw in simple_matches:
                try:
                    publication_name = re.sub(
                        r"<[^>]+>", "", publication_name_raw
                    ).strip()
                    if not publication_name or len(publication_name) < 5:
                        continue

                    # Skip UI elements
                    if publication_name.lower() in ui_elements:
                        continue

                    publication_entry = {
                        "journal_name": publication_name,
                        "normalized_name": None,
                        "source": f"kscien_{publication_type}",
                        "source_url": "https://kscien.org/predatory-publishing/",
                        "page": page_num,
                        "metadata": {
                            "website_url": None,
                            "publication_type": publication_type,
                            "list_type": AssessmentType.PREDATORY.value,
                            "authority_level": 8,
                            "last_verified": datetime.now().isoformat(),
                        },
                    }

                    publications.append(publication_entry)
                    detail_logger.debug(
                        f"Parsed {publication_type} (simple): {publication_name}"
                    )

                except Exception as e:
                    detail_logger.warning(
                        f"Error parsing simple {publication_type} on page {page_num}: {e}"
                    )
                    status_logger.debug(
                        f"    kscien_{publication_type}: Simple parse error on page {page_num} - {e}"
                    )
                    continue

    except Exception as e:
        detail_logger.error(
            f"Error parsing Kscien {publication_type} page {page_num}: {e}"
        )
        status_logger.error(
            f"    kscien_{publication_type}: Error parsing page {page_num} - {e}"
        )

    return publications


def _has_next_page(
    html: str, current_page: int, expected_count: int | None, items_fetched: int
) -> bool:
    """Check if there's a next page in Kscien pagination.

    Args:
        html: The HTML content of the current page.
        current_page: The current page number.
        expected_count: Expected total count for this publication type (if available).
        items_fetched: Number of items fetched so far.

    Returns:
        True if there are more pages to fetch, False otherwise.
    """
    try:
        # If we have the expected count for this specific publication type, use it
        if expected_count is not None:
            # If we've fetched all expected items, no more pages
            if items_fetched >= expected_count:
                detail_logger.debug(
                    f"Fetched {items_fetched}/{expected_count} items, no more pages"
                )
                return False

            detail_logger.debug(
                f"Fetched {items_fetched}/{expected_count} items so far, continuing"
            )

        # Check for numbered pagination links to next page
        next_page = current_page + 1
        next_page_pattern = (
            rf'<a[^>]*href=["\'][^"\']*_pagination={next_page}[^"\']*["\'][^>]*>'
        )
        if re.search(next_page_pattern, html, re.IGNORECASE):
            detail_logger.debug(f"Found link to page {next_page}")
            return True

        # Note: The pagination text "1 - 90 of 3539" is static and shows the total
        # across ALL categories, not the specific publication type, so we don't use it
        detail_logger.debug(f"No pagination link found for page {next_page}")

    except Exception as e:
        detail_logger.debug(f"Error checking pagination: {e}")

    return False


def deduplicate_entries(publications: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove duplicate publications based on normalized names.

    Args:
        publications: A list of publication dictionaries to deduplicate.

    Returns:
        A list of unique publication dictionaries, where uniqueness is determined
        by the normalized name.
    """
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
