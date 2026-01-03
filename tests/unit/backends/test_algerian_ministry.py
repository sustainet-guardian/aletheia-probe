# SPDX-License-Identifier: MIT
"""Tests for Algerian Ministry backend."""

import pytest

from aletheia_probe.backends.algerian_ministry import AlgerianMinistryBackend
from aletheia_probe.enums import EvidenceType


def test_algerian_ministry_evidence_type():
    """Test that Algerian Ministry backend returns correct evidence type."""
    backend = AlgerianMinistryBackend()
    assert backend.get_evidence_type() == EvidenceType.PREDATORY_LIST
