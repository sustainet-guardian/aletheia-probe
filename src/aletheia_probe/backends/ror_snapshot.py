# SPDX-License-Identifier: MIT
"""ROR snapshot backend for synchronization and identity-link evidence."""

import time
from collections.abc import Iterable
from typing import TYPE_CHECKING

from ..cache import RorCache
from ..config import get_config_manager
from ..enums import AssessmentType, EvidenceType
from ..fallback_chain import QueryFallbackChain
from ..models import BackendResult, BackendStatus, QueryInput
from ..openalex import OpenAlexClient
from .base import CachedBackend, get_backend_registry


if TYPE_CHECKING:
    from ..updater.core import DataSource
    from ..updater.sources.ror_snapshot import RorSnapshotSource


class RorSnapshotBackend(CachedBackend):
    """Backend wrapper for syncing local ROR snapshots.

    Runtime query behavior intentionally uses authoritative links only
    (for now: OpenAlex source -> host institution -> institution.ids.ror).
    """

    def __init__(self) -> None:
        super().__init__(
            source_name="ror_snapshot",
            list_type=AssessmentType.MIXED,
            cache_ttl_hours=24 * 30,
        )
        self._data_source: RorSnapshotSource | None = None
        self._ror_cache: RorCache | None = None

    def get_name(self) -> str:
        """Return backend name."""
        return "ror_snapshot"

    def get_evidence_type(self) -> EvidenceType:
        """Return evidence type for identity enrichment backend."""
        return EvidenceType.QUALITY_INDICATOR

    async def query(self, query_input: QueryInput) -> BackendResult:
        """Resolve authoritative ROR links (no heuristic name/domain matching)."""
        start_time = time.time()
        chain = QueryFallbackChain([])
        ror_cache = self._get_ror_cache()

        linked_ror_ids = await self._resolve_authoritative_ror_ids(query_input)
        if not linked_ror_ids:
            return BackendResult(
                backend_name=self.get_name(),
                status=BackendStatus.NOT_FOUND,
                confidence=0.0,
                assessment=None,
                data={
                    "searched_in": self.source_name,
                    "message": (
                        "No authoritative ROR link found in upstream metadata "
                        "(OpenAlex/Crossref)"
                    ),
                },
                sources=[self.source_name],
                error_message=None,
                response_time=time.time() - start_time,
                cached=True,
                fallback_chain=chain,
            )

        linked_matches: list[dict[str, str]] = []
        for ror_id in linked_ror_ids:
            organization = ror_cache.get_organization_by_ror_id(ror_id)
            if organization is None:
                continue
            linked_matches.append(
                {
                    "ror_id": str(organization["ror_id"]),
                    "display_name": str(organization.get("display_name") or ""),
                    "country_code": str(organization.get("country_code") or ""),
                }
            )

        if not linked_matches:
            return BackendResult(
                backend_name=self.get_name(),
                status=BackendStatus.NOT_FOUND,
                confidence=0.0,
                assessment=None,
                data={
                    "searched_in": self.source_name,
                    "message": "Authoritative ROR links found, but no local snapshot match",
                    "linked_ror_ids": linked_ror_ids,
                },
                sources=[self.source_name],
                error_message=None,
                response_time=time.time() - start_time,
                cached=True,
                fallback_chain=chain,
            )

        return BackendResult(
            backend_name=self.get_name(),
            status=BackendStatus.FOUND,
            confidence=0.98,
            assessment=AssessmentType.QUALITY_INDICATOR,
            data={
                "match_method": "authoritative_link",
                "primary_match": linked_matches[0],
                "linked_matches": linked_matches,
                "linked_ror_ids": linked_ror_ids,
                "source": "Research Organization Registry (ROR) snapshot",
            },
            sources=[self.source_name],
            error_message=None,
            response_time=time.time() - start_time,
            cached=True,
            fallback_chain=chain,
        )

    def get_data_source(self) -> "DataSource | None":
        """Return ROR snapshot data source instance."""
        if self._data_source is None:
            from ..updater.sources.ror_snapshot import RorSnapshotSource

            self._data_source = RorSnapshotSource()
        return self._data_source

    def _get_ror_cache(self) -> RorCache:
        """Lazily initialize the ROR cache."""
        if self._ror_cache is None:
            self._ror_cache = RorCache()
        return self._ror_cache

    async def _resolve_authoritative_ror_ids(
        self, query_input: QueryInput
    ) -> list[str]:
        """Resolve ROR IDs from authoritative upstream links only."""
        identifiers = query_input.identifiers or {}
        issn_candidates = self._unique_non_empty(
            [identifiers.get("issn"), identifiers.get("eissn")]
        )
        if not issn_candidates:
            return []

        email = self._get_openalex_email()
        resolved_ids: list[str] = []
        async with OpenAlexClient(email=email) as client:
            for issn in issn_candidates:
                source = await client.get_source_by_issn(issn)
                if not isinstance(source, dict):
                    continue
                host_organization = source.get("host_organization")
                if not isinstance(host_organization, str) or not host_organization:
                    continue
                institution = await client.get_institution_by_id(host_organization)
                if not isinstance(institution, dict):
                    continue
                ids_payload = institution.get("ids", {})
                ror_id = (
                    ids_payload.get("ror") if isinstance(ids_payload, dict) else None
                )
                if isinstance(ror_id, str) and ror_id.strip():
                    resolved_ids.append(ror_id.strip())
        return self._unique_non_empty(resolved_ids)

    def _get_openalex_email(self) -> str:
        """Return configured OpenAlex email or safe default."""
        backend_config = get_config_manager().get_backend_config("openalex_analyzer")
        if backend_config and backend_config.email:
            return backend_config.email
        return "noreply@aletheia-probe.org"

    @staticmethod
    def _unique_non_empty(values: Iterable[str | None]) -> list[str]:
        """Return de-duplicated non-empty strings preserving order."""
        deduped: list[str] = []
        seen: set[str] = set()
        for value in values:
            if not isinstance(value, str):
                continue
            candidate = value.strip()
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            deduped.append(candidate)
        return deduped


get_backend_registry().register_factory(
    "ror_snapshot",
    lambda: RorSnapshotBackend(),
    default_config={},
)
