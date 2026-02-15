# SPDX-License-Identifier: MIT
"""Tests for the ROR cache module."""

import tempfile
from datetime import date
from pathlib import Path

import pytest

from aletheia_probe.cache import RorCache
from aletheia_probe.cache.connection_utils import get_configured_connection
from aletheia_probe.cache.schema import init_database


@pytest.fixture
def temp_cache() -> RorCache:
    """Create a temporary cache for ROR tests."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as file_obj:
        cache_path = Path(file_obj.name)

    init_database(cache_path)
    cache = RorCache(cache_path)
    yield cache

    cache_path.unlink(missing_ok=True)


@pytest.fixture
def sample_ror_organization() -> dict:
    """Sample ROR organization payload."""
    return {
        "id": "https://ror.org/0117jxy09",
        "status": "active",
        "established": 2015,
        "types": ["company", "funder"],
        "domains": ["springernature.com"],
        "names": [
            {
                "value": "Springer Nature (Germany)",
                "lang": "en",
                "types": ["label", "ror_display"],
            },
            {"value": "Springer Nature", "lang": "en", "types": ["alias"]},
        ],
        "links": [
            {"type": "website", "value": "https://www.springernature.com"},
            {
                "type": "wikipedia",
                "value": "https://en.wikipedia.org/wiki/Springer_Nature",
            },
        ],
        "external_ids": [
            {"type": "wikidata", "preferred": "Q21096327", "all": ["Q21096327"]},
            {
                "type": "fundref",
                "preferred": "501100020487",
                "all": ["501100020487"],
            },
        ],
        "relationships": [
            {
                "id": "https://ror.org/03dsk4d59",
                "type": "child",
                "label": "Springer Nature (United Kingdom)",
            }
        ],
        "locations": [
            {
                "geonames_details": {
                    "country_code": "DE",
                    "name": "Berlin",
                    "lat": 52.52437,
                    "lng": 13.41053,
                }
            }
        ],
        "admin": {
            "created": {"date": "2018-11-14", "schema_version": "2.1"},
            "last_modified": {"date": "2025-10-06", "schema_version": "2.1"},
        },
    }


class TestRorCache:
    """Test cases for RorCache."""

    def test_create_snapshot_and_get_active(self, temp_cache: RorCache) -> None:
        snapshot_id = temp_cache.create_snapshot(
            ror_version="v2.2",
            schema_version="2.1",
            release_date=date(2026, 1, 29),
            source_url="https://zenodo.org/records/18419061",
            record_count=115_598,
        )
        assert snapshot_id > 0
        assert temp_cache.get_active_snapshot_id() == snapshot_id

    def test_import_organizations(
        self, temp_cache: RorCache, sample_ror_organization: dict
    ) -> None:
        snapshot_id = temp_cache.create_snapshot(
            ror_version="v2.2",
            schema_version="2.1",
            release_date=date(2026, 1, 29),
            source_url="https://zenodo.org/records/18419061",
            record_count=1,
        )
        imported = temp_cache.import_organizations(
            snapshot_id, [sample_ror_organization]
        )
        assert imported == 1

        with get_configured_connection(temp_cache.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM ror_organizations")
            assert cursor.fetchone()[0] == 1
            cursor.execute("SELECT COUNT(*) FROM ror_names")
            assert cursor.fetchone()[0] >= 2
            cursor.execute("SELECT COUNT(*) FROM ror_domains")
            assert cursor.fetchone()[0] == 1
            cursor.execute("SELECT COUNT(*) FROM ror_external_ids")
            assert cursor.fetchone()[0] == 2

    def test_search_by_name(
        self, temp_cache: RorCache, sample_ror_organization: dict
    ) -> None:
        snapshot_id = temp_cache.create_snapshot(
            ror_version="v2.2",
            schema_version="2.1",
            release_date=date(2026, 1, 29),
            source_url="https://zenodo.org/records/18419061",
            record_count=1,
        )
        temp_cache.import_organizations(snapshot_id, [sample_ror_organization])

        candidates = temp_cache.search_organizations_by_name("Springer Nature")
        assert candidates
        assert candidates[0]["ror_id"] == "https://ror.org/0117jxy09"

    def test_search_by_domain(
        self, temp_cache: RorCache, sample_ror_organization: dict
    ) -> None:
        snapshot_id = temp_cache.create_snapshot(
            ror_version="v2.2",
            schema_version="2.1",
            release_date=date(2026, 1, 29),
            source_url="https://zenodo.org/records/18419061",
            record_count=1,
        )
        temp_cache.import_organizations(snapshot_id, [sample_ror_organization])

        candidates = temp_cache.search_organizations_by_domain(
            "https://www.springernature.com"
        )
        assert candidates
        assert candidates[0]["ror_id"] == "https://ror.org/0117jxy09"

    def test_upsert_journal_and_conference_links(
        self, temp_cache: RorCache, sample_ror_organization: dict
    ) -> None:
        snapshot_id = temp_cache.create_snapshot(
            ror_version="v2.2",
            schema_version="2.1",
            release_date=date(2026, 1, 29),
            source_url="https://zenodo.org/records/18419061",
            record_count=1,
        )
        temp_cache.import_organizations(snapshot_id, [sample_ror_organization])

        with get_configured_connection(temp_cache.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO journals (normalized_name, display_name) VALUES (?, ?)",
                ("nature", "Nature"),
            )
            journal_id = int(cursor.lastrowid)
            conn.commit()

        temp_cache.upsert_journal_link(
            journal_id=journal_id,
            ror_id="https://ror.org/0117jxy09",
            match_status="matched",
            confidence=0.97,
            matching_method="domain_exact",
            evidence={"domain_match": True},
            snapshot_id=snapshot_id,
        )

        temp_cache.upsert_conference_link(
            conference_id=journal_id,
            ror_id="https://ror.org/0117jxy09",
            match_status="matched",
            confidence=0.82,
            matching_method="name_fuzzy",
            evidence={"name_similarity": 0.91},
            snapshot_id=snapshot_id,
        )

        with get_configured_connection(temp_cache.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM journal_ror_links")
            assert cursor.fetchone()[0] == 1
            cursor.execute("SELECT COUNT(*) FROM conference_ror_links")
            assert cursor.fetchone()[0] == 1
