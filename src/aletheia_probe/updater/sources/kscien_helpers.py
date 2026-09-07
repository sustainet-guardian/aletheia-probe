# SPDX-License-Identifier: MIT
"""Shared utility functions for fetching and parsing data from Kscien.org."""

import asyncio
import html
import re
from collections.abc import Callable
from datetime import datetime
from enum import Enum
from typing import Any

from aiohttp import ClientError, ClientSession

from ...enums import AssessmentType
from ...logging_config import get_detail_logger, get_status_logger
from ...normalizer import input_normalizer


KSCIEN_LIST_PAGE_URL = "https://kscien.org/non-recommended-journals-lists/"
KSCIEN_REST_URL = "https://kscien.org/wp-json/wp/v2/predatory-publishing"
KSCIEN_REST_PER_PAGE = 100
KSCIEN_REST_PAGE_DELAY_SECONDS = 0.5
KSCIEN_REST_MAX_ATTEMPTS = 4
KSCIEN_REST_RETRY_BASE_DELAY_SECONDS = 1.0
KSCIEN_REST_RETRY_STATUSES = {429, 500, 502, 503, 504}
_KSCIEN_REST_REQUEST_LOCK = asyncio.Lock()


detail_logger = get_detail_logger()
status_logger = get_status_logger()


class PublicationType(str, Enum):
    """Kscien publication types."""

    PREDATORY_CONFERENCES = "predatory-conferences"
    STANDALONE_JOURNALS = "standalone-journals"
    HIJACKED_JOURNALS = "hijacked-journals"
    PUBLISHERS = "publishers"
    MISLEADING_METRICS = "misleading-metrics"


KSCIEN_TAXONOMY_IDS = {
    PublicationType.HIJACKED_JOURNALS: 10,
    PublicationType.MISLEADING_METRICS: 11,
    PublicationType.PREDATORY_CONFERENCES: 12,
    PublicationType.PUBLISHERS: 13,
    PublicationType.STANDALONE_JOURNALS: 14,
}


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
    return await _fetch_kscien_rest_data(session, publication_type, max_pages, get_name)


async def _fetch_kscien_rest_data(
    session: ClientSession,
    publication_type: PublicationType,
    max_pages: int,
    get_name: Callable[[], str],
) -> list[dict[str, Any]]:
    """Fetch Kscien entries from the current WordPress REST API."""
    taxonomy_id = KSCIEN_TAXONOMY_IDS.get(publication_type)
    if taxonomy_id is None:
        detail_logger.warning(f"No Kscien taxonomy ID for {publication_type}")
        return []

    publications = []
    expected_count = None

    for page in range(1, max_pages + 1):
        params = {
            "per_page": KSCIEN_REST_PER_PAGE,
            "page": page,
            "publishing-taxonomy": taxonomy_id,
        }
        try:
            page_result = await _fetch_kscien_rest_page(
                session, params, page, publication_type, get_name
            )
            if page_result is None:
                break

            page_items, total_count, total_pages = page_result
            if expected_count is None:
                expected_count = total_count

            if not isinstance(page_items, list) or not page_items:
                detail_logger.info(
                    f"No {publication_type} found on REST page {page}, stopping pagination"
                )
                break

            page_publications = [
                publication
                for item in page_items
                if (
                    publication := _parse_kscien_rest_item(item, page, publication_type)
                )
            ]
            publications.extend(page_publications)

            if page >= total_pages:
                break

        except ValueError:
            raise
        except Exception as e:
            detail_logger.error(
                f"Error fetching Kscien {publication_type} REST page {page}: {e}"
            )
            status_logger.error(
                f"    {get_name()}: Error fetching REST page {page} - {e}"
            )
            break

        await asyncio.sleep(KSCIEN_REST_PAGE_DELAY_SECONDS)

    actual_count = len(publications)
    if expected_count is not None and actual_count != expected_count:
        message = (
            f"Kscien REST count mismatch: fetched {actual_count}, "
            f"expected {expected_count} {publication_type}"
        )
        detail_logger.warning(f"⚠️ {message}")
        status_logger.warning(
            f"    {get_name()}: Count mismatch - got {actual_count}, expected {expected_count}"
        )
        raise ValueError(message)
    elif expected_count is not None:
        detail_logger.info(
            f"✅ Successfully fetched {actual_count}/{expected_count} {publication_type} from Kscien REST"
        )

    return publications


async def _fetch_kscien_rest_page(
    session: ClientSession,
    params: dict[str, int],
    page: int,
    publication_type: PublicationType,
    get_name: Callable[[], str],
) -> tuple[list[Any], int | None, int] | None:
    """Fetch one Kscien REST page with retry handling for transient failures."""
    for attempt in range(1, KSCIEN_REST_MAX_ATTEMPTS + 1):
        retry_status = None
        try:
            detail_logger.debug(
                f"Fetching Kscien {publication_type} REST page {page}: {KSCIEN_REST_URL}"
            )
            async with _KSCIEN_REST_REQUEST_LOCK:
                async with session.get(KSCIEN_REST_URL, params=params) as response:
                    if response.status == 400 and page > 1:
                        detail_logger.debug(
                            f"Kscien REST page {page} returned 400, stopping pagination"
                        )
                        return None

                    if response.status == 200:
                        total_header = response.headers.get("X-WP-Total")
                        total_pages_header = response.headers.get("X-WP-TotalPages")
                        total_count = int(total_header) if total_header else None
                        total_pages = (
                            int(total_pages_header) if total_pages_header else page
                        )
                        page_items = await response.json(content_type=None)
                        return page_items, total_count, total_pages

                    if (
                        response.status in KSCIEN_REST_RETRY_STATUSES
                        and attempt < KSCIEN_REST_MAX_ATTEMPTS
                    ):
                        retry_status = response.status
                    else:
                        raise ValueError(
                            f"HTTP {response.status} from REST page {page}"
                        )

        except (ClientError, TimeoutError) as e:
            if attempt >= KSCIEN_REST_MAX_ATTEMPTS:
                raise ValueError(
                    f"Kscien REST page {page} failed after {attempt} attempts: {e}"
                ) from e
            await _sleep_before_retry(page, attempt, get_name, error=e)
            continue

        if retry_status is not None:
            await _sleep_before_retry(page, attempt, get_name, status=retry_status)
            continue

    raise ValueError(
        f"Kscien REST page {page} failed after {KSCIEN_REST_MAX_ATTEMPTS} attempts"
    )


async def _sleep_before_retry(
    page: int,
    attempt: int,
    get_name: Callable[[], str],
    status: int | None = None,
    error: BaseException | None = None,
) -> None:
    """Sleep before retrying a transient Kscien REST failure."""
    delay = KSCIEN_REST_RETRY_BASE_DELAY_SECONDS * attempt
    if status is not None:
        detail_logger.warning(
            f"Kscien REST page {page} returned HTTP {status}; retrying in {delay:.1f}s"
        )
        status_logger.warning(
            f"    {get_name()}: HTTP {status} from REST page {page}, retrying"
        )
    elif error is not None:
        detail_logger.warning(
            f"Kscien REST page {page} failed with {error}; retrying in {delay:.1f}s"
        )
        status_logger.warning(
            f"    {get_name()}: REST page {page} failed, retrying - {error}"
        )

    await asyncio.sleep(delay)


def _parse_kscien_rest_item(
    item: Any,
    page_num: int,
    publication_type: PublicationType,
) -> dict[str, Any] | None:
    """Parse one Kscien WordPress REST API item into cache input format."""
    if not isinstance(item, dict):
        return None

    title = item.get("title", {})
    publication_name = title.get("rendered") if isinstance(title, dict) else title
    if not isinstance(publication_name, str):
        return None

    publication_name = _clean_html_text(publication_name)
    if not publication_name:
        return None

    content = item.get("content", {})
    rendered_content = (
        content.get("rendered", "") if isinstance(content, dict) else str(content or "")
    )
    website_url = _extract_website_url(rendered_content)

    return {
        "journal_name": publication_name,
        "normalized_name": None,
        "source": f"kscien_{publication_type.value}",
        "source_url": KSCIEN_LIST_PAGE_URL,
        "page": page_num,
        "metadata": {
            "website_url": website_url,
            "publication_type": publication_type.value,
            "list_type": AssessmentType.PREDATORY.value,
            "authority_level": 8,
            "last_verified": datetime.now().isoformat(),
            "kscien_post_id": item.get("id"),
            "kscien_post_url": item.get("link"),
        },
    }


def _clean_html_text(value: str) -> str:
    """Strip HTML tags/entities and normalize whitespace."""
    without_tags = re.sub(r"<[^>]+>", " ", value)
    return " ".join(html.unescape(without_tags).split()).strip()


def _extract_website_url(rendered_content: str) -> str | None:
    """Extract the listed publication website URL from rendered item content."""
    href_match = re.search(r'href=["\']([^"\']+)["\']', rendered_content, re.IGNORECASE)
    if href_match:
        return html.unescape(href_match.group(1)).strip()

    text = _clean_html_text(rendered_content)
    url_match = re.search(r"https?://\S+", text)
    if url_match:
        return url_match.group(0).rstrip(".,;)")
    return None


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
        normalized_name = (
            normalized.normalized_venue.name if normalized.normalized_venue else ""
        )
        if normalized_name is None:
            continue
        normalized_key = normalized_name.lower()

        if normalized_key not in seen:
            seen.add(normalized_key)
            # Ensure we have the normalized name in the entry
            pub["normalized_name"] = normalized_name
            unique_publications.append(pub)

    return unique_publications
