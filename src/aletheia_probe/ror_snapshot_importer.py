# SPDX-License-Identifier: MIT
"""Utilities for downloading and importing local ROR snapshots."""

import asyncio
import hashlib
import json
import tempfile
import zipfile
from datetime import date
from pathlib import Path
from typing import Any

import aiohttp

from .cache import RorCache
from .logging_config import get_detail_logger, get_status_logger


detail_logger = get_detail_logger()
status_logger = get_status_logger()

DEFAULT_DOWNLOAD_CHUNK_SIZE = 1024 * 1024  # 1 MiB
DEFAULT_CONNECT_TIMEOUT_SECONDS = 30
DEFAULT_SOCKET_READ_TIMEOUT_SECONDS = 900


class RorSnapshotImporter:
    """Imports a full ROR snapshot archive into local cache tables."""

    def __init__(self, cache: RorCache | None = None) -> None:
        self.cache = cache or RorCache()
        self.timeout = aiohttp.ClientTimeout(
            total=None,
            connect=DEFAULT_CONNECT_TIMEOUT_SECONDS,
            sock_read=DEFAULT_SOCKET_READ_TIMEOUT_SECONDS,
        )

    async def download_archive(self, archive_url: str, destination_dir: Path) -> Path:
        """Download a ROR archive file to ``destination_dir``.

        Args:
            archive_url: HTTPS URL for a ROR release archive.
            destination_dir: Directory where the archive will be stored.

        Returns:
            Downloaded archive path.
        """
        destination_dir.mkdir(parents=True, exist_ok=True)
        filename = archive_url.rstrip("/").split("/")[-1] or "ror_snapshot.zip"
        archive_path = destination_dir / filename

        detail_logger.info(f"Downloading ROR snapshot archive: {archive_url}")

        with tempfile.NamedTemporaryFile(
            mode="wb",
            delete=False,
            dir=str(destination_dir),
            prefix="ror-",
            suffix=".part",
        ) as temp_file:
            temp_path = Path(temp_file.name)

        total_bytes = 0
        progress_threshold = 5 * 1024 * 1024
        next_progress_log = progress_threshold
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(archive_url) as response:
                    response.raise_for_status()
                    with open(temp_path, "wb") as output_file:
                        async for chunk in response.content.iter_chunked(
                            DEFAULT_DOWNLOAD_CHUNK_SIZE
                        ):
                            if not chunk:
                                continue
                            output_file.write(chunk)
                            total_bytes += len(chunk)
                            if total_bytes >= next_progress_log:
                                status_logger.info(
                                    f"    ror_snapshot: Downloaded {total_bytes / (1024 * 1024):,.0f} MiB..."
                                )
                                next_progress_log += progress_threshold

            temp_path.replace(archive_path)
            status_logger.info(
                f"    ror_snapshot: Downloaded archive ({total_bytes / (1024 * 1024):,.1f} MiB)"
            )
            return archive_path
        finally:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)

    def load_organizations_from_archive(
        self, archive_path: Path
    ) -> list[dict[str, Any]]:
        """Load ROR organizations from a zip archive.

        Args:
            archive_path: Path to a zip archive containing a JSON organization dump.

        Returns:
            Parsed list of organization records.

        Raises:
            ValueError: If no JSON organization payload is found.
        """
        with zipfile.ZipFile(archive_path) as archive:
            json_member = self._find_json_member(archive)
            if json_member is None:
                raise ValueError(
                    f"No JSON organization payload found in archive: {archive_path}"
                )

            with archive.open(json_member) as member:
                payload = json.load(member)

        if isinstance(payload, list):
            organizations = payload
        elif isinstance(payload, dict) and isinstance(payload.get("items"), list):
            organizations = payload["items"]
        else:
            raise ValueError("Unsupported ROR archive JSON structure")

        detail_logger.info(
            f"Loaded {len(organizations)} organizations from {archive_path.name}"
        )
        return organizations

    def import_archive(
        self,
        archive_path: Path,
        source_url: str,
        release_date: date,
        ror_version: str,
        schema_version: str | None = None,
        set_active: bool = True,
    ) -> int:
        """Import a ROR archive into cache tables and create a snapshot entry.

        Args:
            archive_path: Local archive path.
            source_url: Original download URL.
            release_date: ROR release date.
            ror_version: ROR release version string.
            schema_version: Optional schema version (auto-detected if missing).
            set_active: Whether imported snapshot should become active.

        Returns:
            Snapshot ID.
        """
        organizations = self.load_organizations_from_archive(archive_path)
        if not organizations:
            raise ValueError("Archive does not contain any organizations")

        resolved_schema_version = schema_version or self._detect_schema_version(
            organizations
        )
        checksum = self._compute_sha256(archive_path)

        snapshot_id = self.cache.create_snapshot(
            ror_version=ror_version,
            schema_version=resolved_schema_version,
            release_date=release_date,
            source_url=source_url,
            record_count=len(organizations),
            sha256=checksum,
            is_active=set_active,
        )
        self.cache.clear_all_ror_data()
        imported = self.cache.import_organizations(
            snapshot_id,
            organizations,
            status_prefix="    ror_snapshot",
        )

        status_logger.info(
            f"    ror_snapshot: Imported ROR snapshot {ror_version}: "
            f"{imported} organizations (snapshot_id={snapshot_id})"
        )
        return snapshot_id

    @staticmethod
    def _find_json_member(archive: zipfile.ZipFile) -> str | None:
        json_candidates = [
            member_name
            for member_name in archive.namelist()
            if member_name.lower().endswith(".json")
        ]
        if not json_candidates:
            return None
        json_candidates.sort()
        return json_candidates[0]

    @staticmethod
    def _detect_schema_version(organizations: list[dict[str, Any]]) -> str:
        if not organizations:
            return "unknown"
        admin = organizations[0].get("admin") or {}
        created = admin.get("created") or {}
        last_modified = admin.get("last_modified") or {}
        created_schema = created.get("schema_version")
        modified_schema = last_modified.get("schema_version")
        if isinstance(modified_schema, str) and modified_schema:
            return modified_schema
        if isinstance(created_schema, str) and created_schema:
            return created_schema
        return "unknown"

    @staticmethod
    def _compute_sha256(path: Path) -> str:
        hasher = hashlib.sha256()
        with open(path, "rb") as file_obj:
            for block in iter(lambda: file_obj.read(1024 * 1024), b""):
                hasher.update(block)
        return hasher.hexdigest()


async def download_and_import_ror_snapshot(
    archive_url: str,
    destination_dir: Path,
    source_url: str,
    release_date: date,
    ror_version: str,
    schema_version: str | None = None,
    set_active: bool = True,
    cache: RorCache | None = None,
) -> int:
    """Convenience helper to download and import a ROR snapshot archive."""
    importer = RorSnapshotImporter(cache=cache)
    archive_path = await importer.download_archive(archive_url, destination_dir)
    return importer.import_archive(
        archive_path=archive_path,
        source_url=source_url,
        release_date=release_date,
        ror_version=ror_version,
        schema_version=schema_version,
        set_active=set_active,
    )


def run_download_and_import_ror_snapshot(
    archive_url: str,
    destination_dir: Path,
    source_url: str,
    release_date: date,
    ror_version: str,
    schema_version: str | None = None,
    set_active: bool = True,
    cache: RorCache | None = None,
) -> int:
    """Sync wrapper around ``download_and_import_ror_snapshot``."""
    return asyncio.run(
        download_and_import_ror_snapshot(
            archive_url=archive_url,
            destination_dir=destination_dir,
            source_url=source_url,
            release_date=release_date,
            ror_version=ror_version,
            schema_version=schema_version,
            set_active=set_active,
            cache=cache,
        )
    )
