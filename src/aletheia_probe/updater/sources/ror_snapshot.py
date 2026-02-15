# SPDX-License-Identifier: MIT
"""ROR snapshot data source for local organization registry imports."""

import asyncio
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

import aiohttp

from ...cache import DataSourceManager
from ...config import get_config_manager
from ...enums import AssessmentType
from ...logging_config import get_detail_logger, get_status_logger
from ...ror_snapshot_importer import RorSnapshotImporter
from ..core import DataSource


detail_logger = get_detail_logger()
status_logger = get_status_logger()

DEFAULT_UPDATE_INTERVAL_DAYS = 30
_ROR_ARCHIVE_VERSION_PATTERN = re.compile(
    r"v(?P<version>\d+\.\d+).*(?P<date>\d{4}-\d{2}-\d{2})"
)
_DOI_PATTERN = re.compile(r"(10\.\d{4,9}/zenodo\.\d+)")


class RorSnapshotSource(DataSource):
    """Data source that imports full ROR snapshots into local cache tables."""

    def __init__(
        self,
        data_dir: Path | None = None,
        update_interval_days: int = DEFAULT_UPDATE_INTERVAL_DAYS,
    ) -> None:
        config = get_config_manager().load_config()
        self.archive_url = config.data_source_urls.ror_snapshot_archive_url
        self.source_url = config.data_source_urls.ror_snapshot_concept_doi_url
        self.update_interval_days = update_interval_days
        self.allow_empty_data_success = True
        self._request_timeout = aiohttp.ClientTimeout(total=30)

        if data_dir is None:
            data_dir = Path.cwd() / ".aletheia-probe" / "ror"
        self.data_dir = data_dir

    def get_name(self) -> str:
        """Return source name."""
        return "ror_snapshot"

    def get_list_type(self) -> AssessmentType:
        """Return source type.

        ROR is an identity enrichment source and does not directly classify venues.
        """
        return AssessmentType.MIXED

    def should_update(self) -> bool:
        """Check if source should be refreshed."""
        data_source_manager = DataSourceManager()
        last_update = data_source_manager.get_source_last_updated(self.get_name())
        if last_update is None:
            return True

        if (datetime.now() - last_update).days < self.update_interval_days:
            self.skip_reason = "already_up_to_date"
            return False

        return True

    async def fetch_data(self) -> list[dict[str, Any]]:
        """Download and import the latest configured ROR snapshot.

        Returns:
            Empty list by design. Import side-effects write into ROR tables directly.
        """
        status_logger.info(f"    {self.get_name()}: Downloading ROR snapshot")
        (
            archive_url,
            ror_version,
            release_date_value,
        ) = await self._resolve_latest_archive_details()
        status_logger.info(f"    {self.get_name()}: Downloading archive {archive_url}")
        importer = RorSnapshotImporter()
        archive_path = await importer.download_archive(archive_url, self.data_dir)

        snapshot_id = importer.import_archive(
            archive_path=archive_path,
            source_url=self.source_url,
            release_date=release_date_value,
            ror_version=ror_version,
            schema_version=None,
            set_active=True,
        )

        status_logger.info(
            f"    {self.get_name()}: Imported snapshot {ror_version} (id={snapshot_id})"
        )
        detail_logger.info(
            f"{self.get_name()}: Imported ROR archive {archive_path.name} into snapshot {snapshot_id}"
        )

        return []

    async def _resolve_latest_archive_details(self) -> tuple[str, str, date]:
        """Resolve latest archive URL, version, and release date from Zenodo API.

        Falls back to configured archive URL when API resolution fails.
        """
        concept_doi = self._extract_doi(self.source_url)
        if not concept_doi:
            detail_logger.warning(
                f"{self.get_name()}: Could not extract concept DOI from {self.source_url}, using fallback archive URL"
            )
            fallback_ror_version, fallback_release_date = (
                self._extract_metadata_from_archive_name(
                    self.archive_url.split("/")[-1]
                )
            )
            return (
                self.archive_url,
                fallback_ror_version,
                fallback_release_date,
            )

        query_url = (
            "https://zenodo.org/api/records/"
            f"?q=conceptdoi:%22{concept_doi}%22&sort=mostrecent&size=1"
        )

        try:
            async with aiohttp.ClientSession(timeout=self._request_timeout) as session:
                async with session.get(query_url) as response:
                    response.raise_for_status()
                    payload = await response.json()

            latest_record = (
                payload.get("hits", {}).get("hits", [None])[0]
                if isinstance(payload, dict)
                else None
            )
            if not isinstance(latest_record, dict):
                raise ValueError("Zenodo response does not contain records")

            files = latest_record.get("files", [])
            if not isinstance(files, list) or not files:
                raise ValueError("Zenodo record has no downloadable files")

            archive_file = next(
                (
                    file_item
                    for file_item in files
                    if isinstance(file_item, dict)
                    and str(file_item.get("key", "")).lower().endswith(".zip")
                ),
                None,
            )
            if archive_file is None:
                raise ValueError("Zenodo record has no zip file")

            archive_url = archive_file.get("links", {}).get("self")
            if not isinstance(archive_url, str) or not archive_url:
                raise ValueError("Zip file does not provide a download URL")

            metadata = latest_record.get("metadata", {})
            publication_date = (
                metadata.get("publication_date") if isinstance(metadata, dict) else None
            )
            release_date_value = (
                date.fromisoformat(publication_date)
                if isinstance(publication_date, str)
                else date.today()
            )
            ror_version_from_metadata: str | None = None
            if isinstance(metadata, dict):
                raw_version = metadata.get("version")
                if isinstance(raw_version, str):
                    ror_version_from_metadata = raw_version

            if ror_version_from_metadata is None:
                fallback_ror_version, _ = self._extract_metadata_from_archive_name(
                    str(archive_file.get("key", ""))
                )
                ror_version = fallback_ror_version
            else:
                ror_version = ror_version_from_metadata

            detail_logger.info(
                f"{self.get_name()}: Resolved latest ROR archive URL from Zenodo API ({ror_version})"
            )
            return archive_url, ror_version, release_date_value

        except (
            aiohttp.ClientError,
            asyncio.TimeoutError,
            ValueError,
            KeyError,
        ) as error:
            detail_logger.warning(
                f"{self.get_name()}: Failed to resolve latest archive via Zenodo API ({error}); using fallback archive URL"
            )
            fallback_ror_version, fallback_release_date = (
                self._extract_metadata_from_archive_name(
                    self.archive_url.split("/")[-1]
                )
            )
            return (
                self.archive_url,
                fallback_ror_version,
                fallback_release_date,
            )

    @staticmethod
    def _extract_metadata_from_archive_name(filename: str) -> tuple[str, date]:
        """Extract ROR version and release date from archive filename."""
        match = _ROR_ARCHIVE_VERSION_PATTERN.search(filename)
        if not match:
            return "unknown", date.today()

        release_date_value = date.today()
        release_date_raw = match.group("date")
        try:
            release_date_value = date.fromisoformat(release_date_raw)
        except ValueError:
            release_date_value = date.today()

        return f"v{match.group('version')}", release_date_value

    @staticmethod
    def _extract_doi(value: str) -> str | None:
        """Extract DOI from a URL-like or DOI-like string."""
        match = _DOI_PATTERN.search(value)
        if not match:
            return None
        return match.group(1)
