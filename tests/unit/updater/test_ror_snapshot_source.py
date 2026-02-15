# SPDX-License-Identifier: MIT
"""Tests for ROR snapshot importer utilities."""

import json
import tempfile
import zipfile
from datetime import date
from pathlib import Path

import pytest

from aletheia_probe.cache import RorCache
from aletheia_probe.cache.connection_utils import get_configured_connection
from aletheia_probe.cache.schema import init_database
from aletheia_probe.ror_snapshot_importer import RorSnapshotImporter


@pytest.fixture
def temp_cache() -> RorCache:
    """Create a temporary cache for ROR snapshot importer tests."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as file_obj:
        cache_path = Path(file_obj.name)

    init_database(cache_path)
    cache = RorCache(cache_path)
    yield cache
    cache_path.unlink(missing_ok=True)


@pytest.fixture
def sample_organizations() -> list[dict]:
    """Return sample ROR organizations payload."""
    return [
        {
            "id": "https://ror.org/0117jxy09",
            "status": "active",
            "types": ["company"],
            "domains": ["springernature.com"],
            "names": [
                {
                    "value": "Springer Nature (Germany)",
                    "lang": "en",
                    "types": ["label", "ror_display"],
                }
            ],
            "external_ids": [],
            "relationships": [],
            "links": [{"type": "website", "value": "https://www.springernature.com"}],
            "locations": [],
            "admin": {
                "created": {"date": "2018-11-14", "schema_version": "2.1"},
                "last_modified": {"date": "2025-10-06", "schema_version": "2.1"},
            },
        }
    ]


def test_load_organizations_from_archive(
    temp_cache: RorCache, sample_organizations: list[dict]
) -> None:
    importer = RorSnapshotImporter(cache=temp_cache)

    with tempfile.TemporaryDirectory() as temp_dir:
        archive_path = Path(temp_dir) / "ror.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.writestr("ror-data.json", json.dumps(sample_organizations))

        organizations = importer.load_organizations_from_archive(archive_path)
        assert len(organizations) == 1
        assert organizations[0]["id"] == "https://ror.org/0117jxy09"


def test_import_archive(temp_cache: RorCache, sample_organizations: list[dict]) -> None:
    importer = RorSnapshotImporter(cache=temp_cache)

    with tempfile.TemporaryDirectory() as temp_dir:
        archive_path = Path(temp_dir) / "ror.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.writestr("ror-data.json", json.dumps(sample_organizations))

        snapshot_id = importer.import_archive(
            archive_path=archive_path,
            source_url="https://zenodo.org/records/18419061",
            release_date=date(2026, 1, 29),
            ror_version="v2.2",
            schema_version=None,
            set_active=True,
        )
        assert snapshot_id > 0

    with get_configured_connection(temp_cache.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM ror_snapshots")
        assert cursor.fetchone()[0] == 1
        cursor.execute("SELECT COUNT(*) FROM ror_organizations")
        assert cursor.fetchone()[0] == 1


def test_load_organizations_from_archive_raises_without_json(
    temp_cache: RorCache,
) -> None:
    importer = RorSnapshotImporter(cache=temp_cache)

    with tempfile.TemporaryDirectory() as temp_dir:
        archive_path = Path(temp_dir) / "ror.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.writestr("README.txt", "no json file here")

        with pytest.raises(ValueError, match="No JSON organization payload"):
            importer.load_organizations_from_archive(archive_path)
