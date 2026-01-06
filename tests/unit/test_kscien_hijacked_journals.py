# SPDX-License-Identifier: MIT
"""Unit tests for KscienHijackedJournalsSource."""

from aletheia_probe.enums import AssessmentType
from aletheia_probe.updater.sources.kscien_generic import KscienGenericSource
from aletheia_probe.updater.sources.kscien_helpers import PublicationType
from aletheia_probe.updater.sources.kscien_hijacked_journals import (
    KscienHijackedJournalsSource,
)


def test_initialization():
    """Test that KscienHijackedJournalsSource initializes correctly."""
    source = KscienHijackedJournalsSource()

    assert isinstance(source, KscienGenericSource)
    assert source.publication_type == PublicationType.HIJACKED_JOURNALS
    assert source.list_type == AssessmentType.HIJACKED
