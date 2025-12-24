# SPDX-License-Identifier: MIT
"""Tests for the cache assessment module."""

import hashlib
import tempfile
from pathlib import Path

import pytest

from aletheia_probe.cache import AssessmentCache
from aletheia_probe.cache.schema import init_database
from aletheia_probe.enums import AssessmentType
from aletheia_probe.models import AssessmentResult, BackendResult, BackendStatus


@pytest.fixture
def temp_cache():
    """Create a temporary cache for testing with all cache components."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        cache_path = Path(f.name)

    # Initialize database schema
    init_database(cache_path)

    cache = AssessmentCache(cache_path)
    yield cache

    # Cleanup
    cache_path.unlink(missing_ok=True)


@pytest.fixture
def sample_assessment_result():
    """Sample assessment result for testing."""
    return AssessmentResult(
        input_query="Test Journal",
        assessment=AssessmentType.PREDATORY,
        confidence=0.85,
        overall_score=0.9,
        backend_results=[
            BackendResult(
                backend_name="test_backend",
                status=BackendStatus.FOUND,
                confidence=0.8,
                assessment=AssessmentType.PREDATORY,
                data={"key": "value"},
                sources=["test_source"],
                response_time=0.1,
            )
        ],
        metadata=None,
        reasoning=["Found in predatory list"],
        processing_time=1.5,
    )


class TestCacheAssessment:
    """Test cases for CacheAssessment."""

    def test_validate_query_hash_valid(self, temp_cache):
        """Test that valid query hashes pass validation."""
        valid_hash = hashlib.md5(b"test").hexdigest()  # 32 hex characters
        # Should not raise an exception
        temp_cache._validate_query_hash(valid_hash)

    def test_validate_query_hash_empty(self, temp_cache):
        """Test that empty query hashes are rejected."""
        with pytest.raises(ValueError, match="query_hash cannot be empty or None"):
            temp_cache._validate_query_hash("")

        with pytest.raises(ValueError, match="query_hash cannot be empty or None"):
            temp_cache._validate_query_hash("   ")  # whitespace only

    def test_validate_query_hash_wrong_length(self, temp_cache):
        """Test that query hashes with wrong length are rejected."""
        with pytest.raises(ValueError, match="query_hash must be 32 characters long"):
            temp_cache._validate_query_hash("abc123")  # too short

        with pytest.raises(ValueError, match="query_hash must be 32 characters long"):
            temp_cache._validate_query_hash("a" * 64)  # too long

    def test_validate_query_hash_invalid_characters(self, temp_cache):
        """Test that query hashes with invalid characters are rejected."""
        with pytest.raises(
            ValueError, match="query_hash must contain only hexadecimal characters"
        ):
            temp_cache._validate_query_hash("g" + "a" * 31)  # 'g' is not hex

        with pytest.raises(
            ValueError, match="query_hash must contain only hexadecimal characters"
        ):
            temp_cache._validate_query_hash(
                "123456789012345678901234567890zz"
            )  # contains invalid chars 'z'

    def test_cache_assessment_result_invalid_hash(
        self, temp_cache, sample_assessment_result
    ):
        """Test that cache_assessment_result rejects invalid query hashes."""
        with pytest.raises(ValueError, match="query_hash cannot be empty or None"):
            temp_cache.cache_assessment_result(
                "", "Test Query", sample_assessment_result
            )

        with pytest.raises(ValueError, match="query_hash must be 32 characters long"):
            temp_cache.cache_assessment_result(
                "invalid", "Test Query", sample_assessment_result
            )

    def test_get_cached_assessment_invalid_hash(self, temp_cache):
        """Test that get_cached_assessment rejects invalid query hashes."""
        with pytest.raises(ValueError, match="query_hash cannot be empty or None"):
            temp_cache.get_cached_assessment("")

        with pytest.raises(ValueError, match="query_hash must be 32 characters long"):
            temp_cache.get_cached_assessment("invalid")

    def test_store_and_get_assessment(self, temp_cache, sample_assessment_result):
        """Test storing and retrieving assessment results."""
        query_hash = hashlib.md5(b"test_hash").hexdigest()

        # Store assessment
        temp_cache.cache_assessment_result(
            query_hash, "Test Journal", sample_assessment_result
        )

        # Retrieve assessment
        retrieved = temp_cache.get_cached_assessment(query_hash)

        assert retrieved is not None
        assert retrieved.input_query == sample_assessment_result.input_query
        assert retrieved.assessment == sample_assessment_result.assessment
        assert retrieved.confidence == sample_assessment_result.confidence

    def test_get_assessment_nonexistent(self, temp_cache):
        """Test retrieving non-existent assessment."""
        nonexistent_hash = hashlib.md5(b"nonexistent_hash").hexdigest()
        result = temp_cache.get_cached_assessment(nonexistent_hash)
        assert result is None

    def test_get_assessment_expired(self, temp_cache, sample_assessment_result):
        """Test that expired assessments are not returned."""
        query_hash = hashlib.md5(b"expired_hash").hexdigest()

        # Store with negative TTL (already expired)
        temp_cache.cache_assessment_result(
            query_hash, "Test Journal", sample_assessment_result, ttl_hours=-1
        )

        result = temp_cache.get_cached_assessment(query_hash)
        assert result is None

    def test_cleanup_expired_cache(self, temp_cache, sample_assessment_result):
        """Test cleanup of expired cache entries."""
        recent_hash = hashlib.md5(b"recent_hash").hexdigest()
        old_hash = hashlib.md5(b"old_hash").hexdigest()

        # Add entries with different expiration times
        temp_cache.cache_assessment_result(
            recent_hash, "Test Journal", sample_assessment_result, ttl_hours=24
        )
        temp_cache.cache_assessment_result(
            old_hash,
            "Test Journal",
            sample_assessment_result,
            ttl_hours=-1,  # Already expired
        )

        # Cleanup
        expired_count = temp_cache.cleanup_expired_cache()

        assert expired_count == 1  # Exactly the expired one

        # Verify cleanup worked
        recent_result = temp_cache.get_cached_assessment(recent_hash)
        old_result = temp_cache.get_cached_assessment(old_hash)

        assert recent_result is not None
        assert old_result is None

    def test_get_assessment_cache_count(self, temp_cache, sample_assessment_result):
        """Test getting assessment cache count."""
        # Initially empty
        assert temp_cache.get_assessment_cache_count() == 0

        # Add an assessment
        query_hash = hashlib.md5(b"Test Journal").hexdigest()
        temp_cache.cache_assessment_result(
            query_hash=query_hash,
            query_input="Test Journal",
            result=sample_assessment_result,
        )

        # Should be 1
        assert temp_cache.get_assessment_cache_count() == 1

    def test_clear_assessment_cache(self, temp_cache, sample_assessment_result):
        """Test clearing assessment cache."""
        # Add some assessments
        query_hash1 = hashlib.md5(b"Test Journal 1").hexdigest()
        temp_cache.cache_assessment_result(
            query_hash=query_hash1,
            query_input="Test Journal 1",
            result=sample_assessment_result,
        )
        query_hash2 = hashlib.md5(b"Test Journal 2").hexdigest()
        temp_cache.cache_assessment_result(
            query_hash=query_hash2,
            query_input="Test Journal 2",
            result=sample_assessment_result,
        )

        # Clear cache
        count = temp_cache.clear_assessment_cache()
        assert count == 2
        assert temp_cache.get_assessment_cache_count() == 0
