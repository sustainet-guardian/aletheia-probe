# SPDX-License-Identifier: MIT
"""Unit tests for the Kscien generic source and helpers."""

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from aiohttp import ClientSession

from aletheia_probe.updater.sources.kscien_generic import KscienGenericSource
from aletheia_probe.updater.sources.kscien_helpers import (
    KSCIEN_REST_PER_PAGE,
    KSCIEN_REST_URL,
    KSCIEN_TAXONOMY_IDS,
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
    """Test fetching data from one Kscien REST page."""
    publication_type: PublicationType = PublicationType.PREDATORY_CONFERENCES
    base_url = "https://kscien.org/non-recommended-journals-lists/"
    max_pages = 1

    def get_name() -> str:
        return "test_source"

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.headers = {"X-WP-Total": "2", "X-WP-TotalPages": "1"}
    mock_response.json.return_value = [
        {
            "id": 101,
            "link": "https://kscien.org/predatory-publishing/test-conference-1/",
            "title": {"rendered": "Test Conference &amp; Expo 1"},
            "content": {"rendered": "<p>http://example.com/conf1</p>"},
        },
        {
            "id": 102,
            "link": "https://kscien.org/predatory-publishing/test-conference-2/",
            "title": {"rendered": "Test Conference 2"},
            "content": {
                "rendered": '<p><a href="http://example.com/conf2">Visit Website</a></p>'
            },
        },
    ]

    mock_session.get.return_value.__aenter__.return_value = mock_response

    result = await fetch_kscien_data(
        mock_session, publication_type, base_url, max_pages, get_name
    )

    assert len(result) == 2
    assert result[0]["journal_name"] == "Test Conference & Expo 1"
    assert result[1]["metadata"]["website_url"] == "http://example.com/conf2"
    mock_session.get.assert_called_once_with(
        KSCIEN_REST_URL,
        params={
            "per_page": KSCIEN_REST_PER_PAGE,
            "page": 1,
            "publishing-taxonomy": KSCIEN_TAXONOMY_IDS[publication_type],
        },
    )


def create_mock_response(
    items: list[dict[str, Any]],
    total: int,
    total_pages: int,
    status: int = 200,
) -> AsyncMock:
    """Helper to create a mock REST response with the given items."""
    response = AsyncMock()
    response.status = status
    response.headers = {
        "X-WP-Total": str(total),
        "X-WP-TotalPages": str(total_pages),
    }
    response.json.return_value = items

    # The __aenter__ method of the context manager should return the response
    context_manager = AsyncMock()
    context_manager.__aenter__.return_value = response
    return context_manager


@pytest.mark.asyncio
async def test_fetch_kscien_data_pagination(mock_session):
    """Test fetching Kscien REST data with pagination."""
    publication_type: PublicationType = PublicationType.STANDALONE_JOURNALS
    base_url = "https://kscien.org/non-recommended-journals-lists/"
    max_pages = 2

    def get_name() -> str:
        return "test_source"

    page_1_items = [
        {
            "id": 201,
            "link": "https://kscien.org/predatory-publishing/test-journal-1/",
            "title": {"rendered": "Test Journal 1"},
            "content": {"rendered": "<p>http://example.com/j1</p>"},
        },
        {
            "id": 202,
            "link": "https://kscien.org/predatory-publishing/test-journal-2/",
            "title": {"rendered": "Test Journal 2"},
            "content": {"rendered": "<p>http://example.com/j2</p>"},
        },
    ]
    page_2_items = [
        {
            "id": 203,
            "link": "https://kscien.org/predatory-publishing/test-journal-3/",
            "title": {"rendered": "Test Journal 3"},
            "content": {"rendered": "<p>http://example.com/j3</p>"},
        }
    ]

    def get_side_effect(_url: str, *args: Any, **kwargs: Any) -> AsyncMock:
        page = kwargs["params"]["page"]
        if page == 2:
            return create_mock_response(page_2_items, total=3, total_pages=2)
        return create_mock_response(page_1_items, total=3, total_pages=2)

    mock_session.get.side_effect = get_side_effect

    result = await fetch_kscien_data(
        mock_session, publication_type, base_url, max_pages, get_name
    )

    assert len(result) == 3
    assert result[2]["journal_name"] == "Test Journal 3"
    assert mock_session.get.call_count == 2
    assert mock_session.get.call_args_list[1].kwargs["params"] == {
        "per_page": KSCIEN_REST_PER_PAGE,
        "page": 2,
        "publishing-taxonomy": KSCIEN_TAXONOMY_IDS[publication_type],
    }


@pytest.mark.asyncio
async def test_fetch_kscien_data_retries_transient_page_failure(mock_session):
    """Test that transient Kscien REST 5xx responses are retried."""
    publication_type: PublicationType = PublicationType.PREDATORY_CONFERENCES

    def get_name() -> str:
        return "test_source"

    page_1_items = [
        {
            "id": 301,
            "link": "https://kscien.org/predatory-publishing/test-conference-1/",
            "title": {"rendered": "Test Conference 1"},
            "content": {"rendered": "<p>http://example.com/c1</p>"},
        }
    ]
    page_2_items = [
        {
            "id": 302,
            "link": "https://kscien.org/predatory-publishing/test-conference-2/",
            "title": {"rendered": "Test Conference 2"},
            "content": {"rendered": "<p>http://example.com/c2</p>"},
        }
    ]

    responses = [
        create_mock_response(page_1_items, total=2, total_pages=2),
        create_mock_response([], total=2, total_pages=2, status=500),
        create_mock_response(page_2_items, total=2, total_pages=2),
    ]
    mock_session.get.side_effect = responses

    with patch(
        "aletheia_probe.updater.sources.kscien_helpers.asyncio.sleep",
        new_callable=AsyncMock,
    ) as mock_sleep:
        result = await fetch_kscien_data(
            mock_session,
            publication_type,
            "https://kscien.org/non-recommended-journals-lists/",
            2,
            get_name,
        )

    assert len(result) == 2
    assert result[1]["journal_name"] == "Test Conference 2"
    assert mock_session.get.call_count == 3
    mock_sleep.assert_awaited()


@pytest.mark.asyncio
async def test_fetch_kscien_data_rejects_incomplete_results(mock_session):
    """Test that persistent Kscien page failures do not return partial data."""
    publication_type: PublicationType = PublicationType.HIJACKED_JOURNALS

    def get_name() -> str:
        return "test_source"

    page_1_items = [
        {
            "id": 401,
            "link": "https://kscien.org/predatory-publishing/test-journal-1/",
            "title": {"rendered": "Test Journal 1"},
            "content": {"rendered": "<p>http://example.com/j1</p>"},
        }
    ]

    responses = [
        create_mock_response(page_1_items, total=2, total_pages=2),
        create_mock_response([], total=2, total_pages=2, status=500),
        create_mock_response([], total=2, total_pages=2, status=500),
        create_mock_response([], total=2, total_pages=2, status=500),
        create_mock_response([], total=2, total_pages=2, status=500),
    ]
    mock_session.get.side_effect = responses

    with (
        patch(
            "aletheia_probe.updater.sources.kscien_helpers.asyncio.sleep",
            new_callable=AsyncMock,
        ),
        pytest.raises(ValueError, match="HTTP 500 from REST page 2"),
    ):
        await fetch_kscien_data(
            mock_session,
            publication_type,
            "https://kscien.org/non-recommended-journals-lists/",
            2,
            get_name,
        )

    assert mock_session.get.call_count == 5


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
    publication_type: PublicationType = PublicationType.PUBLISHERS
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
