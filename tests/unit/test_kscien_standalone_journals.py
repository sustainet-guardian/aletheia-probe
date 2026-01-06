# SPDX-License-Identifier: MIT
"""Unit tests for KscienStandaloneJournalsSource."""

from aletheia_probe.enums import AssessmentType
from aletheia_probe.updater.sources.kscien_generic import KscienGenericSource
from aletheia_probe.updater.sources.kscien_helpers import PublicationType
from aletheia_probe.updater.sources.kscien_standalone_journals import (
    KscienStandaloneJournalsSource,
)


def test_initialization():
    """Test that KscienStandaloneJournalsSource initializes correctly."""
    source = KscienStandaloneJournalsSource()

    assert isinstance(source, KscienGenericSource)
    assert source.publication_type == PublicationType.STANDALONE_JOURNALS
    assert source.list_type == AssessmentType.PREDATORY
