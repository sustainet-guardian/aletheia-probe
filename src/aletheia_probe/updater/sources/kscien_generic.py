# SPDX-License-Identifier: MIT
"""Generic Kscien data source for multiple publication types."""

from datetime import datetime
from typing import Any

from aiohttp import ClientSession, ClientTimeout

from ...cache import DataSourceManager
from ...enums import AssessmentType
from ...logging_config import get_detail_logger, get_status_logger
from ..core import DataSource
from .kscien_helpers import (
    PublicationType,
    deduplicate_entries,
    fetch_kscien_data,
)


# Constants
MAX_PAGINATION_PAGES = 45  # Safety limit for pagination
UPDATE_INTERVAL_DAYS = 7  # Update weekly


detail_logger = get_detail_logger()
status_logger = get_status_logger()


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
        self,
        publication_type: PublicationType,
        list_type: AssessmentType = AssessmentType.PREDATORY,
    ) -> None:
        """Initialize the Kscien generic data source.

        Args:
            publication_type: Type of publications to fetch
            list_type: Assessment type (e.g., PREDATORY or HIJACKED)
        """
        self.publication_type = publication_type
        self.list_type = list_type

        # Configure base URL for the specific publication type
        self.base_url = f"https://kscien.org/predatory-publishing/?_publishing_list={publication_type}"

        self.timeout = ClientTimeout(total=60)
        self.max_pages = MAX_PAGINATION_PAGES

    def get_name(self) -> str:
        """Return the data source identifier."""
        return f"kscien_{self.publication_type.replace('-', '_')}"

    def get_list_type(self) -> AssessmentType:
        """Return the list type (predatory, hijacked, etc.)."""
        return self.list_type

    def should_update(self) -> bool:
        """Check if we should update (weekly for static lists)."""
        if not self.base_url:
            detail_logger.debug(
                f"Kscien {self.publication_type} source has no configured URL, skipping update"
            )
            self.skip_reason = "no_url_configured"
            return False

        data_source_manager = DataSourceManager()
        last_update = data_source_manager.get_source_last_updated(self.get_name())
        if last_update is None:
            detail_logger.info(
                f"No previous update found for kscien {self.publication_type}, will update"
            )
            return True

        # Update weekly
        days_since_update = (datetime.now() - last_update).days
        if days_since_update < UPDATE_INTERVAL_DAYS:
            detail_logger.debug(
                f"Last update was {days_since_update} days ago, not updating"
            )
            self.skip_reason = "already_up_to_date"
            return False

        return True

    async def fetch_data(self) -> list[dict[str, Any]]:
        """Fetch data from Kscien for the specified publication type.

        Returns:
            List of publication entries with normalized names
        """
        detail_logger.info(f"Starting Kscien {self.publication_type} data fetch")
        status_logger.info(f"    {self.get_name()}: Starting data fetch")

        try:
            all_publications = []
            async with ClientSession(timeout=self.timeout) as session:
                publications = await fetch_kscien_data(
                    session,
                    self.publication_type,
                    self.base_url,
                    self.max_pages,
                    self.get_name,
                )
                all_publications.extend(publications)
                status_logger.info(
                    f"    {self.get_name()}: Retrieved {len(publications)} raw entries"
                )

            # Remove duplicates based on normalized name
            unique_publications = deduplicate_entries(all_publications)
            detail_logger.info(
                f"Total unique {self.publication_type} after deduplication: {len(unique_publications)}"
            )
            status_logger.info(
                f"    {self.get_name()}: Processed {len(unique_publications)} unique entries"
            )

            return unique_publications
        except Exception as e:
            detail_logger.error(
                f"Error in fetch_data for Kscien {self.publication_type}: {e}"
            )
            status_logger.error(f"    {self.get_name()}: Fetch failed - {e}")
            return []


# Note: KscienGenericSource is registered with specific parameters in updater/__init__.py
# because it requires a publication_type parameter
