# SPDX-License-Identifier: MIT
"""Tests for UGC-CARE backends."""

from aletheia_probe.backends.ugc_care_cloned import UgcCareClonedBackend
from aletheia_probe.backends.ugc_care_cloned_group2 import UgcCareClonedGroup2Backend
from aletheia_probe.backends.ugc_care_delisted_group2 import (
    UgcCareDelistedGroup2Backend,
)
from aletheia_probe.backends.ugc_care_included_from_clone_group1 import (
    UgcCareIncludedFromCloneGroup1Backend,
)
from aletheia_probe.backends.ugc_care_included_from_clone_group2 import (
    UgcCareIncludedFromCloneGroup2Backend,
)
from aletheia_probe.enums import AssessmentType, EvidenceType


def test_ugc_care_cloned_backend_configuration():
    """Test UGC cloned backend configuration and metadata."""
    backend = UgcCareClonedBackend()
    assert backend.get_name() == "ugc_care_cloned"
    assert backend.source_name == "ugc_care_cloned"
    assert backend.list_type == AssessmentType.PREDATORY
    assert backend.get_evidence_type() == EvidenceType.PREDATORY_LIST
    assert backend.cache_ttl_hours == 24 * 30


def test_ugc_care_delisted_group2_backend_configuration():
    """Test UGC delisted backend configuration and metadata."""
    backend = UgcCareDelistedGroup2Backend()
    assert backend.get_name() == "ugc_care_delisted_group2"
    assert backend.source_name == "ugc_care_delisted_group2"
    assert backend.list_type == AssessmentType.PREDATORY
    assert backend.get_evidence_type() == EvidenceType.PREDATORY_LIST
    assert backend.cache_ttl_hours == 24 * 30


def test_ugc_care_cloned_group2_backend_configuration():
    """Test UGC cloned Group II backend configuration and metadata."""
    backend = UgcCareClonedGroup2Backend()
    assert backend.get_name() == "ugc_care_cloned_group2"
    assert backend.source_name == "ugc_care_cloned_group2"
    assert backend.list_type == AssessmentType.PREDATORY
    assert backend.get_evidence_type() == EvidenceType.PREDATORY_LIST
    assert backend.cache_ttl_hours == 24 * 30


def test_ugc_care_included_group1_backend_configuration():
    """Test included Group I backend configuration and metadata."""
    backend = UgcCareIncludedFromCloneGroup1Backend()
    assert backend.get_name() == "ugc_care_included_from_clone_group1"
    assert backend.source_name == "ugc_care_included_from_clone_group1"
    assert backend.list_type == AssessmentType.LEGITIMATE
    assert backend.get_evidence_type() == EvidenceType.LEGITIMATE_LIST
    assert backend.cache_ttl_hours == 24 * 30


def test_ugc_care_included_group2_backend_configuration():
    """Test included Group II backend configuration and metadata."""
    backend = UgcCareIncludedFromCloneGroup2Backend()
    assert backend.get_name() == "ugc_care_included_from_clone_group2"
    assert backend.source_name == "ugc_care_included_from_clone_group2"
    assert backend.list_type == AssessmentType.LEGITIMATE
    assert backend.get_evidence_type() == EvidenceType.LEGITIMATE_LIST
    assert backend.cache_ttl_hours == 24 * 30


def test_ugc_care_backends_registered():
    """Test both UGC-CARE backends are available in backend registry."""
    from aletheia_probe.backends.base import get_backend_registry

    registry = get_backend_registry()
    cloned_backend = registry.create_backend("ugc_care_cloned")
    cloned_group2_backend = registry.create_backend("ugc_care_cloned_group2")
    delisted_backend = registry.create_backend("ugc_care_delisted_group2")
    included_group1_backend = registry.create_backend(
        "ugc_care_included_from_clone_group1"
    )
    included_group2_backend = registry.create_backend(
        "ugc_care_included_from_clone_group2"
    )

    assert isinstance(cloned_backend, UgcCareClonedBackend)
    assert isinstance(cloned_group2_backend, UgcCareClonedGroup2Backend)
    assert isinstance(delisted_backend, UgcCareDelistedGroup2Backend)
    assert isinstance(included_group1_backend, UgcCareIncludedFromCloneGroup1Backend)
    assert isinstance(included_group2_backend, UgcCareIncludedFromCloneGroup2Backend)
