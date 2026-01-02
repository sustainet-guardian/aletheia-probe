# SPDX-License-Identifier: MIT
"""Comprehensive tests for article_retraction_checker module."""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import aiohttp
import pytest

from aletheia_probe.article_retraction_checker import (
    ArticleRetractionChecker,
    ArticleRetractionResult,
    check_article_retraction,
)
from aletheia_probe.cache import RetractionCache


@pytest.fixture
def retraction_cache(isolated_test_cache):
    """Create RetractionCache from isolated test cache path."""
    return RetractionCache(isolated_test_cache)


class TestArticleRetractionResult:
    """Test suite for ArticleRetractionResult class."""

    def test_init_default_values(self):
        """Test ArticleRetractionResult initialization with defaults."""
        result = ArticleRetractionResult(doi="10.1234/test")

        assert result.doi == "10.1234/test"
        assert result.is_retracted is False
        assert result.retraction_type is None
        assert result.retraction_date is None
        assert result.retraction_doi is None
        assert result.retraction_reason is None
        assert result.sources == []
        assert result.checked_sources == []

    def test_init_with_all_values(self):
        """Test ArticleRetractionResult initialization with all values."""
        sources = ["crossref"]
        checked_sources = ["crossref", "retraction_watch"]

        result = ArticleRetractionResult(
            doi="10.1234/test",
            is_retracted=True,
            retraction_type="misconduct",
            retraction_date="2023-01-15",
            retraction_doi="10.1234/retraction",
            retraction_reason="Data fabrication",
            sources=sources,
            checked_sources=checked_sources,
        )

        assert result.doi == "10.1234/test"
        assert result.is_retracted is True
        assert result.retraction_type == "misconduct"
        assert result.retraction_date == "2023-01-15"
        assert result.retraction_doi == "10.1234/retraction"
        assert result.retraction_reason == "Data fabrication"
        assert result.sources == sources
        assert result.checked_sources == checked_sources

    def test_to_dict(self):
        """Test conversion to dictionary representation."""
        result = ArticleRetractionResult(
            doi="10.1234/test",
            is_retracted=True,
            retraction_type="misconduct",
            retraction_date="2023-01-15",
            retraction_doi="10.1234/retraction",
            retraction_reason="Data fabrication",
            sources=["crossref"],
            checked_sources=["crossref"],
        )

        result_dict = result.to_dict()

        assert isinstance(result_dict, dict)
        assert result_dict["doi"] == "10.1234/test"
        assert result_dict["is_retracted"] is True
        assert result_dict["retraction_type"] == "misconduct"
        assert result_dict["retraction_date"] == "2023-01-15"
        assert result_dict["retraction_doi"] == "10.1234/retraction"
        assert result_dict["retraction_reason"] == "Data fabrication"
        assert result_dict["sources"] == ["crossref"]
        assert result_dict["checked_sources"] == ["crossref"]


class TestArticleRetractionCheckerInit:
    """Test suite for ArticleRetractionChecker initialization."""

    def test_init_default_email(self, retraction_cache):
        """Test ArticleRetractionChecker initialization with default email."""
        checker = ArticleRetractionChecker(retraction_cache)

        assert checker.email == "noreply@aletheia-probe.org"
        assert checker.crossref_base_url == "https://api.crossref.org"
        assert "User-Agent" in checker.headers
        # Verify exact User-Agent format instead of substring matching
        expected_user_agent = "AletheiaProbe/1.0 (mailto:noreply@aletheia-probe.org)"
        assert checker.headers["User-Agent"] == expected_user_agent

    def test_init_custom_email(self, retraction_cache):
        """Test ArticleRetractionChecker initialization with custom email."""
        custom_email = "test@example.com"
        checker = ArticleRetractionChecker(retraction_cache, email=custom_email)

        assert checker.email == custom_email
        # Verify exact User-Agent format instead of substring matching
        expected_user_agent = f"AletheiaProbe/1.0 (mailto:{custom_email})"
        assert checker.headers["User-Agent"] == expected_user_agent


class TestArticleRetractionCheckerDOIValidation:
    """Test suite for DOI validation and normalization."""

    @pytest.mark.asyncio
    async def test_check_doi_empty_string(self, retraction_cache):
        """Test handling of empty DOI string."""
        checker = ArticleRetractionChecker(retraction_cache)
        result = await checker.check_doi("")

        assert result.doi == ""
        assert result.is_retracted is False

    @pytest.mark.asyncio
    async def test_check_doi_normalization(self, retraction_cache):
        """Test DOI normalization (lowercase and strip)."""
        checker = ArticleRetractionChecker(retraction_cache)

        # Mock the cache and API to check what DOI is being used
        with patch.object(
            retraction_cache, "get_article_retraction", return_value=None
        ):
            with (
                patch.object(checker, "_check_retraction_watch_local") as mock_rw,
                patch.object(checker, "_check_crossref_api") as mock_crossref,
            ):
                mock_rw.return_value = ArticleRetractionResult(
                    doi="10.1234/test", is_retracted=False
                )
                mock_crossref.return_value = ArticleRetractionResult(
                    doi="10.1234/test", is_retracted=False
                )

                # Test with uppercase and whitespace
                await checker.check_doi("  10.1234/TEST  ")

                # Verify normalized DOI was used
                mock_rw.assert_called_once_with("10.1234/test")


class TestArticleRetractionCheckerCacheIntegration:
    """Test suite for cache integration."""

    @pytest.mark.asyncio
    async def test_check_doi_cache_hit(self, retraction_cache):
        """Test that cache hit returns cached result without API calls."""
        checker = ArticleRetractionChecker(retraction_cache)
        doi = "10.1234/test.cached"

        # Pre-populate cache
        retraction_cache.cache_article_retraction(
            doi=doi,
            is_retracted=True,
            source="cache",
            retraction_type="misconduct",
            retraction_date="2023-01-15",
            retraction_doi="10.1234/retraction",
            retraction_reason="Data fabrication",
        )

        # Check DOI - should return cached result
        result = await checker.check_doi(doi)

        assert result.doi == doi
        assert result.is_retracted is True
        assert result.retraction_type == "misconduct"
        assert result.retraction_date == "2023-01-15"
        assert result.retraction_doi == "10.1234/retraction"
        assert result.retraction_reason == "Data fabrication"
        assert "cache" in result.sources

    @pytest.mark.asyncio
    async def test_check_doi_cache_miss_caches_result(self, retraction_cache):
        """Test that cache miss fetches from API and caches result."""
        checker = ArticleRetractionChecker(retraction_cache)
        doi = "10.1234/test.new"

        # Mock the API to return a retraction
        with patch.object(checker, "_check_retraction_watch_local") as mock_rw:
            mock_rw.return_value = ArticleRetractionResult(
                doi=doi,
                is_retracted=True,
                retraction_type="misconduct",
                sources=["retraction_watch"],
            )

            # First call - should fetch from API
            result = await checker.check_doi(doi)
            assert result.is_retracted is True

            # Verify result was cached
            cached = retraction_cache.get_article_retraction(doi)
            assert cached is not None
            assert cached["is_retracted"] is True


class TestArticleRetractionCheckerRetractionWatchLocal:
    """Test suite for local Retraction Watch checking."""

    @pytest.mark.asyncio
    async def test_check_retraction_watch_local_found(self, retraction_cache):
        """Test finding retraction in local Retraction Watch data."""
        checker = ArticleRetractionChecker(retraction_cache)
        doi = "10.1234/retracted"

        # Pre-populate cache with Retraction Watch data
        retraction_cache.cache_article_retraction(
            doi=doi,
            is_retracted=True,
            source="retraction_watch",
            retraction_type="misconduct",
            retraction_reason="Data fabrication",
        )

        result = await checker._check_retraction_watch_local(doi)

        assert result.doi == doi
        assert result.is_retracted is True
        assert result.sources == ["retraction_watch"]
        assert result.retraction_type == "misconduct"

    @pytest.mark.asyncio
    async def test_check_retraction_watch_local_not_found(self, retraction_cache):
        """Test when DOI not found in local Retraction Watch data."""
        checker = ArticleRetractionChecker(retraction_cache)
        doi = "10.1234/not.in.rw"

        result = await checker._check_retraction_watch_local(doi)

        assert result.doi == doi
        assert result.is_retracted is False

    @pytest.mark.asyncio
    async def test_check_retraction_watch_local_wrong_source(self, retraction_cache):
        """Test that only retraction_watch source is returned."""
        checker = ArticleRetractionChecker(retraction_cache)
        doi = "10.1234/crossref.only"

        # Cache with different source
        retraction_cache.cache_article_retraction(
            doi=doi, is_retracted=True, source="crossref"
        )

        result = await checker._check_retraction_watch_local(doi)

        # Should not return result since source is not retraction_watch
        assert result.is_retracted is False


class TestArticleRetractionCheckerCrossrefAPI:
    """Test suite for Crossref API integration."""

    @pytest.mark.asyncio
    async def test_check_crossref_api_success_with_retraction(self, retraction_cache):
        """Test successful Crossref API response with retraction."""
        checker = ArticleRetractionChecker(retraction_cache)
        doi = "10.1234/retracted"

        crossref_response = {
            "status": "ok",
            "message": {
                "DOI": doi,
                "type": "journal-article",
                "title": ["Retracted Article"],
                "updated-by": [
                    {
                        "DOI": "10.1234/retraction.notice",
                        "type": "retraction",
                        "label": "Retraction notice",
                        "updated": {
                            "date-parts": [[2023, 1, 15]],
                            "timestamp": 1673740800000,
                        },
                    }
                ],
            },
        }

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value=crossref_response)
            mock_get.return_value.__aenter__.return_value = mock_response

            result = await checker._check_crossref_api(doi)

            assert result.doi == doi
            assert result.is_retracted is True
            assert result.retraction_type == "retraction"
            assert result.retraction_doi == "10.1234/retraction.notice"
            assert result.retraction_date == "2023-01-15"
            assert "crossref" in result.sources

    @pytest.mark.asyncio
    async def test_check_crossref_api_no_retraction(self, retraction_cache):
        """Test Crossref API response for non-retracted article."""
        checker = ArticleRetractionChecker(retraction_cache)
        doi = "10.1234/not.retracted"

        crossref_response = {
            "status": "ok",
            "message": {
                "DOI": doi,
                "type": "journal-article",
                "title": ["Normal Article"],
            },
        }

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value=crossref_response)
            mock_get.return_value.__aenter__.return_value = mock_response

            result = await checker._check_crossref_api(doi)

            assert result.doi == doi
            assert result.is_retracted is False

    @pytest.mark.asyncio
    async def test_check_crossref_api_404_not_found(self, retraction_cache):
        """Test Crossref API 404 response."""
        checker = ArticleRetractionChecker(retraction_cache)
        doi = "10.1234/not.found"

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 404
            mock_get.return_value.__aenter__.return_value = mock_response

            result = await checker._check_crossref_api(doi)

            assert result.doi == doi
            assert result.is_retracted is False

    @pytest.mark.asyncio
    async def test_check_crossref_api_500_server_error(self, retraction_cache):
        """Test Crossref API 500 server error handling."""
        checker = ArticleRetractionChecker(retraction_cache)
        doi = "10.1234/server.error"

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 500
            mock_get.return_value.__aenter__.return_value = mock_response

            result = await checker._check_crossref_api(doi)

            assert result.doi == doi
            assert result.is_retracted is False

    @pytest.mark.asyncio
    async def test_check_crossref_api_timeout(self, retraction_cache):
        """Test Crossref API timeout handling."""
        checker = ArticleRetractionChecker(retraction_cache)
        doi = "10.1234/timeout"

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_get.return_value.__aenter__.side_effect = asyncio.TimeoutError(
                "Request timeout"
            )

            result = await checker._check_crossref_api(doi)

            assert result.doi == doi
            assert result.is_retracted is False

    @pytest.mark.asyncio
    async def test_check_crossref_api_client_error(self, retraction_cache):
        """Test Crossref API client error handling."""
        checker = ArticleRetractionChecker(retraction_cache)
        doi = "10.1234/client.error"

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_get.return_value.__aenter__.side_effect = aiohttp.ClientError(
                "Client error"
            )

            result = await checker._check_crossref_api(doi)

            assert result.doi == doi
            assert result.is_retracted is False

    @pytest.mark.asyncio
    async def test_check_crossref_api_json_decode_error(self, retraction_cache):
        """Test Crossref API JSON decode error handling."""
        checker = ArticleRetractionChecker(retraction_cache)
        doi = "10.1234/bad.json"

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(side_effect=ValueError("Invalid JSON"))
            mock_get.return_value.__aenter__.return_value = mock_response

            result = await checker._check_crossref_api(doi)

            assert result.doi == doi
            assert result.is_retracted is False

    @pytest.mark.asyncio
    async def test_check_crossref_api_update_to_retraction(self, retraction_cache):
        """Test Crossref API with 'update-to' retraction field."""
        checker = ArticleRetractionChecker(retraction_cache)
        doi = "10.1234/retracted.via.update.to"

        crossref_response = {
            "status": "ok",
            "message": {
                "DOI": doi,
                "update-to": [
                    {
                        "DOI": "10.1234/retraction",
                        "type": "retraction",
                        "label": "Retracted",
                    }
                ],
            },
        }

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value=crossref_response)
            mock_get.return_value.__aenter__.return_value = mock_response

            result = await checker._check_crossref_api(doi)

            assert result.doi == doi
            assert result.is_retracted is True


class TestArticleRetractionCheckerParseRetraction:
    """Test suite for parsing retraction information."""

    def test_parse_crossref_retraction_basic(self, retraction_cache):
        """Test parsing basic retraction information."""
        checker = ArticleRetractionChecker(retraction_cache)
        doi = "10.1234/test"
        update_info = {
            "DOI": "10.1234/retraction",
            "type": "retraction",
            "label": "Retracted due to misconduct",
        }
        full_message = {}

        result = checker._parse_crossref_retraction(doi, update_info, full_message)

        assert result.doi == doi
        assert result.is_retracted is True
        assert result.retraction_type == "retraction"
        assert result.retraction_doi == "10.1234/retraction"
        assert result.retraction_reason == "Retracted due to misconduct"
        assert "crossref" in result.sources

    def test_parse_crossref_retraction_with_date(self, retraction_cache):
        """Test parsing retraction with date information."""
        checker = ArticleRetractionChecker(retraction_cache)
        doi = "10.1234/test"
        update_info = {
            "DOI": "10.1234/retraction",
            "type": "retraction",
            "updated": {"date-parts": [[2023, 3, 15]]},
        }
        full_message = {}

        result = checker._parse_crossref_retraction(doi, update_info, full_message)

        assert result.retraction_date == "2023-03-15"

    def test_parse_crossref_retraction_with_incomplete_date(self, retraction_cache):
        """Test parsing retraction with incomplete date (less than 3 parts)."""
        checker = ArticleRetractionChecker(retraction_cache)
        doi = "10.1234/test"
        update_info = {
            "DOI": "10.1234/retraction",
            "type": "retraction",
            "updated": {"date-parts": [[2023, 3]]},  # Only year and month
        }
        full_message = {}

        result = checker._parse_crossref_retraction(doi, update_info, full_message)

        # Should not set retraction_date if incomplete
        assert result.retraction_date is None

    def test_parse_crossref_retraction_is_notice(self, retraction_cache):
        """Test parsing retraction notice (update-to field)."""
        checker = ArticleRetractionChecker()
        doi = "10.1234/test"
        update_info = {"DOI": "10.1234/retraction", "type": "retraction"}
        full_message = {}

        result = checker._parse_crossref_retraction(
            doi, update_info, full_message, is_notice=True
        )


class TestArticleRetractionCheckerCacheResult:
    """Test suite for caching results."""

    def test_cache_result_retracted(self, retraction_cache):
        """Test caching a retracted article result."""
        checker = ArticleRetractionChecker(retraction_cache)
        doi = "10.1234/retracted"

        result = ArticleRetractionResult(
            doi=doi,
            is_retracted=True,
            retraction_type="misconduct",
            retraction_date="2023-01-15",
            retraction_doi="10.1234/retraction",
            retraction_reason="Data fabrication",
            sources=["crossref"],
        )

        checker._cache_result(result, "crossref")

        # Verify cached
        cached = retraction_cache.get_article_retraction(doi)
        assert cached is not None
        assert cached["is_retracted"] is True
        assert cached["retraction_type"] == "misconduct"
        assert cached["source"] == "crossref"

    def test_cache_result_not_retracted(self, retraction_cache):
        """Test caching a non-retracted article result."""
        checker = ArticleRetractionChecker(retraction_cache)
        doi = "10.1234/not.retracted"

        result = ArticleRetractionResult(doi=doi, is_retracted=False)

        checker._cache_result(result, "multiple")

        # Verify cached
        cached = retraction_cache.get_article_retraction(doi)
        assert cached is not None
        assert cached["is_retracted"] is False
        assert cached["source"] == "multiple"


class TestArticleRetractionCheckerIntegration:
    """Integration tests for the complete check workflow."""

    @pytest.mark.asyncio
    async def test_check_doi_workflow_retraction_watch_hit(self, retraction_cache):
        """Test complete workflow when Retraction Watch has the retraction."""
        checker = ArticleRetractionChecker(retraction_cache)
        doi = "10.1234/in.rw"

        # Mock Retraction Watch to return retraction (not using cache)
        # We want to test the actual workflow, not cache hit
        with patch.object(checker, "_check_retraction_watch_local") as mock_rw:
            mock_rw.return_value = ArticleRetractionResult(
                doi=doi,
                is_retracted=True,
                retraction_type="misconduct",
                sources=["retraction_watch"],
            )

            result = await checker.check_doi(doi)

            assert result.is_retracted is True
            assert "retraction_watch_local" in result.checked_sources
            # Should stop after RW hit, not check Crossref
            assert "crossref" not in result.checked_sources

    @pytest.mark.asyncio
    async def test_check_doi_workflow_crossref_only(self, retraction_cache):
        """Test workflow when only Crossref has the retraction."""
        checker = ArticleRetractionChecker(retraction_cache)
        doi = "10.1234/in.crossref"

        crossref_response = {
            "status": "ok",
            "message": {
                "DOI": doi,
                "updated-by": [{"DOI": "10.1234/retraction", "type": "retraction"}],
            },
        }

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value=crossref_response)
            mock_get.return_value.__aenter__.return_value = mock_response

            result = await checker.check_doi(doi)

            assert result.is_retracted is True
            assert "retraction_watch_local" in result.checked_sources
            assert "crossref" in result.checked_sources

    @pytest.mark.asyncio
    async def test_check_doi_workflow_not_retracted(self, retraction_cache):
        """Test workflow when article is not retracted anywhere."""
        checker = ArticleRetractionChecker(retraction_cache)
        doi = "10.1234/clean.article"

        crossref_response = {
            "status": "ok",
            "message": {"DOI": doi, "type": "journal-article"},
        }

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value=crossref_response)
            mock_get.return_value.__aenter__.return_value = mock_response

            result = await checker.check_doi(doi)

            assert result.is_retracted is False
            assert len(result.checked_sources) == 2  # Both sources checked

            # Verify negative result was cached
            cached = retraction_cache.get_article_retraction(doi)
            assert cached is not None
            assert cached["is_retracted"] is False

    @pytest.mark.asyncio
    async def test_check_doi_workflow_crossref_error_continues(self, retraction_cache):
        """Test that workflow continues when Crossref API fails."""
        checker = ArticleRetractionChecker(retraction_cache)
        doi = "10.1234/crossref.error"

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_get.return_value.__aenter__.side_effect = aiohttp.ClientError(
                "Network error"
            )

            result = await checker.check_doi(doi)

            # Should return not retracted even with error
            assert result.is_retracted is False
            assert "retraction_watch_local" in result.checked_sources
            assert "crossref" in result.checked_sources


class TestCheckArticleRetractionConvenienceFunction:
    """Test suite for the convenience function."""

    @pytest.mark.asyncio
    async def test_check_article_retraction_function(self, retraction_cache):
        """Test the convenience function creates checker and calls check_doi."""
        doi = "10.1234/convenience.test"

        crossref_response = {
            "status": "ok",
            "message": {"DOI": doi, "type": "journal-article"},
        }

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value=crossref_response)
            mock_get.return_value.__aenter__.return_value = mock_response

            result = await check_article_retraction(doi)

            assert isinstance(result, ArticleRetractionResult)
            assert result.doi == doi
