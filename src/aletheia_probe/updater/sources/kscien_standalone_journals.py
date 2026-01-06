# SPDX-License-Identifier: MIT
"""Kscien standalone journals data source."""

from ...enums import AssessmentType
from .kscien_generic import KscienGenericSource
from .kscien_helpers import PublicationType


class KscienStandaloneJournalsSource(KscienGenericSource):
    """Data source for Kscien's standalone predatory journals list.

    Covers individual predatory journals that are not part of
    predatory publishers but are predatory on their own.
    """

    def __init__(self) -> None:
        """Initialize the Kscien standalone journals data source."""
        super().__init__(
            publication_type=PublicationType.STANDALONE_JOURNALS,
            list_type=AssessmentType.PREDATORY,
        )
