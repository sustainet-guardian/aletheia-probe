# SPDX-License-Identifier: MIT
"""Tests for the Cross Validator backend cached flag propagation."""

import pytest

from aletheia_probe.backends.cross_validator import CrossValidatorBackend
from aletheia_probe.models import BackendResult, BackendStatus, QueryInput


class TestCrossValidatorCachedFlag:
    """Test cases for cached flag propagation in CrossValidator backend."""

    @pytest.mark.asyncio
    async def test_cached_flag_both_backends_cached(self):
        """Test that cached=True when both sub-backends return cached results."""
        backend = CrossValidatorBackend()
        query_input = QueryInput(
            raw_input="Test Journal",
            normalized_name="test journal",
            identifiers={"issn": "1234-5678"},
        )

        # Mock both backends to return cached results
        async def mock_openalex_query(qi):
            return BackendResult(
                backend_name="openalex_analyzer",
                status=BackendStatus.FOUND,
                confidence=0.8,
                assessment="legitimate",
                data={"openalex_data": {}, "analysis": {}},
                sources=["openalex"],
                response_time=0.1,
                cached=True,  # Cached result
            )

        async def mock_crossref_query(qi):
            return BackendResult(
                backend_name="crossref_analyzer",
                status=BackendStatus.FOUND,
                confidence=0.7,
                assessment="legitimate",
                data={"crossref_data": {}, "analysis": {}},
                sources=["crossref"],
                response_time=0.1,
                cached=True,  # Cached result
            )

        backend.openalex_backend.query = mock_openalex_query
        backend.crossref_backend.query = mock_crossref_query

        result = await backend.query(query_input)

        assert result.backend_name == "cross_validator"
        assert result.cached is True  # Both backends cached, so result is cached

    @pytest.mark.asyncio
    async def test_cached_flag_one_backend_cached(self):
        """Test that cached=False when only one sub-backend returns cached result."""
        backend = CrossValidatorBackend()
        query_input = QueryInput(
            raw_input="Test Journal",
            normalized_name="test journal",
            identifiers={"issn": "1234-5678"},
        )

        # Mock one backend cached, one not
        async def mock_openalex_query(qi):
            return BackendResult(
                backend_name="openalex_analyzer",
                status=BackendStatus.FOUND,
                confidence=0.8,
                assessment="legitimate",
                data={"openalex_data": {}, "analysis": {}},
                sources=["openalex"],
                response_time=0.1,
                cached=True,  # Cached result
            )

        async def mock_crossref_query(qi):
            return BackendResult(
                backend_name="crossref_analyzer",
                status=BackendStatus.FOUND,
                confidence=0.7,
                assessment="legitimate",
                data={"crossref_data": {}, "analysis": {}},
                sources=["crossref"],
                response_time=0.5,
                cached=False,  # Fresh API call
            )

        backend.openalex_backend.query = mock_openalex_query
        backend.crossref_backend.query = mock_crossref_query

        result = await backend.query(query_input)

        assert result.backend_name == "cross_validator"
        assert result.cached is False  # One backend not cached, so result is not cached

    @pytest.mark.asyncio
    async def test_cached_flag_neither_backend_cached(self):
        """Test that cached=False when neither sub-backend returns cached result."""
        backend = CrossValidatorBackend()
        query_input = QueryInput(
            raw_input="Test Journal",
            normalized_name="test journal",
            identifiers={"issn": "1234-5678"},
        )

        # Mock both backends to return fresh results
        async def mock_openalex_query(qi):
            return BackendResult(
                backend_name="openalex_analyzer",
                status=BackendStatus.FOUND,
                confidence=0.8,
                assessment="legitimate",
                data={"openalex_data": {}, "analysis": {}},
                sources=["openalex"],
                response_time=0.5,
                cached=False,  # Fresh API call
            )

        async def mock_crossref_query(qi):
            return BackendResult(
                backend_name="crossref_analyzer",
                status=BackendStatus.FOUND,
                confidence=0.7,
                assessment="legitimate",
                data={"crossref_data": {}, "analysis": {}},
                sources=["crossref"],
                response_time=0.6,
                cached=False,  # Fresh API call
            )

        backend.openalex_backend.query = mock_openalex_query
        backend.crossref_backend.query = mock_crossref_query

        result = await backend.query(query_input)

        assert result.backend_name == "cross_validator"
        assert result.cached is False  # No backends cached, so result is not cached

    @pytest.mark.asyncio
    async def test_cached_flag_error_handling_exceptions(self):
        """Test that cached=False when both backends raise exceptions."""
        backend = CrossValidatorBackend()
        query_input = QueryInput(
            raw_input="Test Journal",
            normalized_name="test journal",
        )

        # Mock backend to raise exception
        async def mock_error_query(qi):
            raise ValueError("Test error")

        backend.openalex_backend.query = mock_error_query
        backend.crossref_backend.query = mock_error_query

        result = await backend.query(query_input)

        # When both backends have errors, CrossValidator handles it gracefully
        # and returns NOT_FOUND with error details in the data
        assert result.status == BackendStatus.NOT_FOUND
        assert result.cached is False  # Errors are not cached
        # Verify that both sub-backend errors are captured
        assert result.data["openalex_result"]["status"] == BackendStatus.ERROR
        assert result.data["crossref_result"]["status"] == BackendStatus.ERROR

    @pytest.mark.asyncio
    async def test_cached_flag_one_backend_error(self):
        """Test that cached=False when one backend has an error."""
        backend = CrossValidatorBackend()
        query_input = QueryInput(
            raw_input="Test Journal",
            normalized_name="test journal",
            identifiers={"issn": "1234-5678"},
        )

        # Mock one backend to raise exception, other returns result
        async def mock_error_query(qi):
            raise ValueError("Test error")

        async def mock_success_query(qi):
            return BackendResult(
                backend_name="crossref_analyzer",
                status=BackendStatus.FOUND,
                confidence=0.7,
                assessment="legitimate",
                data={"crossref_data": {}, "analysis": {}},
                sources=["crossref"],
                response_time=0.5,
                cached=True,
            )

        backend.openalex_backend.query = mock_error_query
        backend.crossref_backend.query = mock_success_query

        result = await backend.query(query_input)

        # Should complete and use the successful backend
        assert result.status == BackendStatus.FOUND
        assert result.cached is False  # One backend errored, so not fully cached
