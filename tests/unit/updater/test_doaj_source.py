# SPDX-License-Identifier: MIT
"""Tests for DOAJ journal list data source."""

import os
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from aletheia_probe.enums import AssessmentType
from aletheia_probe.updater.sources.doaj import DOAJ_CSV_HEADERS, DOAJSource


DOAJ_HEADERS = (
    "Journal title",
    "Journal URL",
    "Journal ISSN (print version)",
    "Journal EISSN (online version)",
    "Publisher",
    "Subjects",
)
DOAJ_HEADER_LINE = ",".join(DOAJ_HEADERS) + "\n"
DOAJ_SAMPLE_ROW = (
    "Nature,https://nature.com,0028-0836,1476-4687,Springer Nature,Science\n"
)
NON_DOAJ_HEADER = "foo,bar,baz\n"


@pytest.fixture
def source(tmp_path: Path) -> DOAJSource:
    """Create DOAJ source pointing at an empty temporary data directory."""
    return DOAJSource(data_dir=tmp_path / "doaj")


def _write_csv(path: Path, content: str | None = None) -> Path:
    if content is None:
        content = DOAJ_HEADER_LINE + DOAJ_SAMPLE_ROW
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_source_metadata(source: DOAJSource) -> None:
    """Test source name and classification list type."""
    assert source.get_name() == "doaj"
    assert source.get_list_type() == AssessmentType.LEGITIMATE


@pytest.mark.asyncio
async def test_no_file_found(source: DOAJSource) -> None:
    """When no CSV exists, should_update is False and fetch_data returns empty list."""
    assert source.should_update() is False
    assert source.skip_reason == "file_not_found"
    assert await source.fetch_data() == []
    assert source.data_dir.is_dir()


@pytest.mark.asyncio
async def test_valid_doaj_csv_loaded(source: DOAJSource) -> None:
    """Valid DOAJ CSV is detected and parsed into journal records."""
    _write_csv(source.data_dir / "doaj_export.csv")

    journals = await source.fetch_data()
    assert len(journals) == 1
    assert journals[0]["journal_name"] == "Nature"
    assert journals[0]["issn"] == "0028-0836"


@pytest.mark.asyncio
async def test_invalid_csv_headers_ignored(source: DOAJSource) -> None:
    """A CSV lacking DOAJ headers is ignored."""
    _write_csv(source.data_dir / "random.csv", content=NON_DOAJ_HEADER)

    assert source.should_update() is False
    assert source.skip_reason == "file_not_found"
    assert await source.fetch_data() == []


@pytest.mark.asyncio
async def test_multiple_csvs_uses_newest(source: DOAJSource) -> None:
    """When multiple valid DOAJ CSVs exist, newest by mtime is loaded."""
    older = _write_csv(
        source.data_dir / "old.csv",
        content=DOAJ_HEADER_LINE + "Old Journal,https://old.com,1111-1111,,Pub,Sub\n",
    )
    newer = _write_csv(
        source.data_dir / "new.csv",
        content=DOAJ_HEADER_LINE + "New Journal,https://new.com,2222-2222,,Pub,Sub\n",
    )

    now = time.time()
    os.utime(older, (now - 3600, now - 3600))
    os.utime(newer, (now, now))

    journals = await source.fetch_data()
    assert len(journals) == 1
    assert journals[0]["journal_name"] == "New Journal"


def test_should_update_mtime_behavior(source: DOAJSource) -> None:
    """should_update() returns True for newer files and False for older files."""
    csv_path = _write_csv(source.data_dir / "doaj.csv")
    file_mtime = csv_path.stat().st_mtime

    past_update = datetime.fromtimestamp(file_mtime - 100, tz=timezone.utc).replace(
        tzinfo=None
    )
    recent_update = datetime.fromtimestamp(file_mtime + 100, tz=timezone.utc).replace(
        tzinfo=None
    )

    with patch(
        "aletheia_probe.updater.sources.doaj.DataSourceManager.get_source_last_updated",
        return_value=past_update,
    ):
        assert source.should_update() is True

    with patch(
        "aletheia_probe.updater.sources.doaj.DataSourceManager.get_source_last_updated",
        return_value=recent_update,
    ):
        assert source.should_update() is False
