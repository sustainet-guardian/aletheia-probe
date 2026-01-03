# SPDX-License-Identifier: MIT
"""Core updater classes and base abstractions."""

from abc import ABC, abstractmethod
from typing import Any

from ..enums import AssessmentType


class DataSource(ABC):
    """Abstract base class for data sources.

    Data sources are responsible for fetching and parsing journal data
    from external sources (web APIs, files, databases, etc.). Each source
    implements this interface to provide a consistent way to update the
    local cache.

    Backends use DataSource instances via the DataSyncCapable protocol
    to synchronize their data.
    """

    @abstractmethod
    def get_name(self) -> str:
        """Return the source name.

        Returns:
            Unique identifier for this data source
        """
        pass

    @abstractmethod
    def get_list_type(self) -> AssessmentType:
        """Return the list type as AssessmentType enum member.

        Returns:
            Assessment type (PREDATORY, LEGITIMATE, etc.)
        """
        pass

    @abstractmethod
    async def fetch_data(self) -> list[dict[str, Any]]:
        """Fetch and parse data from the source.

        Returns:
            List of dictionaries with journal information.
            Each dictionary should contain normalized journal data.
        """
        pass

    @abstractmethod
    def should_update(self) -> bool:
        """Check if this source needs updating.

        Returns:
            True if data should be fetched, False if current data is fresh
        """
        pass
