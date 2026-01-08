# SPDX-License-Identifier: MIT
"""Backend for user-provided custom journal lists from CSV/JSON files."""

from pathlib import Path
from typing import TYPE_CHECKING

from ..enums import AssessmentType, EvidenceType
from ..utils.dead_code import code_is_used
from .base import CachedBackend


if TYPE_CHECKING:
    from ..updater.core import DataSource
    from ..updater.sources.custom import CustomListSource


class CustomListBackend(CachedBackend):
    """Backend that checks against user-provided custom journal lists.

    Supports CSV and JSON file formats. Users can add custom lists via CLI
    to supplement the built-in predatory/legitimate journal lists.
    """

    def __init__(
        self,
        file_path: Path,
        list_type: AssessmentType,
        source_name: str,
    ) -> None:
        """Initialize the custom list backend.

        Args:
            file_path: Path to CSV or JSON file containing journal list
            list_type: Type of assessment (PREDATORY, LEGITIMATE, etc.)
            source_name: Unique name for this custom list

        Sets up cache with 24-hour TTL as custom lists are file-based
        and may be updated by the user.
        """
        super().__init__(
            source_name=source_name,
            list_type=list_type,
            cache_ttl_hours=24,  # Daily refresh for file-based lists
        )
        self.file_path = file_path
        self._data_source: CustomListSource | None = None

    def get_name(self) -> str:
        """Return the backend identifier.

        Returns:
            The source name provided during initialization
        """
        return self.source_name

    @code_is_used  # Polymorphic method called via Backend interface
    def get_evidence_type(self) -> EvidenceType:
        """Return the type of evidence this backend provides.

        Returns:
            EvidenceType based on the list_type:
            - PREDATORY_LIST for predatory assessments
            - LEGITIMATE_LIST for legitimate assessments
            - HEURISTIC for unknown list types
        """
        if self.list_type == AssessmentType.PREDATORY:
            return EvidenceType.PREDATORY_LIST
        elif self.list_type == AssessmentType.LEGITIMATE:
            return EvidenceType.LEGITIMATE_LIST
        else:
            # Default to heuristic for unknown list types
            return EvidenceType.HEURISTIC

    def get_data_source(self) -> "DataSource | None":
        """Get the CustomListSource instance for data synchronization.

        Lazily creates a CustomListSource that reads from the file path
        provided during initialization.

        Returns:
            CustomListSource instance or None if file doesn't exist
        """
        if self._data_source is None:
            from ..updater.sources.custom import CustomListSource

            if not self.file_path.exists():
                return None

            self._data_source = CustomListSource(
                self.file_path,
                self.list_type,
                self.source_name,
            )
        return self._data_source
