# SPDX-License-Identifier: MIT
"""Kscien hijacked journals data source."""

from .kscien_generic import KscienGenericSource


class KscienHijackedJournalsSource(KscienGenericSource):
    """Data source for Kscien's hijacked journals list.

    Covers 234 legitimate journals that have been hijacked by
    predatory actors. These journals were originally legitimate
    but have been compromised.
    """

    def __init__(self) -> None:
        """Initialize the Kscien hijacked journals data source."""
        super().__init__(
            publication_type="hijacked-journals",
            list_type="hijacked",  # Different assessment type
        )

    def get_name(self) -> str:
        """Return the data source identifier."""
        return "kscien_hijacked_journals"
