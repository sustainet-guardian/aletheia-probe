# SPDX-License-Identifier: MIT
"""Beall's List predatory journal data source."""

import asyncio
from datetime import datetime
from typing import Any

from aiohttp import ClientSession, ClientTimeout

from ...cache import get_cache_manager
from ...enums import AssessmentType
from ...logging_config import get_detail_logger, get_status_logger
from ..core import DataSource
from ..utils import deduplicate_journals
from .bealls_helpers import BeallsHTMLParser


detail_logger = get_detail_logger()
status_logger = get_status_logger()


class BeallsListSource(DataSource):
    """Data source for Beall's predatory journal list from archived sources."""

    def __init__(self) -> None:
        # URLs for different sources of Beall's archived list
        self.sources = {
            "beallslist_publishers": "https://beallslist.net/",
            "beallslist_standalone": "https://beallslist.net/standalone-journals/",
        }
        self.timeout = ClientTimeout(total=30)
        self.parser = BeallsHTMLParser()

    def get_name(self) -> str:
        return "bealls"

    def get_list_type(self) -> AssessmentType:
        return AssessmentType.PREDATORY

    def should_update(self) -> bool:
        """Check if we should update (weekly for static lists)."""
        last_update = get_cache_manager().get_source_last_updated(self.get_name())
        if last_update is None:
            return True

        # Update weekly
        return (datetime.now() - last_update).days >= 7

    async def fetch_data(self) -> list[dict[str, Any]]:
        """Fetch Beall's list data from multiple sources."""
        status_logger.info(f"    {self.get_name()}: Starting data fetch")
        all_journals = []

        async with ClientSession(timeout=self.timeout) as session:
            # Try each source
            for source_name, url in self.sources.items():
                try:
                    detail_logger.info(f"Fetching data from {source_name}: {url}")
                    journals = await self._fetch_from_source(session, url, source_name)
                    all_journals.extend(journals)
                    detail_logger.info(
                        f"Successfully fetched {len(journals)} entries from {source_name}"
                    )
                    status_logger.info(
                        f"    {self.get_name()}: Retrieved {len(journals)} entries from {source_name}"
                    )
                except Exception as e:
                    status_logger.error(
                        f"    {self.get_name()}: Failed to fetch from {source_name} - {e}"
                    )

        # Remove duplicates based on normalized name
        unique_journals = deduplicate_journals(all_journals)
        detail_logger.info(
            f"Total unique journals after deduplication: {len(unique_journals)}"
        )
        status_logger.info(
            f"    {self.get_name()}: Processed {len(unique_journals)} unique entries"
        )

        return unique_journals

    async def _fetch_from_source(
        self, session: ClientSession, url: str, source_name: str
    ) -> list[dict[str, Any]]:
        """Fetch journal data from a specific source."""
        journals = []

        try:
            async with session.get(url) as response:
                if response.status == 200:
                    html_content = await response.text()
                    journals = self.parser.parse_beallslist_html(html_content, url)

                else:
                    detail_logger.warning(f"HTTP {response.status} from {url}")
                    status_logger.warning(
                        f"    {self.get_name()}: HTTP {response.status} from {url}"
                    )

        except asyncio.TimeoutError:
            detail_logger.error(f"Timeout fetching from {url}")
            status_logger.error(f"    {self.get_name()}: Timeout fetching from {url}")
        except Exception as e:
            detail_logger.error(f"Error fetching from {url}: {e}")
            status_logger.error(f"    {self.get_name()}: Error - {e}")

        return journals
