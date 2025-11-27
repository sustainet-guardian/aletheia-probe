# SPDX-License-Identifier: MIT
"""Kscien publishers data source."""

from ...enums import AssessmentType
from .kscien_generic import KscienGenericSource


class KscienPublishersSource(KscienGenericSource):
    """Data source for Kscien's predatory publishers list.

    Covers 1271 predatory publishers. This enables publisher-level
    journal assessment - any journal from a predatory publisher
    can be flagged as potentially predatory.
    """

    def __init__(self) -> None:
        """Initialize the Kscien publishers data source."""
        super().__init__(
            publication_type="publishers", list_type=AssessmentType.PREDATORY
        )
