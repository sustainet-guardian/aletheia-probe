# SPDX-License-Identifier: MIT
"""Unit tests for the Kscien generic source and helpers."""

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from aiohttp import ClientSession

from aletheia_probe.updater.sources.kscien_generic import KscienGenericSource
from aletheia_probe.updater.sources.kscien_helpers import (
    PublicationType,
    deduplicate_entries,
    fetch_kscien_data,
)


@pytest.fixture
def mock_session():
    """Fixture for a mocked aiohttp ClientSession."""
    session = AsyncMock(spec=ClientSession)
    session.__aenter__.return_value = session
    return session


@pytest.mark.asyncio
async def test_fetch_kscien_data_single_page(mock_session):
    """Test fetching data from a single page."""
    publication_type: PublicationType = "predatory-conferences"
    base_url = (
        f"https://kscien.org/predatory-publishing/?_publishing_list={publication_type}"
    )
    max_pages = 1

    def get_name() -> str:
        return "test_source"

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.text.return_value = """
    <h4 class="p-title">Test Conference 1</h4><p><a href="http://example.com/conf1">Visit Website</a></p>
    <h4 class="p-title">Test Conference 2</h4><p><a href="http://example.com/conf2">Visit Website</a></p>
    """

    mock_session.get.return_value.__aenter__.return_value = mock_response

    result = await fetch_kscien_data(
        mock_session, publication_type, base_url, max_pages, get_name
    )

    assert len(result) == 2
    assert result[0]["journal_name"] == "Test Conference 1"
    assert result[1]["metadata"]["website_url"] == "http://example.com/conf2"


@pytest.mark.asyncio
async def test_fetch_kscien_data_pagination(mock_session):
    """Test fetching data with pagination."""
    publication_type: PublicationType = "standalone-journals"
    base_url = (
        f"https://kscien.org/predatory-publishing/?_publishing_list={publication_type}"
    )
    max_pages = 2

    def get_name() -> str:
        return "test_source"

    def get_side_effect(url: str, *args: Any, **kwargs: Any) -> AsyncMock:
        response = AsyncMock()
        if "pagination=2" in url:
            response.status = 200
            response.text.return_value = """
            <h4 class="p-title">Test Journal 3</h4><p><a href="http://example.com/j3">Visit Website</a></p>
            """
        else:
            response.status = 200
            response.text.return_value = """
            <h4 class="p-title">Test Journal 1</h4><p><a href="http://example.com/j1">Visit Website</a></p>
            <h4 class="p-title">Test Journal 2</h4><p><a href="http://example.com/j2">Visit Website</a></p>
            <a href="?_publishing_list=standalone-journals&_pagination=2">Next</a>
            """
        # The __aenter__ method of the context manager should return the response
        context_manager = AsyncMock()
        context_manager.__aenter__.return_value = response
        return context_manager

    mock_session.get.side_effect = get_side_effect

    result = await fetch_kscien_data(
        mock_session, publication_type, base_url, max_pages, get_name
    )

    assert len(result) == 3
    assert result[2]["journal_name"] == "Test Journal 3"


def test_deduplicate_entries():
    """Test deduplication of entries."""
    entries = [
        {"journal_name": "Test Journal", "normalized_name": "test journal"},
        {"journal_name": "Test Journal", "normalized_name": "test journal"},
        {"journal_name": "Another Journal", "normalized_name": "another journal"},
    ]
    result = deduplicate_entries(entries)
    assert len(result) == 2


@pytest.mark.asyncio
async def test_kscien_generic_source_fetch_data():
    """Test the KscienGenericSource fetch_data method."""
    publication_type: PublicationType = "publishers"
    source = KscienGenericSource(publication_type=publication_type)

    with (
        patch(
            "aletheia_probe.updater.sources.kscien_generic.fetch_kscien_data",
            new_callable=AsyncMock,
        ) as mock_fetch,
        patch(
            "aletheia_probe.updater.sources.kscien_generic.deduplicate_entries",
            side_effect=lambda x: x,
        ) as mock_deduplicate,
    ):
        mock_fetch.return_value = [
            {"journal_name": "Test Publisher", "normalized_name": "test publisher"}
        ]

        result = await source.fetch_data()

        assert len(result) == 1
        assert result[0]["journal_name"] == "Test Publisher"
        mock_fetch.assert_called_once()
        mock_deduplicate.assert_called_once()
