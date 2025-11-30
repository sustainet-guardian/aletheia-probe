# SPDX-License-Identifier: MIT
"""Kscien standalone journals data source."""

from ...enums import AssessmentType
from ..core import get_update_source_registry
from .kscien_generic import KscienGenericSource


class KscienStandaloneJournalsSource(KscienGenericSource):
    """Data source for Kscien's standalone predatory journals list.

    Covers 1476 individual predatory journals that are not part of
    predatory publishers but are predatory on their own.
    """

    def __init__(self) -> None:
        """Initialize the Kscien standalone journals data source."""
        super().__init__(
            publication_type="standalone-journals", list_type=AssessmentType.PREDATORY
        )


# Register the update source factory
get_update_source_registry().register_factory(
    "kscien_standalone_journals",
    lambda: KscienStandaloneJournalsSource(),
    default_config={},
)
