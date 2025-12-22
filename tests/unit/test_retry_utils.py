# SPDX-License-Identifier: MIT
"""Tests for retry utilities."""

import time
from unittest.mock import patch

import pytest

from aletheia_probe.retry_utils import async_retry_with_backoff


class TestAsyncRetryWithBackoff:
    """Test cases for the async_retry_with_backoff decorator."""

    @pytest.mark.asyncio
    async def test_async_successful_call_no_retry(self):
        """Test that successful async calls don't trigger retries."""
        call_count = 0

        @async_retry_with_backoff(max_retries=3)
        async def async_successful_func():
            nonlocal call_count
            call_count += 1
            return "async_success"

        result = await async_successful_func()
        assert result == "async_success"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_async_failure_then_success(self):
        """Test that async function succeeds after initial failures."""
        call_count = 0

        @async_retry_with_backoff(max_retries=3, initial_delay=0.01)
        async def async_flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Temporary async error")
            return "async_success"

        result = await async_flaky_func()
        assert result == "async_success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_async_max_retries_exceeded(self):
        """Test that async function raises exception after max retries."""
        call_count = 0

        @async_retry_with_backoff(max_retries=2, initial_delay=0.01)
        async def async_always_fails():
            nonlocal call_count
            call_count += 1
            raise ValueError("Always fails async")

        with pytest.raises(ValueError, match="Always fails async"):
            await async_always_fails()

        assert call_count == 3  # Initial call + 2 retries

    @pytest.mark.asyncio
    async def test_async_exponential_backoff_timing(self):
        """Test that async exponential backoff timing works correctly."""
        call_times = []

        @async_retry_with_backoff(
            max_retries=3, initial_delay=0.1, exponential_base=2.0
        )
        async def async_timing_func():
            call_times.append(time.time())
            raise ValueError("Always fails")

        with pytest.raises(ValueError):
            await async_timing_func()

        # We should have 4 calls (initial + 3 retries)
        assert len(call_times) == 4

        # Check that delays are roughly correct
        time_diff_1 = call_times[1] - call_times[0]
        time_diff_2 = call_times[2] - call_times[1]
        time_diff_3 = call_times[3] - call_times[2]

        # First delay should be ~0.1s
        assert 0.08 < time_diff_1 < 0.15
        # Second delay should be ~0.2s
        assert 0.18 < time_diff_2 < 0.25
        # Third delay should be ~0.4s
        assert 0.38 < time_diff_3 < 0.45

    @pytest.mark.asyncio
    async def test_async_function_with_arguments(self):
        """Test that decorated async functions can accept arguments."""
        call_count = 0

        @async_retry_with_backoff(max_retries=2, initial_delay=0.01)
        async def async_func_with_args(x, y, z=None):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("Retry once")
            return f"async-{x}-{y}-{z}"

        result = await async_func_with_args("a", "b", z="c")
        assert result == "async-a-b-c"
        assert call_count == 2

    @pytest.mark.asyncio
    @patch("aletheia_probe.retry_utils.detail_logger")
    async def test_async_logging_on_retry(self, mock_logger):
        """Test that async retry attempts are logged correctly."""
        call_count = 0

        @async_retry_with_backoff(max_retries=2, initial_delay=0.01)
        async def async_logged_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Async retry error")
            return "async_success"

        result = await async_logged_func()
        assert result == "async_success"

        # Should log 2 retry attempts
        assert mock_logger.debug.call_count == 2

        # Check log message content
        calls = mock_logger.debug.call_args_list
        assert "failed (attempt 1/2)" in calls[0][0][0]
        assert "failed (attempt 2/2)" in calls[1][0][0]

    @pytest.mark.asyncio
    @patch("aletheia_probe.retry_utils.detail_logger")
    async def test_async_logging_on_final_failure(self, mock_logger):
        """Test that async final failure is logged correctly."""

        @async_retry_with_backoff(max_retries=1, initial_delay=0.01)
        async def async_final_failure_func():
            raise ValueError("Always fails async")

        with pytest.raises(ValueError):
            await async_final_failure_func()

        # Should log 1 retry attempt + 1 final failure
        assert mock_logger.debug.call_count == 2

        # Check final failure message
        calls = mock_logger.debug.call_args_list
        assert "failed after 1 retries" in calls[1][0][0]

    @pytest.mark.asyncio
    async def test_async_specific_exception_types(self):
        """Test that only specified exception types are retried for async functions."""
        call_count = 0

        @async_retry_with_backoff(
            max_retries=2, initial_delay=0.01, exceptions=(ValueError,)
        )
        async def async_selective_retry_func():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("This should be retried")
            elif call_count == 2:
                raise TypeError("This should not be retried")
            return "success"

        with pytest.raises(TypeError, match="This should not be retried"):
            await async_selective_retry_func()

        assert call_count == 2
