# SPDX-License-Identifier: MIT
"""Unit tests for ROR snapshot backend."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from aletheia_probe.backends.ror_snapshot import RorSnapshotBackend
from aletheia_probe.enums import AssessmentType, EvidenceType
from aletheia_probe.models import BackendStatus, QueryInput, VenueType


def test_ror_snapshot_backend_initialization() -> None:
    """Test backend initialization and metadata."""
    backend = RorSnapshotBackend()
    assert backend.get_name() == "ror_snapshot"
    assert backend.source_name == "ror_snapshot"
    assert backend.list_type == AssessmentType.MIXED
    assert backend.cache_ttl_hours == 24 * 30


def test_ror_snapshot_backend_evidence_type() -> None:
    """Test evidence type classification."""
    backend = RorSnapshotBackend()
    assert backend.get_evidence_type() == EvidenceType.QUALITY_INDICATOR


def test_ror_snapshot_backend_registration() -> None:
    """Test backend factory registration."""
    from aletheia_probe.backends.base import get_backend_registry

    registry = get_backend_registry()
    backend = registry.create_backend("ror_snapshot")
    assert isinstance(backend, RorSnapshotBackend)


def test_ror_snapshot_backend_get_data_source() -> None:
    """Test data source creation and caching."""
    backend = RorSnapshotBackend()

    with patch(
        "aletheia_probe.updater.sources.ror_snapshot.RorSnapshotSource"
    ) as mock_source:
        data_source = backend.get_data_source()
        assert data_source == mock_source.return_value
        mock_source.assert_called_once_with()

        second_source = backend.get_data_source()
        assert second_source == data_source
        mock_source.assert_called_once()


@pytest.mark.asyncio
async def test_ror_snapshot_backend_query_no_authoritative_links() -> None:
    """Return NOT_FOUND when no explicit upstream ROR links are available."""
    backend = RorSnapshotBackend()
    backend._resolve_authoritative_ror_ids = AsyncMock(return_value=[])

    result = await backend.query(
        QueryInput(
            raw_input="Springer Nature",
            normalized_name="springer nature",
            aliases=[],
            identifiers={},
            venue_type=VenueType.JOURNAL,
        )
    )

    assert result.status == BackendStatus.NOT_FOUND
    assert "No authoritative ROR link found" in str(result.data.get("message"))


@pytest.mark.asyncio
async def test_ror_snapshot_backend_query_authoritative_link_match() -> None:
    """Return FOUND quality-indicator evidence from explicit linked ROR IDs."""
    backend = RorSnapshotBackend()
    mock_cache = Mock()
    mock_cache.get_organization_by_ror_id.return_value = {
        "ror_id": "https://ror.org/0117jxy09",
        "display_name": "Springer Nature (Germany)",
        "country_code": "DE",
    }
    backend._ror_cache = mock_cache
    backend._resolve_authoritative_ror_ids = AsyncMock(
        return_value=["https://ror.org/0117jxy09"]
    )

    result = await backend.query(
        QueryInput(
            raw_input="Springer Nature",
            normalized_name="springer nature",
            aliases=[],
            identifiers={"issn": "1234-5678"},
            venue_type=VenueType.JOURNAL,
        )
    )

    assert result.status == BackendStatus.FOUND
    assert result.assessment == AssessmentType.QUALITY_INDICATOR
    assert result.data["match_method"] == "authoritative_link"
    assert result.data["primary_match"]["ror_id"] == "https://ror.org/0117jxy09"


@pytest.mark.asyncio
async def test_ror_snapshot_backend_query_linked_id_not_in_local_snapshot() -> None:
    """Return NOT_FOUND when explicit links exist but snapshot lacks those IDs."""
    backend = RorSnapshotBackend()
    mock_cache = Mock()
    mock_cache.get_organization_by_ror_id.return_value = None
    backend._ror_cache = mock_cache
    backend._resolve_authoritative_ror_ids = AsyncMock(
        return_value=["https://ror.org/0xxxxxxx0"]
    )

    result = await backend.query(
        QueryInput(
            raw_input="Some Journal",
            normalized_name="some journal",
            aliases=[],
            identifiers={"issn": "1234-5678"},
            venue_type=VenueType.JOURNAL,
        )
    )

    assert result.status == BackendStatus.NOT_FOUND
    assert "no local snapshot match" in str(result.data.get("message")).lower()
