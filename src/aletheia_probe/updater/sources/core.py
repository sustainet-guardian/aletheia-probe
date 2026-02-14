# SPDX-License-Identifier: MIT
"""CORE/ICORE conference and journal ranking data sources."""

import asyncio
import math
import re
from datetime import datetime
from html import unescape
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from ...cache import DataSourceManager
from ...config import get_config_manager
from ...enums import AssessmentType
from ...logging_config import get_detail_logger, get_status_logger
from ...normalizer import input_normalizer
from ..core import DataSource
from ..utils import deduplicate_journals


detail_logger = get_detail_logger()
status_logger = get_status_logger()

DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_UPDATE_INTERVAL_DAYS = 30
DEFAULT_PAGE_SIZE = 50
DEFAULT_MAX_PAGES = 200
DEFAULT_MAX_FETCH_RETRIES = 3
DEFAULT_RETRY_BASE_DELAY_SECONDS = 1.0

_VALID_LEGITIMATE_RANKS = {
    "A*",
    "A",
    "B",
    "C",
    "AUSTRALASIAN B",
    "AUSTRALASIAN C",
}


class _CorePortalSourceBase(DataSource):
    """Shared CORE portal scraping behavior for paginated ranking pages."""

    def __init__(
        self,
        source_name: str,
        portal_url: str,
        source_filter: str,
    ) -> None:
        self._source_name = source_name
        self.portal_url = portal_url
        self.source_filter = source_filter

    def get_name(self) -> str:
        """Return unique source name."""
        return self._source_name

    def get_list_type(self) -> AssessmentType:
        """Return list type for CORE ranking sources."""
        return AssessmentType.LEGITIMATE

    def should_update(self) -> bool:
        """Check if source should be refreshed from CORE portal."""
        data_source_manager = DataSourceManager()
        last_update = data_source_manager.get_source_last_updated(self.get_name())
        if last_update is None:
            return True

        if (datetime.now() - last_update).days < DEFAULT_UPDATE_INTERVAL_DAYS:
            self.skip_reason = "already_up_to_date"
            return False

        return True

    async def fetch_data(self) -> list[dict[str, Any]]:
        """Fetch all portal pages and parse ranked venue entries."""
        status_logger.info(f"    {self.get_name()}: Starting data fetch")

        all_entries: list[dict[str, Any]] = []
        total_results: int | None = None

        page = 1
        while page <= DEFAULT_MAX_PAGES:
            html_content = await self._fetch_page(page)
            if not html_content:
                break

            if total_results is None:
                total_results = self._extract_total_results(html_content)

            page_entries = self._parse_entries(html_content)
            if not page_entries:
                break

            all_entries.extend(page_entries)

            if total_results is None:
                page += 1
                continue

            total_pages = math.ceil(total_results / DEFAULT_PAGE_SIZE)
            if page >= total_pages:
                break
            page += 1

        deduplicated_entries = deduplicate_journals(all_entries)
        status_logger.info(
            f"    {self.get_name()}: Processed {len(deduplicated_entries)} unique entries"
        )
        detail_logger.info(
            f"{self.get_name()}: Parsed {len(all_entries)} entries from {self.portal_url}"
        )
        return deduplicated_entries

    async def _fetch_page(self, page: int) -> str:
        """Fetch one portal results page via urllib with retries."""
        params = {
            "search": "",
            "by": "all",
            "source": self.source_filter,
            "sort": "atitle",
            "page": page,
        }
        query = urlencode(params)
        url = f"{self.portal_url}?{query}"
        for attempt in range(1, DEFAULT_MAX_FETCH_RETRIES + 1):
            try:
                return await asyncio.to_thread(self._fetch_page_once, url)
            except (URLError, TimeoutError, OSError) as e:
                if attempt >= DEFAULT_MAX_FETCH_RETRIES:
                    status_logger.warning(
                        f"    {self.get_name()}: Page {page} request failed after "
                        f"{DEFAULT_MAX_FETCH_RETRIES} attempts - "
                        f"{type(e).__name__}: {e!r}"
                    )
                    return ""

                status_logger.warning(
                    f"    {self.get_name()}: Page {page} attempt {attempt}/"
                    f"{DEFAULT_MAX_FETCH_RETRIES} failed - {type(e).__name__}. Retrying..."
                )
                await asyncio.sleep(DEFAULT_RETRY_BASE_DELAY_SECONDS * attempt)

        return ""

    def _fetch_page_once(self, url: str) -> str:
        """Perform one blocking urllib fetch and return UTF-8 decoded body."""
        with urlopen(url, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
            if response.status != 200:
                raise URLError(f"HTTP {response.status}")
            content = response.read()
        return content.decode("utf-8", errors="ignore")

    @staticmethod
    def _extract_total_results(html_content: str) -> int | None:
        """Extract total result count from the portal summary line."""
        match = re.search(
            r"Showing\s+results\s+\d+\s*-\s*\d+\s+of\s+(\d+)",
            html_content,
            re.IGNORECASE,
        )
        if not match:
            return None
        return int(match.group(1))

    @staticmethod
    def _clean_html_text(value: str) -> str:
        """Convert HTML fragments to compact plain text."""
        cleaned = re.sub(r"<[^>]+>", " ", value)
        cleaned = unescape(cleaned)
        return re.sub(r"\s+", " ", cleaned).strip()

    @staticmethod
    def _is_ranked_legitimate(rank: str) -> bool:
        """Return True for ranked classes that indicate legitimate standing."""
        return rank.strip().upper() in _VALID_LEGITIMATE_RANKS

    def _parse_entries(self, html_content: str) -> list[dict[str, Any]]:
        """Parse portal-specific HTML into normalized entries."""
        raise NotImplementedError("Subclasses must implement entry parsing")


class CoreConferenceSource(_CorePortalSourceBase):
    """Data source for CORE/ICORE conference rankings."""

    def __init__(self) -> None:
        config = get_config_manager().load_config()
        super().__init__(
            source_name="core_conferences",
            portal_url=config.data_source_urls.core_conference_rankings_url,
            source_filter=config.data_source_urls.core_conference_default_source,
        )

    def _parse_entries(self, html_content: str) -> list[dict[str, Any]]:
        """Parse conference table rows into normalized venue entries."""
        rows = re.findall(
            r'<tr\s+class="(?:evenrow|oddrow)"[^>]*>(.*?)</tr>',
            html_content,
            re.IGNORECASE | re.DOTALL,
        )

        entries: list[dict[str, Any]] = []
        for row in rows:
            cells = re.findall(
                r"<td[^>]*>(.*?)</td>",
                row,
                re.IGNORECASE | re.DOTALL,
            )
            if len(cells) < 4:
                continue

            title = self._clean_html_text(cells[0])
            acronym = self._clean_html_text(cells[1])
            source = self._clean_html_text(cells[2])
            rank = self._clean_html_text(cells[3])

            if not title or not self._is_ranked_legitimate(rank):
                continue

            try:
                normalized = input_normalizer.normalize(title)
            except Exception as e:
                detail_logger.debug(
                    f"{self.get_name()}: Failed to normalize title '{title}' - {e}"
                )
                continue

            entries.append(
                {
                    "journal_name": title,
                    "normalized_name": normalized.normalized_name,
                    "metadata": {
                        "source_url": self.portal_url,
                        "core_entity_type": "conference",
                        "core_source": source,
                        "core_rank": rank,
                        "core_acronym": acronym or None,
                    },
                }
            )

        return entries


class CoreJournalSource(_CorePortalSourceBase):
    """Data source for CORE journal rankings (legacy dataset)."""

    def __init__(self) -> None:
        config = get_config_manager().load_config()
        super().__init__(
            source_name="core_journals",
            portal_url=config.data_source_urls.core_journal_rankings_url,
            source_filter=config.data_source_urls.core_journal_default_source,
        )

    def _parse_entries(self, html_content: str) -> list[dict[str, Any]]:
        """Parse journal table rows into normalized journal entries."""
        rows = re.findall(
            r'<tr\s+class="(?:evenrow|oddrow)"[^>]*>(.*?)</tr>',
            html_content,
            re.IGNORECASE | re.DOTALL,
        )

        entries: list[dict[str, Any]] = []
        for row in rows:
            cells = re.findall(
                r"<td[^>]*>(.*?)</td>",
                row,
                re.IGNORECASE | re.DOTALL,
            )
            if len(cells) < 3:
                continue

            title = self._clean_html_text(cells[0])
            source = self._clean_html_text(cells[1])
            rank = self._clean_html_text(cells[2])

            if not title or not self._is_ranked_legitimate(rank):
                continue

            try:
                normalized = input_normalizer.normalize(title)
            except Exception as e:
                detail_logger.debug(
                    f"{self.get_name()}: Failed to normalize title '{title}' - {e}"
                )
                continue

            entries.append(
                {
                    "journal_name": title,
                    "normalized_name": normalized.normalized_name,
                    "metadata": {
                        "source_url": self.portal_url,
                        "core_entity_type": "journal",
                        "core_source": source,
                        "core_rank": rank,
                    },
                }
            )

        return entries
