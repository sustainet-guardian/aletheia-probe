# SPDX-License-Identifier: MIT
"""Tests for the OpenAlex integration module."""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from aletheia_probe.openalex import OpenAlexClient, get_publication_stats


class TestOpenAlexClient:
    """Test cases for OpenAlexClient."""

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test OpenAlex client as async context manager."""
        async with OpenAlexClient() as client:
            assert client.session is not None

        # Session should be closed after context exit
        assert client.session is None or client.session.closed

    @pytest.mark.asyncio
    async def test_get_source_by_issn_success(self):
        """Test getting source by ISSN with successful response."""
        mock_response_data = {
            "results": [
                {
                    "id": "https://openalex.org/S123456789",
                    "display_name": "Nature",
                    "issn_l": "0028-0836",
                    "issn": ["0028-0836", "1476-4687"],
                }
            ]
        }

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value=mock_response_data)
            mock_response.raise_for_status = Mock()
            mock_get.return_value.__aenter__.return_value = mock_response

            async with OpenAlexClient() as client:
                result = await client.get_source_by_issn("0028-0836")

            assert result is not None
            assert result["display_name"] == "Nature"
            assert "0028-0836" in result["issn"]

    @pytest.mark.asyncio
    async def test_get_source_by_issn_not_found(self):
        """Test getting source by ISSN when not found."""
        mock_response_data: dict[str, list] = {"results": []}

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_response = AsyncMock()
            mock_response.json = AsyncMock(return_value=mock_response_data)
            mock_response.raise_for_status = Mock()
            mock_get.return_value.__aenter__.return_value = mock_response

            async with OpenAlexClient() as client:
                result = await client.get_source_by_issn("9999-9999")

            assert result is None

    @pytest.mark.asyncio
    async def test_get_source_by_issn_error(self):
        """Test getting source by ISSN with HTTP error."""
        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_response = AsyncMock()
            mock_response.raise_for_status.side_effect = Exception("HTTP Error")
            mock_get.return_value.__aenter__.return_value = mock_response

            async with OpenAlexClient() as client:
                result = await client.get_source_by_issn("0028-0836")

            assert result is None

    @pytest.mark.asyncio
    async def test_get_source_by_name_success(self):
        """Test getting source by name with successful response."""
        mock_response_data = {
            "results": [
                {
                    "id": "https://openalex.org/S123456789",
                    "display_name": "Journal of Computer Science",
                    "issn_l": "1234-5679",
                    "works_count": 1000,
                    "cited_by_count": 50000,
                    "first_publication_year": 2000,
                    "last_publication_year": 2023,
                    "type": "journal",
                }
            ]
        }

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value=mock_response_data)
            mock_response.raise_for_status = Mock()
            mock_get.return_value.__aenter__.return_value = mock_response

            async with OpenAlexClient() as client:
                result = await client.get_source_by_name("Journal of Computer Science")

            assert result is not None
            assert result["display_name"] == "Journal of Computer Science"

    @pytest.mark.asyncio
    async def test_enrich_journal_data_conference_series_fallback(self):
        """Test fallback to conference series name in enrich_journal_data."""
        full_conference_name = (
            "34th International Conference on Machine Learning (ICML 2024)"
        )
        series_name = "International Conference on Machine Learning"

        mock_full_name_source = None  # Simulate initial failure
        mock_series_source = {
            "id": "https://openalex.org/S987654321",
            "display_name": "International Conference on Machine Learning",
            "works_count": 5000,
            "cited_by_count": 100000,
            "first_publication_year": 1984,
            "last_publication_year": 2024,
            "type": "conference",
            "is_series_match": True,  # This should be set by get_source_by_name
        }

        # Mock get_source_by_name to simulate fallback
        with patch.object(
            OpenAlexClient, "get_source_by_name"
        ) as mock_get_source_by_name:
            mock_get_source_by_name.side_effect = [
                mock_full_name_source,  # First call (full name) fails
                mock_series_source,  # Second call (series name) succeeds
            ]

            # Mock extract_conference_series to return the series name
            with patch(
                "aletheia_probe.normalizer.input_normalizer.extract_conference_series",
                return_value=series_name,
            ) as mock_extract_series:
                async with OpenAlexClient() as client:
                    result = await client.enrich_journal_data(full_conference_name)

                # Assertions
                assert result is not None
                assert result["display_name"] == series_name
                assert "openalex_id" in result and result["openalex_id"] == "S987654321"
                assert mock_get_source_by_name.call_count == 2, (
                    "get_source_by_name should be called twice"
                )
                mock_get_source_by_name.assert_any_call(full_conference_name)
                mock_get_source_by_name.assert_any_call(
                    series_name, is_series_lookup=True
                )
                mock_extract_series.assert_called_once_with(full_conference_name)

    @pytest.mark.asyncio
    async def test_enrich_journal_data_series_fallback_edge_cases(self):
        """Test edge cases in series fallback logic."""

        # Test case 1: Series extraction returns None
        with patch.object(OpenAlexClient, "get_source_by_name") as mock_get_source:
            mock_get_source.return_value = None  # Both full name and series fail

            with patch(
                "aletheia_probe.normalizer.input_normalizer.extract_conference_series",
                return_value=None,  # Series extraction returns None
            ):
                async with OpenAlexClient() as client:
                    result = await client.enrich_journal_data("Some Conference")

                # Should only call once (for full name), not for series
                assert mock_get_source.call_count == 1
                assert result is None

        # Test case 2: Series name same as original
        with patch.object(OpenAlexClient, "get_source_by_name") as mock_get_source:
            mock_get_source.return_value = None

            with patch(
                "aletheia_probe.normalizer.input_normalizer.extract_conference_series",
                return_value="Some Conference",  # Same as input
            ):
                async with OpenAlexClient() as client:
                    result = await client.enrich_journal_data("Some Conference")

                # Should only call once (for full name), not for series since they're identical
                assert mock_get_source.call_count == 1
                assert result is None

        # Test case 3: Series extraction raises exception
        with patch.object(OpenAlexClient, "get_source_by_name") as mock_get_source:
            mock_get_source.return_value = None

            with patch(
                "aletheia_probe.normalizer.input_normalizer.extract_conference_series",
                side_effect=ValueError("Test error"),
            ):
                async with OpenAlexClient() as client:
                    result = await client.enrich_journal_data("Some Conference")

                # Should only call once (for full name), exception should be caught
                assert mock_get_source.call_count == 1
                assert result is None

    @pytest.mark.asyncio
    async def test_enrich_journal_data_series_fallback_both_fail(self):
        """Test when both full name and series name fail to find matches."""
        full_conference_name = "Unknown Conference 2024"
        series_name = "Unknown Conference"

        with patch.object(OpenAlexClient, "get_source_by_name") as mock_get_source:
            mock_get_source.return_value = None  # Both calls fail

            with patch(
                "aletheia_probe.normalizer.input_normalizer.extract_conference_series",
                return_value=series_name,
            ):
                async with OpenAlexClient() as client:
                    result = await client.enrich_journal_data(full_conference_name)

                # Should call twice (full name, then series)
                assert mock_get_source.call_count == 2
                mock_get_source.assert_any_call(full_conference_name)
                mock_get_source.assert_any_call(series_name, is_series_lookup=True)
                assert result is None

    @pytest.mark.asyncio
    async def test_get_publication_stats_standalone(self):
        """Test standalone get_publication_stats function."""
        with patch("aletheia_probe.openalex.OpenAlexClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.enrich_journal_data = AsyncMock(
                return_value={
                    "total_publications": 1000,
                    "recent_publications": 50,
                    "publication_years": [2020, 2021, 2022, 2023],
                }
            )
            mock_client_class.return_value = mock_client

            result = await get_publication_stats("Test Journal", issn="1234-5679")

            assert result is not None
            assert result["total_publications"] == 1000
            assert result["recent_publications"] == 50

    @pytest.mark.asyncio
    async def test_get_publication_stats_client_error(self):
        """Test get_publication_stats with client error."""
        with patch("aletheia_probe.openalex.OpenAlexClient") as mock_client_class:
            mock_client_class.side_effect = ValueError("Client error")

            result = await get_publication_stats("Test Journal")

            assert result is None
