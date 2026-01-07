# SPDX-License-Identifier: MIT
"""Tests for DOAJ backend."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import ClientError

from aletheia_probe.backend_exceptions import BackendError, RateLimitError
from aletheia_probe.backends.doaj import DOAJBackend
from aletheia_probe.models import BackendResult, BackendStatus, QueryInput


class TestDOAJBackend:
    """Test cases for DOAJBackend."""

    @pytest.fixture
    def backend(self):
        """Create backend instance with mocked cache."""
        backend = DOAJBackend()
        backend.assessment_cache = MagicMock()
        backend.assessment_cache.get_cached_assessment.return_value = None
        return backend

    @pytest.fixture
    def query_input(self):
        """Create sample query input."""
        return QueryInput(
            raw_input="Journal of Testing",
            normalized_name="journal of testing",
            identifiers={"issn": "1234-5678"},
            aliases=[],
        )

    @pytest.mark.asyncio
    async def test_query_success_issn(self, backend, query_input):
        """Test successful query by ISSN."""
        mock_response_data = {
            "results": [
                {
                    "bibjson": {
                        "title": "Journal of Testing",
                        "pissn": "1234-5678",
                        "eissn": "8765-4321",
                        "publisher": "Test Pub",
                    }
                }
            ]
        }

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value=mock_response_data)
            mock_get.return_value.__aenter__.return_value = mock_response

            result = await backend.query(query_input)

            assert result.status == BackendStatus.FOUND
            assert result.confidence == 1.0  # Exact ISSN match
            assert result.data["doaj_title"] == "Journal of Testing"
            assert result.data["doaj_issn"] == "1234-5678"

    @pytest.mark.asyncio
    async def test_query_success_title_exact(self, backend):
        """Test successful query by exact title."""
        query_input = QueryInput(
            raw_input="Journal of Testing",
            normalized_name="journal of testing",
            identifiers={},
            aliases=[],
        )
        mock_response_data = {
            "results": [
                {
                    "bibjson": {
                        "title": "Journal of Testing",
                        "pissn": "1234-5678",
                    }
                }
            ]
        }

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value=mock_response_data)
            mock_get.return_value.__aenter__.return_value = mock_response

            result = await backend.query(query_input)

            assert result.status == BackendStatus.FOUND
            assert result.confidence == 0.95  # Exact name match base confidence

    @pytest.mark.asyncio
    async def test_query_not_found(self, backend, query_input):
        """Test query with no results."""
        mock_response_data = {"results": []}

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value=mock_response_data)
            mock_get.return_value.__aenter__.return_value = mock_response

            result = await backend.query(query_input)

            assert result.status == BackendStatus.NOT_FOUND
            assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_rate_limit_handling(self, backend, query_input):
        """Test handling of rate limit responses."""
        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 429
            mock_response.headers = {"Retry-After": "10"}
            mock_get.return_value.__aenter__.return_value = mock_response

            # The _query_api catches exceptions and returns error result
            # But here we want to verify RateLimitError is raised internally
            # or handled correctly by the retry logic.
            # Since we mock the session, the retry logic in _fetch_from_doaj_api
            # will see RateLimitError raised by _check_rate_limit_response
            # and retry. We need to exhaust retries or mock success after retry.

            # Let's mock it raising RateLimitError constantly to see it fail eventually
            # wait, _query_api catches Exception.

            result = await backend.query(query_input)

            # Should eventually return RATE_LIMITED status
            assert result.status == BackendStatus.RATE_LIMITED
            assert "Rate limit exceeded" in result.error_message

    @pytest.mark.asyncio
    async def test_http_error_handling(self, backend, query_input):
        """Test handling of generic HTTP errors."""
        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 500
            mock_response.text = AsyncMock(return_value="Server Error")
            mock_get.return_value.__aenter__.return_value = mock_response

            result = await backend.query(query_input)

            assert result.status == BackendStatus.ERROR
            assert "DOAJ API error: HTTP 500" in result.error_message

    @pytest.mark.asyncio
    async def test_confidence_scoring_similarity(self, backend):
        """Test confidence scoring with similarity match."""
        query_input = QueryInput(
            raw_input="Journal of Computations",
            normalized_name="journal of computations",
            identifiers={},
            aliases=[],
        )

        # Similar but not exact title
        mock_response_data = {
            "results": [
                {
                    "bibjson": {
                        "title": "Journal of Computation",  # Close match
                        "pissn": "1234-5678",
                    }
                }
            ]
        }

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value=mock_response_data)
            mock_get.return_value.__aenter__.return_value = mock_response

            result = await backend.query(query_input)

            assert result.status == BackendStatus.FOUND
            # Should be between similarity threshold (0.6) and high (0.95)
            assert 0.6 <= result.confidence <= 0.95
