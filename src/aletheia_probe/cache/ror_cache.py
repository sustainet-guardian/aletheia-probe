# SPDX-License-Identifier: MIT
"""ROR snapshot and organization identity cache helpers."""

import json
import re
import time
from collections.abc import Iterable
from datetime import date
from typing import Any
from urllib.parse import urlparse

from ..logging_config import get_detail_logger, get_status_logger
from .base import CacheBase


detail_logger = get_detail_logger()
status_logger = get_status_logger()

_WHITESPACE_RE = re.compile(r"\s+")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
DEFAULT_ROR_IMPORT_BATCH_SIZE = 1000


class RorCache(CacheBase):
    """Manages local ROR snapshot data and venue-to-ROR link evidence."""

    def create_snapshot(
        self,
        ror_version: str,
        schema_version: str,
        release_date: date,
        source_url: str,
        record_count: int,
        sha256: str | None = None,
        is_active: bool = True,
    ) -> int:
        """Create a ROR snapshot entry.

        Args:
            ror_version: ROR dataset version label (for example, ``v2.2``).
            schema_version: ROR schema version (for example, ``2.1``).
            release_date: Snapshot release date.
            source_url: Source archive URL.
            record_count: Number of organizations in snapshot.
            sha256: Optional SHA-256 checksum of source archive.
            is_active: Whether this snapshot should be marked as active.

        Returns:
            Newly created snapshot ID.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if is_active:
                cursor.execute("UPDATE ror_snapshots SET is_active = 0")

            cursor.execute(
                """
                INSERT INTO ror_snapshots (
                    ror_version,
                    schema_version,
                    release_date,
                    source_url,
                    sha256,
                    record_count,
                    is_active
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ror_version,
                    schema_version,
                    release_date.isoformat(),
                    source_url,
                    sha256,
                    record_count,
                    int(is_active),
                ),
            )
            snapshot_id = int(cursor.lastrowid)
            conn.commit()
            detail_logger.debug(
                f"Created ROR snapshot {snapshot_id} ({ror_version}, active={is_active})"
            )
            return snapshot_id

    def get_active_snapshot_id(self) -> int | None:
        """Return the active snapshot ID, if any."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT id FROM ror_snapshots WHERE is_active = 1 ORDER BY id DESC LIMIT 1"
            )
            row = cursor.fetchone()
            return int(row[0]) if row else None

    def get_active_snapshot_record_count(self) -> int:
        """Return record count for active snapshot, or 0 if unavailable."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT record_count
                FROM ror_snapshots
                WHERE is_active = 1
                ORDER BY id DESC
                LIMIT 1
                """
            )
            row = cursor.fetchone()
            if row is None:
                return 0
            return int(row[0])

    def clear_all_ror_data(self) -> int:
        """Delete all ROR organization/link table rows before a full re-import.

        Returns:
            Number of deleted organizations.
        """
        with self.get_connection() as conn:
            conn.execute("DELETE FROM journal_ror_links")
            conn.execute("DELETE FROM conference_ror_links")
            conn.execute("DELETE FROM ror_names")
            conn.execute("DELETE FROM ror_domains")
            conn.execute("DELETE FROM ror_links")
            conn.execute("DELETE FROM ror_external_ids")
            conn.execute("DELETE FROM ror_relationships")
            cursor = conn.execute("DELETE FROM ror_organizations")
            deleted_count = int(cursor.rowcount)
            conn.commit()
            detail_logger.debug(
                f"Cleared all ROR data rows before import: {deleted_count} organizations"
            )
            return deleted_count

    def clear_snapshot_data(self, snapshot_id: int) -> int:
        """Backward-compatible alias that now clears all ROR data.

        Returns:
            Number of deleted organizations.
        """
        _ = snapshot_id
        return self.clear_all_ror_data()

    def import_organizations(
        self,
        snapshot_id: int,
        organizations: Iterable[dict[str, Any]],
        status_prefix: str | None = None,
        progress_interval_seconds: float = 5.0,
        batch_size: int = DEFAULT_ROR_IMPORT_BATCH_SIZE,
    ) -> int:
        """Import organizations into local ROR cache for a snapshot.

        Args:
            snapshot_id: Snapshot ID to associate records with.
            organizations: Parsed ROR organization records.
            status_prefix: Optional status prefix for progress messages.
            progress_interval_seconds: Minimum seconds between progress logs.
            batch_size: Number of organization rows to write per DB batch.

        Returns:
            Number of organizations imported.
        """
        imported = 0
        progress_label = status_prefix or "ROR"
        last_progress_log = time.monotonic()
        has_raw_json = self._ror_organizations_has_raw_json_column()

        organization_rows: list[tuple[Any, ...]] = []
        name_rows: list[tuple[Any, ...]] = []
        domain_rows: list[tuple[Any, ...]] = []
        link_rows: list[tuple[Any, ...]] = []
        external_id_rows: list[tuple[Any, ...]] = []
        relationship_rows: list[tuple[Any, ...]] = []

        with self.get_connection() as conn:
            for organization in organizations:
                appended = self._append_organization_rows(
                    snapshot_id=snapshot_id,
                    organization=organization,
                    has_raw_json=has_raw_json,
                    organization_rows=organization_rows,
                    name_rows=name_rows,
                    domain_rows=domain_rows,
                    link_rows=link_rows,
                    external_id_rows=external_id_rows,
                    relationship_rows=relationship_rows,
                )
                if appended:
                    imported += 1

                if len(organization_rows) >= batch_size:
                    self._flush_import_batch(
                        conn=conn,
                        has_raw_json=has_raw_json,
                        organization_rows=organization_rows,
                        name_rows=name_rows,
                        domain_rows=domain_rows,
                        link_rows=link_rows,
                        external_id_rows=external_id_rows,
                        relationship_rows=relationship_rows,
                    )

                now = time.monotonic()
                if now - last_progress_log >= progress_interval_seconds:
                    status_logger.info(
                        f"{progress_label}: Imported {imported:,} organizations..."
                    )
                    last_progress_log = now

            self._flush_import_batch(
                conn=conn,
                has_raw_json=has_raw_json,
                organization_rows=organization_rows,
                name_rows=name_rows,
                domain_rows=domain_rows,
                link_rows=link_rows,
                external_id_rows=external_id_rows,
                relationship_rows=relationship_rows,
            )
            conn.commit()

        detail_logger.info(f"Imported {imported} ROR organizations")
        return imported

    def search_organizations_by_name(
        self, name: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Search active snapshot organizations by normalized name."""
        normalized = self._normalize_text(name)
        like_pattern = f"{normalized}%"

        with self.get_connection_with_row_factory() as conn:
            cursor = conn.execute(
                """
                SELECT
                    ro.ror_id,
                    COALESCE(
                        MAX(CASE WHEN rn.name_types_json LIKE '%ror_display%' THEN rn.value END),
                        MIN(rn.value)
                    ) AS display_name,
                    ro.country_code,
                    ro.org_types_json
                FROM ror_organizations ro
                JOIN ror_snapshots rs ON rs.id = ro.snapshot_id AND rs.is_active = 1
                JOIN ror_names rn ON rn.ror_id = ro.ror_id
                WHERE rn.value_normalized = ? OR rn.value_normalized LIKE ?
                GROUP BY ro.ror_id, ro.country_code, ro.org_types_json
                ORDER BY (rn.value_normalized = ?) DESC, display_name ASC
                LIMIT ?
                """,
                (normalized, like_pattern, normalized, limit),
            )
            rows = cursor.fetchall()

        return [
            {
                "ror_id": row["ror_id"],
                "display_name": row["display_name"],
                "country_code": row["country_code"],
                "org_types": json.loads(row["org_types_json"]),
            }
            for row in rows
        ]

    def search_organizations_by_domain(
        self, domain_or_url: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Search active snapshot organizations by domain."""
        normalized_domain = self._normalize_domain(domain_or_url)
        if not normalized_domain:
            return []

        with self.get_connection_with_row_factory() as conn:
            cursor = conn.execute(
                """
                SELECT
                    ro.ror_id,
                    COALESCE(
                        MAX(CASE WHEN rn.name_types_json LIKE '%ror_display%' THEN rn.value END),
                        MIN(rn.value)
                    ) AS display_name,
                    rd.domain
                FROM ror_domains rd
                JOIN ror_organizations ro ON ro.ror_id = rd.ror_id
                JOIN ror_snapshots rs ON rs.id = ro.snapshot_id AND rs.is_active = 1
                LEFT JOIN ror_names rn ON rn.ror_id = ro.ror_id
                WHERE rd.domain_normalized = ?
                GROUP BY ro.ror_id, rd.domain
                ORDER BY display_name ASC
                LIMIT ?
                """,
                (normalized_domain, limit),
            )
            rows = cursor.fetchall()

        return [
            {
                "ror_id": row["ror_id"],
                "display_name": row["display_name"],
                "domain": row["domain"],
            }
            for row in rows
        ]

    def get_organization_by_ror_id(self, ror_id: str) -> dict[str, Any] | None:
        """Return active-snapshot organization by exact ROR ID."""
        if not isinstance(ror_id, str) or not ror_id.strip():
            return None
        candidate = ror_id.strip()

        with self.get_connection_with_row_factory() as conn:
            cursor = conn.execute(
                """
                SELECT
                    ro.ror_id,
                    COALESCE(
                        MAX(CASE WHEN rn.name_types_json LIKE '%ror_display%' THEN rn.value END),
                        MIN(rn.value)
                    ) AS display_name,
                    ro.country_code
                FROM ror_organizations ro
                JOIN ror_snapshots rs ON rs.id = ro.snapshot_id AND rs.is_active = 1
                LEFT JOIN ror_names rn ON rn.ror_id = ro.ror_id
                WHERE ro.ror_id = ?
                GROUP BY ro.ror_id, ro.country_code
                LIMIT 1
                """,
                (candidate,),
            )
            row = cursor.fetchone()

        if row is None:
            return None
        return {
            "ror_id": row["ror_id"],
            "display_name": row["display_name"],
            "country_code": row["country_code"],
        }

    def upsert_journal_link(
        self,
        journal_id: int,
        ror_id: str,
        match_status: str,
        confidence: float,
        matching_method: str,
        evidence: dict[str, Any],
        snapshot_id: int | None = None,
    ) -> None:
        """Upsert journal-to-ROR evidence link."""
        resolved_snapshot_id = snapshot_id or self.get_active_snapshot_id()
        if resolved_snapshot_id is None:
            raise ValueError(
                "No active ROR snapshot available; pass snapshot_id explicitly"
            )

        self._upsert_venue_link(
            table_name="journal_ror_links",
            venue_id_column="journal_id",
            venue_id=journal_id,
            ror_id=ror_id,
            match_status=match_status,
            confidence=confidence,
            matching_method=matching_method,
            evidence=evidence,
            snapshot_id=resolved_snapshot_id,
        )

    def upsert_conference_link(
        self,
        conference_id: int,
        ror_id: str,
        match_status: str,
        confidence: float,
        matching_method: str,
        evidence: dict[str, Any],
        snapshot_id: int | None = None,
    ) -> None:
        """Upsert conference-to-ROR evidence link."""
        resolved_snapshot_id = snapshot_id or self.get_active_snapshot_id()
        if resolved_snapshot_id is None:
            raise ValueError(
                "No active ROR snapshot available; pass snapshot_id explicitly"
            )

        self._upsert_venue_link(
            table_name="conference_ror_links",
            venue_id_column="conference_id",
            venue_id=conference_id,
            ror_id=ror_id,
            match_status=match_status,
            confidence=confidence,
            matching_method=matching_method,
            evidence=evidence,
            snapshot_id=resolved_snapshot_id,
        )

    def _upsert_venue_link(
        self,
        table_name: str,
        venue_id_column: str,
        venue_id: int,
        ror_id: str,
        match_status: str,
        confidence: float,
        matching_method: str,
        evidence: dict[str, Any],
        snapshot_id: int,
    ) -> None:
        """Insert or update one venue-to-ROR evidence row."""
        evidence_json = json.dumps(evidence, sort_keys=True)
        with self.get_connection() as conn:
            conn.execute(
                f"""
                INSERT INTO {table_name} (
                    {venue_id_column},
                    ror_id,
                    match_status,
                    confidence,
                    matching_method,
                    evidence_json,
                    snapshot_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT({venue_id_column}, ror_id, snapshot_id)
                DO UPDATE SET
                    match_status = excluded.match_status,
                    confidence = excluded.confidence,
                    matching_method = excluded.matching_method,
                    evidence_json = excluded.evidence_json,
                    created_at = CURRENT_TIMESTAMP
                """,
                (
                    venue_id,
                    ror_id,
                    match_status,
                    confidence,
                    matching_method,
                    evidence_json,
                    snapshot_id,
                ),
            )
            conn.commit()

    def _append_organization_rows(
        self,
        snapshot_id: int,
        organization: dict[str, Any],
        has_raw_json: bool,
        organization_rows: list[tuple[Any, ...]],
        name_rows: list[tuple[Any, ...]],
        domain_rows: list[tuple[Any, ...]],
        link_rows: list[tuple[Any, ...]],
        external_id_rows: list[tuple[Any, ...]],
        relationship_rows: list[tuple[Any, ...]],
    ) -> bool:
        """Extract one organization into append-only row buffers."""
        ror_id = organization.get("id")
        if not isinstance(ror_id, str) or not ror_id:
            return False

        country_code, city, lat, lng = self._extract_location_fields(organization)
        org_types = organization.get("types") or []
        status = str(organization.get("status") or "active")
        established = organization.get("established")
        if not isinstance(established, int):
            established = None

        if has_raw_json:
            organization_rows.append(
                (
                    ror_id,
                    snapshot_id,
                    status,
                    established,
                    country_code,
                    city,
                    lat,
                    lng,
                    json.dumps(org_types, sort_keys=True),
                    "",
                )
            )
        else:
            organization_rows.append(
                (
                    ror_id,
                    snapshot_id,
                    status,
                    established,
                    country_code,
                    city,
                    lat,
                    lng,
                    json.dumps(org_types, sort_keys=True),
                )
            )

        for name_entry in organization.get("names") or []:
            value = name_entry.get("value")
            if not isinstance(value, str) or not value.strip():
                continue
            normalized_value = self._normalize_text(value)
            if not normalized_value:
                continue
            name_rows.append(
                (
                    ror_id,
                    value.strip(),
                    normalized_value,
                    name_entry.get("lang"),
                    json.dumps(name_entry.get("types") or [], sort_keys=True),
                )
            )

        for domain in organization.get("domains") or []:
            if not isinstance(domain, str) or not domain.strip():
                continue
            normalized = self._normalize_domain(domain)
            if not normalized:
                continue
            domain_rows.append((ror_id, domain.strip(), normalized))

        for link_entry in organization.get("links") or []:
            url = link_entry.get("value")
            if not isinstance(url, str) or not url.strip():
                continue
            host_normalized = self._normalize_domain(url)
            link_rows.append(
                (
                    ror_id,
                    str(link_entry.get("type") or "website"),
                    url.strip(),
                    host_normalized,
                )
            )

        for external_id in organization.get("external_ids") or []:
            id_type = external_id.get("type")
            if not isinstance(id_type, str) or not id_type:
                continue
            external_id_rows.append(
                (
                    ror_id,
                    id_type,
                    external_id.get("preferred"),
                    json.dumps(external_id.get("all") or [], sort_keys=True),
                )
            )

        for relationship in organization.get("relationships") or []:
            related_ror_id = relationship.get("id")
            relation_type = relationship.get("type")
            if not isinstance(related_ror_id, str) or not isinstance(
                relation_type, str
            ):
                continue
            relationship_rows.append(
                (
                    ror_id,
                    related_ror_id,
                    relation_type,
                    relationship.get("label"),
                )
            )
        return True

    def _flush_import_batch(
        self,
        conn: Any,
        has_raw_json: bool,
        organization_rows: list[tuple[Any, ...]],
        name_rows: list[tuple[Any, ...]],
        domain_rows: list[tuple[Any, ...]],
        link_rows: list[tuple[Any, ...]],
        external_id_rows: list[tuple[Any, ...]],
        relationship_rows: list[tuple[Any, ...]],
    ) -> None:
        """Write buffered rows using bulk ``executemany`` operations."""
        if not organization_rows:
            return

        if has_raw_json:
            conn.executemany(
                """
                INSERT OR REPLACE INTO ror_organizations (
                    ror_id,
                    snapshot_id,
                    status,
                    established,
                    country_code,
                    city,
                    lat,
                    lng,
                    org_types_json,
                    raw_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                organization_rows,
            )
        else:
            conn.executemany(
                """
                INSERT OR REPLACE INTO ror_organizations (
                    ror_id,
                    snapshot_id,
                    status,
                    established,
                    country_code,
                    city,
                    lat,
                    lng,
                    org_types_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                organization_rows,
            )

        if name_rows:
            conn.executemany(
                """
                INSERT INTO ror_names (
                    ror_id,
                    value,
                    value_normalized,
                    lang,
                    name_types_json
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                name_rows,
            )
        if domain_rows:
            conn.executemany(
                """
                INSERT OR IGNORE INTO ror_domains (ror_id, domain, domain_normalized)
                VALUES (?, ?, ?)
                """,
                domain_rows,
            )
        if link_rows:
            conn.executemany(
                """
                INSERT INTO ror_links (ror_id, link_type, url, host_normalized)
                VALUES (?, ?, ?, ?)
                """,
                link_rows,
            )
        if external_id_rows:
            conn.executemany(
                """
                INSERT INTO ror_external_ids (
                    ror_id,
                    id_type,
                    preferred_value,
                    all_values_json
                )
                VALUES (?, ?, ?, ?)
                """,
                external_id_rows,
            )
        if relationship_rows:
            conn.executemany(
                """
                INSERT INTO ror_relationships (
                    ror_id,
                    related_ror_id,
                    relation_type,
                    related_label
                )
                VALUES (?, ?, ?, ?)
                """,
                relationship_rows,
            )

        organization_rows.clear()
        name_rows.clear()
        domain_rows.clear()
        link_rows.clear()
        external_id_rows.clear()
        relationship_rows.clear()

    def _ror_organizations_has_raw_json_column(self) -> bool:
        """Return whether the local ``ror_organizations`` table still has ``raw_json``."""
        with self.get_connection() as conn:
            cursor = conn.execute("PRAGMA table_info(ror_organizations)")
            columns = {str(row[1]) for row in cursor.fetchall()}
        return "raw_json" in columns

    @staticmethod
    def _extract_location_fields(
        organization: dict[str, Any],
    ) -> tuple[str | None, str | None, float | None, float | None]:
        """Extract best-effort location fields from the first location entry."""
        locations = organization.get("locations") or []
        if not isinstance(locations, list) or not locations:
            return None, None, None, None

        first_location = locations[0]
        geonames_details = first_location.get("geonames_details") or {}
        country_code = geonames_details.get("country_code")
        city = geonames_details.get("name")
        lat = geonames_details.get("lat")
        lng = geonames_details.get("lng")

        return (
            country_code if isinstance(country_code, str) else None,
            city if isinstance(city, str) else None,
            float(lat) if isinstance(lat, (int, float)) else None,
            float(lng) if isinstance(lng, (int, float)) else None,
        )

    @staticmethod
    def _normalize_text(value: str) -> str:
        """Normalize text for deterministic case-insensitive matching."""
        normalized = _NON_ALNUM_RE.sub(" ", value.lower())
        return _WHITESPACE_RE.sub(" ", normalized).strip()

    @staticmethod
    def _normalize_domain(domain_or_url: str) -> str | None:
        """Normalize domain string or URL host."""
        candidate = domain_or_url.strip().lower()
        if not candidate:
            return None

        parsed = urlparse(candidate if "://" in candidate else f"https://{candidate}")
        host = parsed.netloc or parsed.path
        host = host.split("/")[0]
        host = host.strip(".")
        if not host:
            return None
        if host.startswith("www."):
            host = host[4:]
        return host or None
