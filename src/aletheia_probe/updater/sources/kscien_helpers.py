# SPDX-License-Identifier: MIT
"""Shared utility functions for fetching and parsing data from Kscien.org."""

import asyncio
import re
from collections.abc import Callable
from datetime import datetime
from typing import Any, Literal

from aiohttp import ClientSession

from ...logging_config import get_detail_logger, get_status_logger
from ...normalizer import input_normalizer


detail_logger = get_detail_logger()
status_logger = get_status_logger()


PublicationType = Literal[
    "predatory-conferences",
    "standalone-journals",
    "hijacked-journals",
    "publishers",
    "misleading-metrics",
]


async def fetch_kscien_data(
    session: ClientSession,
    publication_type: PublicationType,
    base_url: str,
    max_pages: int,
    get_name: Callable[[], str],
) -> list[dict[str, Any]]:
    """Fetch publications from Kscien.org with pagination support."""
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
                if not _has_next_page(html_content, page):
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


def _parse_kscien_page(
    html: str,
    page_num: int,
    publication_type: PublicationType,
) -> list[dict[str, Any]]:
    """Parse publication names from a Kscien.org page using regex."""
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
                        "list_type": "predatory",
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
            simple_pattern = r"<h4[^>]*>(.*?)</h4>"
            simple_matches = re.findall(simple_pattern, html, re.DOTALL | re.IGNORECASE)

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
                        "source": f"kscien_{publication_type}",
                        "source_url": "https://kscien.org/predatory-publishing/",
                        "page": page_num,
                        "metadata": {
                            "website_url": None,
                            "publication_type": publication_type,
                            "list_type": "predatory",
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


def _has_next_page(html: str, current_page: int) -> bool:
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


def deduplicate_entries(publications: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
