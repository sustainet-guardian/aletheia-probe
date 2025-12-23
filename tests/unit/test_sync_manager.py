# SPDX-License-Identifier: MIT
"""Tests for the CacheSyncManager class."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest

from aletheia_probe.backends.base import CachedBackend, HybridBackend
from aletheia_probe.cache_sync import CacheSyncManager


class MockCachedBackend(CachedBackend):
    """Mock cached backend for testing."""

    def __init__(self, name: str, source_name: str):
        super().__init__(source_name, "predatory")
        self._name = name

    def get_name(self) -> str:
        return self._name

    def get_description(self) -> str:
        return f"Mock cached backend {self._name}"


class MockHybridBackend(HybridBackend):
    """Mock hybrid backend for testing."""

    def __init__(self, name: str):
        super().__init__()
        self._name = name

    async def _query_api(self, query_input):
        """Implementation of abstract method."""
        from aletheia_probe.models import BackendResult, BackendStatus

        return BackendResult(
            backend_name=self._name,
            status=BackendStatus.NOT_FOUND,
            confidence=0.0,
            assessment=None,
            response_time=0.0,
        )

    def get_name(self) -> str:
        return self._name

    def get_description(self) -> str:
        return f"Mock hybrid backend {self._name}"


@pytest.fixture
def sync_manager():
    """Create cache sync manager for testing."""
    return CacheSyncManager()


@pytest.fixture
def mock_config():
    """Create mock configuration."""
    config = Mock()
    config.cache = Mock()
    config.cache.auto_sync = True
    config.cache.cleanup_disabled = True
    config.cache.update_threshold_days = 7
    return config


class TestCacheSyncManager:
    """Test cases for CacheSyncManager."""

    @pytest.mark.asyncio
    async def test_sync_cache_with_config_auto_sync_disabled(
        self, sync_manager, mock_config
    ):
        """Test sync when auto sync is disabled."""
        mock_config.cache.auto_sync = False

        with patch.object(
            sync_manager.config_manager, "load_config", return_value=mock_config
        ):
            result = await sync_manager.sync_cache_with_config(force=False)

            assert result["status"] == "skipped"
            assert result["reason"] == "auto_sync_disabled"

    @pytest.mark.asyncio
    async def test_sync_cache_with_config_force_override(
        self, sync_manager, mock_config
    ):
        """Test sync with force override when auto sync is disabled."""
        mock_config.cache.auto_sync = False

        with (
            patch.object(
                sync_manager.config_manager, "load_config", return_value=mock_config
            ),
            patch(
                "aletheia_probe.cache_sync.sync_manager.get_backend_registry"
            ) as mock_get_registry,
            patch.object(
                sync_manager.config_manager, "get_enabled_backends", return_value=[]
            ),
        ):
            mock_registry = Mock()
            mock_registry.get_backend_names.return_value = []
            mock_get_registry.return_value = mock_registry

            result = await sync_manager.sync_cache_with_config(force=True)

            assert "status" not in result or result.get("status") != "skipped"

    @pytest.mark.asyncio
    async def test_sync_cache_with_config_sync_in_progress(
        self, sync_manager, mock_config
    ):
        """Test sync when sync is already in progress."""
        sync_manager.sync_in_progress = True

        result = await sync_manager.sync_cache_with_config()

        assert result["status"] == "skipped"
        assert result["reason"] == "sync_in_progress"

    @pytest.mark.asyncio
    async def test_sync_cache_enabled_backend(self, sync_manager, mock_config):
        """Test sync for enabled backend."""
        backend = MockCachedBackend("test_backend", "test_source")

        with (
            patch.object(
                sync_manager.config_manager, "load_config", return_value=mock_config
            ),
            patch(
                "aletheia_probe.cache_sync.sync_manager.get_backend_registry"
            ) as mock_get_registry,
            patch.object(
                sync_manager.config_manager,
                "get_enabled_backends",
                return_value=["test_backend"],
            ),
            patch.object(
                sync_manager, "_ensure_backend_data_available", new_callable=AsyncMock
            ) as mock_ensure,
        ):
            mock_registry = Mock()
            mock_registry.get_backend_names.return_value = ["test_backend"]
            mock_registry.get_backend.return_value = backend
            mock_get_registry.return_value = mock_registry
            mock_ensure.return_value = {"status": "success", "records_updated": 100}

            result = await sync_manager.sync_cache_with_config()

            assert "test_backend" in result
            assert result["test_backend"]["status"] == "success"
            mock_ensure.assert_called_once_with(backend, False, True)

    @pytest.mark.asyncio
    async def test_sync_cache_disabled_backend(self, sync_manager, mock_config):
        """Test sync for disabled backend."""
        backend = MockCachedBackend("disabled_backend", "disabled_source")

        with (
            patch.object(
                sync_manager.config_manager, "load_config", return_value=mock_config
            ),
            patch(
                "aletheia_probe.cache_sync.sync_manager.get_backend_registry"
            ) as mock_get_registry,
            patch.object(
                sync_manager.config_manager, "get_enabled_backends", return_value=[]
            ),
            patch.object(
                sync_manager, "_cleanup_disabled_backend_data", new_callable=AsyncMock
            ) as mock_cleanup,
        ):
            mock_registry = Mock()
            mock_registry.get_backend_names.return_value = ["disabled_backend"]
            mock_registry.get_backend.return_value = backend
            mock_get_registry.return_value = mock_registry
            mock_cleanup.return_value = {"status": "cleaned", "records_removed": 50}

            result = await sync_manager.sync_cache_with_config()

            assert "disabled_backend" in result
            assert result["disabled_backend"]["status"] == "cleaned"
            mock_cleanup.assert_called_once_with(backend, True)

    @pytest.mark.asyncio
    async def test_sync_cache_cleanup_disabled(self, sync_manager, mock_config):
        """Test sync when cleanup is disabled."""
        mock_config.cache.cleanup_disabled = False
        backend = MockCachedBackend("disabled_backend", "disabled_source")

        with (
            patch.object(
                sync_manager.config_manager, "load_config", return_value=mock_config
            ),
            patch(
                "aletheia_probe.cache_sync.sync_manager.get_backend_registry"
            ) as mock_get_registry,
            patch.object(
                sync_manager.config_manager, "get_enabled_backends", return_value=[]
            ),
        ):
            mock_registry = Mock()
            mock_registry.get_backend_names.return_value = ["disabled_backend"]
            mock_registry.get_backend.return_value = backend
            mock_get_registry.return_value = mock_registry

            result = await sync_manager.sync_cache_with_config()

            assert result["disabled_backend"]["status"] == "skipped"
            assert result["disabled_backend"]["reason"] == "cleanup_disabled"

    @pytest.mark.asyncio
    async def test_sync_cache_backend_error(self, sync_manager, mock_config):
        """Test sync when backend raises an error."""
        with (
            patch.object(
                sync_manager.config_manager, "load_config", return_value=mock_config
            ),
            patch(
                "aletheia_probe.cache_sync.sync_manager.get_backend_registry"
            ) as mock_get_registry,
            patch.object(
                sync_manager.config_manager,
                "get_enabled_backends",
                return_value=["error_backend"],
            ),
        ):
            mock_registry = Mock()
            mock_registry.get_backend_names.return_value = ["error_backend"]
            mock_registry.get_backend.side_effect = Exception("Backend error")
            mock_get_registry.return_value = mock_registry

            result = await sync_manager.sync_cache_with_config()

            assert "error_backend" in result
            assert result["error_backend"]["status"] == "error"
            assert "Backend error" in result["error_backend"]["error"]

    @pytest.mark.asyncio
    async def test_ensure_backend_data_available_no_data(self, sync_manager):
        """Test ensuring data is available when none exists."""
        backend = MockCachedBackend("test_backend", "test_source")

        with (
            patch(
                "aletheia_probe.cache_sync.sync_manager.DataSourceManager"
            ) as mock_get_cache_manager,
            patch.object(
                sync_manager, "_fetch_backend_data", new_callable=AsyncMock
            ) as mock_fetch,
        ):
            mock_cache_manager = Mock()
            mock_get_cache_manager.return_value = mock_cache_manager
            mock_cache_manager.has_source_data.return_value = False
            mock_fetch.return_value = {"status": "success", "records_updated": 100}

            result = await sync_manager._ensure_backend_data_available(backend)

            assert result["status"] == "success"
            # Verify call was made (signature now includes AsyncDBWriter as 3rd param)
            mock_fetch.assert_called_once()
            assert mock_fetch.call_args[0][0] == "test_source"
            assert not mock_fetch.call_args[0][1]

    @pytest.mark.asyncio
    async def test_ensure_backend_data_available_stale_data(self, sync_manager):
        """Test ensuring data is available when data is stale."""
        backend = MockCachedBackend("test_backend", "test_source")

        with (
            patch(
                "aletheia_probe.cache_sync.sync_manager.DataSourceManager"
            ) as mock_get_cache_manager,
            patch.object(sync_manager, "_should_update_source", return_value=True),
            patch.object(
                sync_manager, "_fetch_backend_data", new_callable=AsyncMock
            ) as mock_fetch,
        ):
            mock_cache_manager = Mock()
            mock_get_cache_manager.return_value = mock_cache_manager
            mock_cache_manager.has_source_data.return_value = True
            mock_fetch.return_value = {"status": "success", "records_updated": 50}

            result = await sync_manager._ensure_backend_data_available(backend)

            assert result["status"] == "success"
            # Verify call was made (signature now includes AsyncDBWriter as 3rd param)
            mock_fetch.assert_called_once()
            assert mock_fetch.call_args[0][0] == "test_source"
            assert not mock_fetch.call_args[0][1]

    @pytest.mark.asyncio
    async def test_ensure_backend_data_available_fresh_data(self, sync_manager):
        """Test ensuring data is available when data is fresh."""
        backend = MockCachedBackend("test_backend", "test_source")

        with (
            patch(
                "aletheia_probe.cache_sync.sync_manager.DataSourceManager"
            ) as mock_get_cache_manager,
            patch.object(sync_manager, "_should_update_source", return_value=False),
        ):
            mock_cache_manager = Mock()
            mock_get_cache_manager.return_value = mock_cache_manager
            mock_cache_manager.has_source_data.return_value = True

            result = await sync_manager._ensure_backend_data_available(backend)

            assert result["status"] == "current"
            assert result["reason"] == "data_fresh"

    @pytest.mark.asyncio
    async def test_ensure_backend_data_not_cached_backend(self, sync_manager):
        """Test ensuring data for non-cached backend."""
        backend = MockHybridBackend("hybrid_backend")

        result = await sync_manager._ensure_backend_data_available(backend)

        assert result["status"] == "skipped"
        assert result["reason"] == "not_cached_backend"

    @pytest.mark.asyncio
    async def test_cleanup_disabled_backend_data(self, sync_manager):
        """Test cleanup of disabled backend data."""
        backend = MockCachedBackend("disabled_backend", "disabled_source")

        with patch(
            "aletheia_probe.cache_sync.sync_manager.DataSourceManager"
        ) as mock_data_source_manager:
            mock_cache_manager = Mock()
            mock_data_source_manager.return_value = mock_cache_manager
            mock_cache_manager.has_source_data.return_value = True
            mock_cache_manager.remove_source_data.return_value = 25
            mock_cache_manager.log_update = Mock()

            result = await sync_manager._cleanup_disabled_backend_data(backend)

            assert result["status"] == "cleaned"
            assert result["records_removed"] == 25
            mock_cache_manager.remove_source_data.assert_called_once_with(
                "disabled_source"
            )

    @pytest.mark.asyncio
    async def test_cleanup_disabled_backend_no_data(self, sync_manager):
        """Test cleanup when no data exists."""
        backend = MockCachedBackend("disabled_backend", "disabled_source")

        with patch(
            "aletheia_probe.cache_sync.sync_manager.DataSourceManager"
        ) as mock_data_source_manager:
            mock_cache_manager = Mock()
            mock_data_source_manager.return_value = mock_cache_manager
            mock_cache_manager.has_source_data.return_value = False

            result = await sync_manager._cleanup_disabled_backend_data(backend)

            assert result["status"] == "skipped"
            assert result["reason"] == "no_data_to_cleanup"

    @pytest.mark.asyncio
    async def test_cleanup_disabled_backend_error(self, sync_manager):
        """Test cleanup with error."""
        import sqlite3

        backend = MockCachedBackend("disabled_backend", "disabled_source")

        with patch(
            "aletheia_probe.cache_sync.sync_manager.DataSourceManager"
        ) as mock_data_source_manager:
            mock_cache_manager = Mock()
            mock_data_source_manager.return_value = mock_cache_manager
            mock_cache_manager.has_source_data.return_value = True
            mock_cache_manager.remove_source_data.side_effect = sqlite3.Error(
                "Cleanup failed"
            )
            mock_cache_manager.log_update = Mock()

            result = await sync_manager._cleanup_disabled_backend_data(backend)

            assert result["status"] == "error"
            assert "Cleanup failed" in result["error"]

    @pytest.mark.asyncio
    async def test_fetch_backend_data(self, sync_manager):
        """Test fetching backend data."""
        mock_source = Mock()
        mock_source.get_name.return_value = "test_source"

        with patch("aletheia_probe.cache_sync.sync_manager.data_updater") as mock_updater:
            mock_updater.sources = [mock_source]
            mock_updater.update_source = AsyncMock(
                return_value={"status": "success", "records_updated": 100}
            )

            result = await sync_manager._fetch_backend_data("test_source")

            assert result["status"] == "success"
            assert result["records_updated"] == 100

    @pytest.mark.asyncio
    async def test_fetch_backend_data_source_not_found(self, sync_manager):
        """Test fetching data for unknown source."""
        with patch("aletheia_probe.cache_sync.sync_manager.data_updater") as mock_updater:
            mock_updater.sources = []

            result = await sync_manager._fetch_backend_data("unknown_source")

            assert result["status"] == "error"
            assert "No data source configured" in result["error"]

    @pytest.mark.asyncio
    async def test_fetch_backend_data_update_error(self, sync_manager):
        """Test fetching data with update error."""
        mock_source = Mock()
        mock_source.get_name.return_value = "test_source"

        with patch("aletheia_probe.cache_sync.sync_manager.data_updater") as mock_updater:
            mock_updater.sources = [mock_source]
            mock_updater.update_source = AsyncMock(
                side_effect=Exception("Update failed")
            )

            result = await sync_manager._fetch_backend_data("test_source")

            assert result["status"] == "error"
            assert "Update failed" in result["error"]

    def test_should_update_source_never_updated(self, sync_manager):
        """Test should update for source that was never updated."""
        with (
            patch(
                "aletheia_probe.cache_sync.sync_manager.DataSourceManager"
            ) as mock_get_cache_manager,
            patch.object(sync_manager.config_manager, "load_config"),
        ):
            mock_cache_manager = Mock()
            mock_get_cache_manager.return_value = mock_cache_manager
            mock_cache_manager.get_source_last_updated.return_value = None

            should_update = sync_manager._should_update_source("test_source")

            assert should_update is True

    def test_should_update_source_old_data(self, sync_manager, mock_config):
        """Test should update for old data."""
        old_date = datetime.now() - timedelta(days=10)

        with (
            patch(
                "aletheia_probe.cache_sync.sync_manager.DataSourceManager"
            ) as mock_get_cache_manager,
            patch.object(
                sync_manager.config_manager, "load_config", return_value=mock_config
            ),
        ):
            mock_cache_manager = Mock()
            mock_get_cache_manager.return_value = mock_cache_manager
            mock_cache_manager.get_source_last_updated.return_value = old_date

            should_update = sync_manager._should_update_source("test_source")

            assert should_update is True

    def test_should_update_source_fresh_data(self, sync_manager, mock_config):
        """Test should update for fresh data."""
        recent_date = datetime.now() - timedelta(days=3)

        with (
            patch(
                "aletheia_probe.cache_sync.sync_manager.DataSourceManager"
            ) as mock_get_cache_manager,
            patch.object(
                sync_manager.config_manager, "load_config", return_value=mock_config
            ),
        ):
            mock_cache_manager = Mock()
            mock_get_cache_manager.return_value = mock_cache_manager
            mock_cache_manager.get_source_last_updated.return_value = recent_date

            should_update = sync_manager._should_update_source("test_source")

            assert should_update is False

    def test_get_sync_status(self, sync_manager):
        """Test getting sync status."""
        cached_backend = MockCachedBackend("cached_backend", "cached_source")
        hybrid_backend = MockHybridBackend("hybrid_backend")

        with (
            patch(
                "aletheia_probe.cache_sync.sync_manager.get_backend_registry"
            ) as mock_get_registry,
            patch.object(
                sync_manager.config_manager,
                "get_enabled_backends",
                return_value=["cached_backend"],
            ),
            patch(
                "aletheia_probe.cache_sync.sync_manager.DataSourceManager"
            ) as mock_get_cache_manager,
        ):
            mock_registry = Mock()
            mock_registry.get_backend_names.return_value = [
                "cached_backend",
                "hybrid_backend",
            ]
            mock_registry.get_backend.side_effect = lambda name: (
                cached_backend if name == "cached_backend" else hybrid_backend
            )
            mock_get_registry.return_value = mock_registry
            mock_cache_manager = Mock()
            mock_get_cache_manager.return_value = mock_cache_manager
            mock_cache_manager.get_available_sources.return_value = ["cached_source"]
            mock_cache_manager.get_source_last_updated.return_value = datetime.now()
            mock_cache_manager.get_source_statistics.return_value = {
                "cached_source": {"total": 100}
            }

            status = sync_manager.get_sync_status()

            assert status["sync_in_progress"] is False
            assert "cached_backend" in status["backends"]
            assert "hybrid_backend" in status["backends"]

            cached_status = status["backends"]["cached_backend"]
            hybrid_status = status["backends"]["hybrid_backend"]

            assert cached_status["enabled"] is True
            assert cached_status["type"] == "cached"
            assert cached_status["has_data"] is True

            assert hybrid_status["enabled"] is False
            assert hybrid_status["type"] == "hybrid"

    def test_get_sync_status_backend_error(self, sync_manager):
        """Test getting sync status with backend error."""
        with (
            patch(
                "aletheia_probe.cache_sync.sync_manager.get_backend_registry"
            ) as mock_get_registry,
            patch.object(
                sync_manager.config_manager, "get_enabled_backends", return_value=[]
            ),
            patch(
                "aletheia_probe.cache_sync.sync_manager.DataSourceManager"
            ) as mock_get_cache_manager,
        ):
            mock_registry = Mock()
            mock_registry.get_backend_names.return_value = ["error_backend"]
            mock_registry.get_backend.side_effect = Exception("Backend error")
            mock_get_registry.return_value = mock_registry
            mock_cache_manager = Mock()
            mock_get_cache_manager.return_value = mock_cache_manager
            mock_cache_manager.get_available_sources.return_value = []

            status = sync_manager.get_sync_status()

            assert "error_backend" in status["backends"]
            assert "error" in status["backends"]["error_backend"]
            assert "Backend error" in status["backends"]["error_backend"]["error"]
