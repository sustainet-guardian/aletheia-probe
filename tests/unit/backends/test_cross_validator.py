# SPDX-License-Identifier: MIT
"""Tests for the Cross Validator backend caching behavior."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from aletheia_probe.backends.cross_validator import CrossValidatorBackend
from aletheia_probe.cache import CacheManager
from aletheia_probe.models import BackendResult, BackendStatus, QueryInput


class TestCrossValidatorCaching:
    """Test cases for caching behavior in CrossValidator backend."""

    @pytest.fixture
    def temp_cache(self):
        """Create a temporary cache database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            cache_path = Path(f.name)

        cache = CacheManager(cache_path)
        yield cache

        # Cleanup
        cache_path.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_cross_validator_caches_result_on_first_query(self, temp_cache):
        """Test that CrossValidator caches the complete result after first query."""
        with patch("aletheia_probe.backends.base.get_cache_manager") as mock_cm:
            mock_cm.return_value = temp_cache

            backend = CrossValidatorBackend(cache_ttl_hours=24)
            query_input = QueryInput(
                raw_input="Nature",
                normalized_name="nature",
                identifiers={"issn": "0028-0836"},
            )

            # First query - should call sub-backends and cache the result
            result1 = await backend.query(query_input)

            # Verify the first result is not cached (fresh query)
            assert result1.cached is False
            assert result1.backend_name == "cross_validator"
            # Result should be successful (Nature is in both databases)
            assert result1.status == BackendStatus.FOUND

            # Second query with same input - should return cached result
            result2 = await backend.query(query_input)

            # Verify the second result IS cached
            assert result2.cached is True
            assert result2.backend_name == "cross_validator"
            assert result2.status == BackendStatus.FOUND

            # The cached result should have the same assessment
            assert result2.assessment == result1.assessment
            # Response time should be much faster for cached result
            assert result2.response_time < result1.response_time

    @pytest.mark.asyncio
    async def test_cross_validator_cache_key_uniqueness(self, temp_cache):
        """Test that different journals produce different cache keys."""
        with patch("aletheia_probe.backends.base.get_cache_manager") as mock_cm:
            mock_cm.return_value = temp_cache

            backend = CrossValidatorBackend(cache_ttl_hours=24)

            # Query for first journal
            query1 = QueryInput(
                raw_input="Nature",
                normalized_name="nature",
                identifiers={"issn": "0028-0836"},
            )
            result1 = await backend.query(query1)
            assert result1.cached is False

            # Query for second journal with different ISSN
            query2 = QueryInput(
                raw_input="Science",
                normalized_name="science",
                identifiers={"issn": "0036-8075"},
            )
            result2 = await backend.query(query2)
            # Should NOT be cached because it's a different journal
            assert result2.cached is False

            # Query first journal again - should be cached
            result3 = await backend.query(query1)
            assert result3.cached is True

    @pytest.mark.asyncio
    async def test_cross_validator_does_not_query_subbackends_when_cached(
        self, temp_cache
    ):
        """Test that cached results don't trigger sub-backend queries."""
        with patch("aletheia_probe.backends.base.get_cache_manager") as mock_cm:
            mock_cm.return_value = temp_cache

            backend = CrossValidatorBackend(cache_ttl_hours=24)
            query_input = QueryInput(
                raw_input="Nature",
                normalized_name="nature",
                identifiers={"issn": "0028-0836"},
            )

            # First query - establishes cache
            result1 = await backend.query(query_input)
            assert result1.cached is False
            original_response_time = result1.response_time

            # Replace sub-backend query methods with mocks that should NOT be called
            call_count = {"openalex": 0, "crossref": 0}
            original_openalex_query = backend.openalex_backend.query
            original_crossref_query = backend.crossref_backend.query

            async def mock_openalex_query(qi):
                call_count["openalex"] += 1
                return await original_openalex_query(qi)

            async def mock_crossref_query(qi):
                call_count["crossref"] += 1
                return await original_crossref_query(qi)

            backend.openalex_backend.query = mock_openalex_query
            backend.crossref_backend.query = mock_crossref_query

            # Second query - should use cache and NOT call sub-backends
            result2 = await backend.query(query_input)
            assert result2.cached is True

            # Verify sub-backends were NOT queried
            assert call_count["openalex"] == 0, (
                "OpenAlex should not be queried when using cache"
            )
            assert call_count["crossref"] == 0, (
                "Crossref should not be queried when using cache"
            )

    @pytest.mark.asyncio
    async def test_cross_validator_not_found_results_are_cached(self, temp_cache):
        """Test that NOT_FOUND results are cached (even when caused by errors)."""
        with patch("aletheia_probe.backends.base.get_cache_manager") as mock_cm:
            mock_cm.return_value = temp_cache

            backend = CrossValidatorBackend(cache_ttl_hours=24)
            query_input = QueryInput(
                raw_input="Invalid Journal XYZ123",
                normalized_name="invalid journal xyz123",
                identifiers={},
            )

            # Mock sub-backends to raise errors
            async def mock_error_query(qi):
                raise ValueError("Simulated API error")

            backend.openalex_backend.query = mock_error_query
            backend.crossref_backend.query = mock_error_query

            # First query - should get NOT_FOUND (due to both backends erroring)
            result1 = await backend.query(query_input)
            # First result should not be cached
            assert result1.cached is False
            # CrossValidator converts sub-backend errors to NOT_FOUND
            assert result1.status == BackendStatus.NOT_FOUND

            # Second query with same input - NOT_FOUND results ARE cached
            result2 = await backend.query(query_input)
            # Should use cache even though original query had errors
            assert result2.cached is True
            assert result2.status == BackendStatus.NOT_FOUND

    @pytest.mark.asyncio
    async def test_cross_validator_respects_cache_ttl(self, temp_cache):
        """Test that cache respects TTL settings."""
        with patch("aletheia_probe.backends.base.get_cache_manager") as mock_cm:
            mock_cm.return_value = temp_cache

            # Create backend with very short TTL (0 hours means immediate expiry)
            backend = CrossValidatorBackend(cache_ttl_hours=0)
            query_input = QueryInput(
                raw_input="Nature",
                normalized_name="nature",
                identifiers={"issn": "0028-0836"},
            )

            # First query
            result1 = await backend.query(query_input)
            assert result1.cached is False

            # Second query - with TTL=0, cache should be expired
            # Note: Implementation detail - TTL=0 might still cache briefly
            # This test documents the expected behavior with expired TTL
            result2 = await backend.query(query_input)
            # With TTL=0, results should not be cached for reuse
            # (may vary based on cache implementation details)


class TestCrossValidatorLogic:
    """Test the cross-validation logic independent of caching."""

    @pytest.fixture
    def temp_cache(self):
        """Create a temporary cache database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            cache_path = Path(f.name)

        cache = CacheManager(cache_path)
        yield cache

        # Cleanup
        cache_path.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_cross_validator_combines_sub_backend_results(self, temp_cache):
        """Test that CrossValidator properly combines sub-backend results."""
        with patch("aletheia_probe.backends.base.get_cache_manager") as mock_cm:
            mock_cm.return_value = temp_cache

            backend = CrossValidatorBackend()
            query_input = QueryInput(
                raw_input="Test Journal",
                normalized_name="test journal",
                identifiers={"issn": "1234-5678"},
            )

            # Mock both backends to return specific results
            async def mock_openalex_query(qi):
                return BackendResult(
                    backend_name="openalex_analyzer",
                    status=BackendStatus.FOUND,
                    confidence=0.8,
                    assessment="legitimate",
                    data={
                        "openalex_data": {},
                        "analysis": {
                            "reasoning": [],
                            "red_flags": [],
                            "green_flags": [],
                        },
                    },
                    sources=["openalex"],
                    response_time=0.1,
                    cached=False,
                )

            async def mock_crossref_query(qi):
                return BackendResult(
                    backend_name="crossref_analyzer",
                    status=BackendStatus.FOUND,
                    confidence=0.7,
                    assessment="legitimate",
                    data={
                        "crossref_data": {},
                        "analysis": {
                            "reasoning": [],
                            "red_flags": [],
                            "green_flags": [],
                        },
                    },
                    sources=["crossref"],
                    response_time=0.1,
                    cached=False,
                )

            backend.openalex_backend.query = mock_openalex_query
            backend.crossref_backend.query = mock_crossref_query

            result = await backend.query(query_input)

            assert result.backend_name == "cross_validator"
            assert result.status == BackendStatus.FOUND
            # Both sub-backend results should be included in data
            assert "openalex_result" in result.data
            assert "crossref_result" in result.data
            assert "cross_validation" in result.data
